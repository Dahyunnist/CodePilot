# S2 学习记录：MCP 工具边界

## 本阶段目标

让 CodePilot 工具可被 MCP Host 发现和调用；Agent 也能经 MCP stdio 子进程使用仓库检索、读取和测试工具。文件修改仍只发生在隔离工作副本；写回源仓库继续走 S1 审批节点。

## 运行与数据流

1. `codepilot.cli` 根据 `--tool-backend mcp` 启动 `python -m codepilot.mcp_server` 子进程。SDK 通过 stdio 执行 MCP initialize、`tools/list` 和 `tools/call`。
2. `MCPServer` 从函数签名生成参数 schema。外部名称为 `repo_search`、`repo_read`、`repo_diff`、`test_status`、`run_tests`。
3. MCP Host / Agent 收到名称、用途和参数定义。`HybridMCPToolRegistry` 把读取、检索、测试映射到 MCP；`apply_patch` 与 `git_diff` 留在宿主进程。
4. MCP 服务端把请求转换为 `ToolCall`，交给现有 `ToolRegistry.execute()`。未知工具、路径穿越、敏感文件和主机测试审批仍由既有策略判定。
5. `ToolOutcome` 把退出码、标准输出、错误输出、错误类型和耗时带回客户端。`run_tests` 的失败被映射为测试失败，不会伪装成协议成功。
6. MCP 客户端用一个持续 stdio session 顺序发送请求；单请求超时会取消调用。关闭 Agent 时 SDK 关闭客户端和子进程。

## 关键文件

- `codepilot/mcp_server.py`：官方 SDK v2 MCPServer、固定工具边界和 ToolRegistry 路由。
- `codepilot/mcp_client.py`：官方 SDK Client、AnyIO 持久 session、allowlist、schema 读取、超时映射和 Agent 混合工具表。
- `codepilot/tools/builtins.py`、`codepilot/tools/base.py`：`test_status` 与最近测试状态。
- `codepilot/cli.py`：`--tool-backend mcp` 装配 MCP stdio 子进程；标准输出只保留协议数据。
- `tests/test_mcp.py`、`tests/test_cli_e2e.py`：工具发现、schema、真实 `tools/call`、错误、超时、敏感路径、越权工具、主机审批和 Agent 集成。

## 权限边界

- MCP 服务不暴露 `apply_patch`，也没有源仓库写回接口。
- MCP 读取与测试都经过服务端 `ToolRegistry`。Agent 的工作副本补丁经宿主 ToolRegistry 执行。
- MCP 客户端只接收 CodePilot 固定 allowlist。服务端即使再暴露 `delete_everything`，Agent 也不会拿到 schema 或执行它。
- `test_run` 仅在 Docker 模式默认暴露。主机模式必须在 MCP 服务启动时显式批准；CLI 的 `--tool-backend mcp --execution host` 也要求 `--approve-host-tests`。
- SDK 的 stdio 客户端只继承其安全环境白名单，不把 `.env` 中的 `LLM_API_KEY` 传给工具子进程。模型密钥只留在宿主 ModelClient。
- `ToolAnnotations` 是给 MCP Host 的提示，不是授权机制。真正的检查仍是服务端 Registry。

## 设计取舍

- 按 MCP Python SDK 当前稳定 v2 接口实现；不自行拼 JSON-RPC。官方 SDK 同时提供 Client、stdio 和 Streamable HTTP transport。
- 为 Agent 保留既有 `search_code`、`read_file`、`run_tests` 名称；混合注册表把它们映射到 MCP 工具名，避免改动 Agent 的测试判定语义。
- 一条 MCP session 顺序调用，保持 request/reply 对应并简化取消；独立只读并行能力以后可按 request ID 实现。
- `test.status` 是服务进程最近一次测试结果。重启 MCP 服务会清空该短期状态；持久状态仍由 S1 run state 记录。
- stdio 适合本机单仓库集成。远程部署、认证和多租户授权尚未实现。

官方参考：[MCP Python SDK v2](https://py.sdk.modelcontextprotocol.io/)、[SDK Client](https://py.sdk.modelcontextprotocol.io/client/)、[SDK Tools](https://py.sdk.modelcontextprotocol.io/servers/tools/)、[MCP Tools 协议](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)。协议定义 `tools/list`、`tools/call` 和工具 schema；SDK v2 将工具函数参数类型转换为 JSON Schema。

## 验证结果

- NN 环境：Python 3.11，官方 `mcp` SDK **2.3.0**；LangGraph **1.2.16**。
- 完整回归：`D:\\Anaconda3\\envs\\NN\\python.exe -m pytest -q`，**84 passed**。
- MCP 测试覆盖：SDK discovery 与 schema；in-process 和 stdio 客户端调用；不信任服务端新增工具；路径穿越和 `.env` 拒绝；未批准主机测试不暴露；测试失败保留退出码；调用超时映射为 `timeout`。
- 真实模型 + MCP stdio + Docker：`parse-config`，Agent `success`，6 步，12,225 tokens，9.0 秒；Docker 测试 `3 passed`。
- Token：输入 11,426（缓存命中 9,216，未命中 2,210），输出 799。按 2026-10-19 15:50 UTC DeepSeek 官方非高峰价估算 **$0.000839**。该数是模型 token 估算，不是账户账单。
- 轨迹：`reports/live-model-20261019-s2/traces/1e9f458f6c1a4575831d42c73a331696.jsonl`；报告：`reports/live-model-20261019-s2/runs/1e9f458f6c1a4575831d42c73a331696.md`。SQLite 检查点不提交。

## 失败场景

1. MCP Host 请求 `../outside.txt` 或 `.env`：MCP 返回工具错误；底层 `ToolRegistry` 拒绝路径，秘密内容不回传。
2. 恶意或误配置 MCP 服务额外声明 `delete_everything`：固定 allowlist 不会把它交给 Agent；直接发起该工具调用也被拒绝。
3. Docker 或 stdio server 响应超时：客户端返回 `ToolResult.error_type="timeout"`；Agent 不把超时记成测试失败。
4. 主机测试未批准：服务端不公开 `run_tests`，客户端也会拦截调用。

## 10 分钟动手实验

1. 用 CodePilot CLI 加 `--tool-backend mcp` 跑一个干净 fixture，观察 Agent 仍按中文任务调用工具。
2. 用 `python -m codepilot.mcp_server --repo <仓库> --test-command "python -m pytest tests -q" --execution docker` 接入 MCP Inspector 或任意 MCP Host。
3. 用 `tools/list` 查看每个工具的 schema，再调用 `repo_search` 和 `repo_read`。
4. 尝试读取 `../outside.txt`、`.env`，再调用 `apply_patch`；确认服务拒绝越权操作。
5. 开启 `--execution host` 但不加批准参数；确认 `run_tests` 不出现在工具列表。

## 面试追问

**为什么 MCP 注解不能代替授权？** 它们是客户端提示。恶意客户端可忽略提示；必须在服务端按工具名、参数和路径执行权限检查。

**为什么 Agent 的 patch 不经过 MCP？** 此阶段 MCP 服务对外只给读取和测试能力。Agent 的补丁写入工作副本由宿主 Registry 负责；源仓库回写另由 S1 人工审批节点控制。

**如何避免 MCP 工具名与 Agent 内部接口互相绑定？** MCP schema 作为边界契约；Hybrid Registry 显式映射名称和响应。对 Agent 暴露稳定的旧名称，服务端仍可演进自己的工具实现。

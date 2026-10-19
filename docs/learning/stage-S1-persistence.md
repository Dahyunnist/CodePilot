# S1 学习记录：持久化运行与审批恢复

## 本阶段目标

让长时间修复任务能在进程中断后接续，并让写回源仓库必须经过可审计的人类批准。旧的 `Agent.run(task)` 调用仍有效；持久化由 CLI 和 LangGraph 编排层负责。

## 数据流

1. `codepilot.cli.main()` 创建干净工作副本、Task、ModelClient、ToolRegistry 和 TraceLogger。
2. `start_durable_run()` 用运行 ID 作为 LangGraph `thread_id`，在 `reports/run-state.sqlite` 建立 SQLite 检查点。
3. `run_agent` 节点调用原有显式 Agent 循环。Agent 每轮保存消息、工具结果、测试状态、调用次数和耗时到同一 SQLite 数据库的 `agent_progress` 表。
4. 若进程中断，`resume --continue-run` 重新进入未完成节点；Agent 从最近保存的观察结果继续，不重复已完成的工具调用。
5. 如果修复成功且请求了 `--apply-to-repo`，`approval_gate` 用 LangGraph `interrupt()` 保存检查点，并显示基线提交、补丁 SHA-256 和 diff。
6. `resume --approve` 才调用 `WorkspaceManager.apply_changes()`。回写前重算补丁哈希，并验证源仓库 HEAD、干净状态和 `git apply --check`。`resume --reject` 结束流程，不写源仓库。

## 关键代码

- `codepilot/run_graph.py`：有向图、SQLite saver、Agent 进度表、审批中断、补丁哈希核对和回写节点。
- `codepilot/agent.py`：`run()` 支持恢复 AgentState；工具观察落盘后再进入下一轮。
- `codepilot/cli.py`：`run` 创建持久化流程；`resume` 只接受有效中断或待执行节点。
- `codepilot/workspace.py`：沿用既有源仓库 HEAD、工作区干净状态和补丁可应用检查。
- `tests/test_agent.py`、`tests/test_cli_e2e.py`：模拟 Agent 中断恢复、跨进程审批、拒绝、重复恢复和陈旧补丁。

LangGraph checkpointer 保存图节点状态；`agent_progress` 保存运行于单个节点内部的 Agent 步骤。两层都需要：只在节点边界保存，无法从尚未完成的 Agent 节点恢复到上一次工具结果。

## 设计取舍与边界

- 继续使用现有 Agent 循环，不把整个 Agent 重写成 LangGraph 专用消息模型，减少兼容风险。
- SQLite 文件保留任务内容、对话消息和工具结果，可能含有公司源码片段。文件默认位于 `reports/` 并由 `.gitignore` 排除；部署到团队服务器前需配置访问控制、保留期限和加密备份。
- 模型请求可能在收到响应后、保存检查点前被强制终止；恢复时会重发该轮请求，可能产生重复调用费用。工具执行完成并保存观察后，不会重放该工具。
- 当前实际故障恢复验证覆盖“Agent 完成后等待回写审批，再由新 CLI 进程批准”。Agent 节点内部的进程退出由回调测试模拟；尚未用真实 `kill` 在 Docker 测试期间终止进程。
- LangGraph SQLite 适合单机开发和试点。团队并发服务应评估 PostgreSQL saver、数据保留、锁争用和租户隔离。

官方设计依据：LangGraph [checkpointer 与 store](https://docs.langchain.com/oss/python/langgraph/persistence) 用于区分线程状态与跨线程记忆；[interrupt 恢复](https://docs.langchain.com/oss/python/langgraph/interrupts) 要求同一 `thread_id` 和可持久化 checkpointer。CodePilot 此阶段只实现任务级检查点，不实现长期记忆 store。

## 验证结果

- NN 环境：`D:\Anaconda3\envs\NN\python.exe`；LangGraph `1.2.16`，SQLite checkpointer `3.1.2`。
- 回归测试：`D:\\Anaconda3\\envs\\NN\\python.exe -m pytest -q`，**76 passed**。
- 最终版真实模型 + Docker fixture：`parse-config`，Agent `needs_approval`，5 步，10,215 tokens，7.5 秒；容器测试 `3 passed`。
- Token 分解：输入 9,446（缓存命中 7,936，未命中 1,510），输出 769。运行在 2026-10-19 15:36 UTC；按官方非高峰价估算 **$0.000712**。DeepSeek 账单是最终金额；缓存命中和实际价格会影响费用。
- 第一个 CLI 进程在测试成功后返回审批中断；第二个 CLI 进程以相同 `run_id` 恢复，批准后将补丁回写至隔离 fixture。回写后源 fixture 独立测试 `3 passed`。
- 报告：`reports/live-model-20261019-s1-final/runs/2f18f1cc04724ce3b259846a4efdddda.md`；轨迹：`reports/live-model-20261019-s1-final/traces/2f18f1cc04724ce3b259846a4efdddda.jsonl`。SQLite 运行数据库不纳入 Git。

费用估算采用官方 [DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)页面：缓存命中 $0.003/百万输入 token，缓存未命中 $0.15/百万输入 token，输出 $0.60/百万 token。运行时间为 2026-10-19 15:26 UTC，页面定义的非高峰时段。

## 失败场景

1. 等待批准时工作副本补丁发生变化：恢复时 SHA-256 不匹配，标记 `stale_patch`，拒绝回写，旧测试不再被信任。
2. 用户恢复已完成的运行：LangGraph 快照没有待恢复节点，CLI 返回错误，避免重复执行回写。
3. 源仓库 HEAD 改变或出现未提交文件：`WorkspaceManager` 拒绝应用补丁；错误保留在运行结果。

## 10 分钟动手实验

1. 用本机干净 Git fixture 执行 `python -m codepilot run ... --apply-to-repo --state-db reports/demo.sqlite`。
2. 记下终端的运行 ID，打开报告检查测试结论、diff 和 SHA-256。
3. 运行 `python -m codepilot resume --run-id <运行ID> --reject --state-db reports/demo.sqlite`，确认源仓库未改变。
4. 重跑并选择 `--approve`；再用同一 ID 重复恢复，确认第二次被拒绝。
5. 在等待审批时改动工作副本，再批准；确认陈旧补丁无法写回。

## 面试追问

**为什么需要 LangGraph checkpointer 和独立进度表？** Checkpointer 只在节点边界保存；Agent 循环是一个长节点。进度表保存节点内部每轮消息与工具结果。

**中断恢复是否保证模型请求严格只执行一次？** 否。响应返回后写 checkpoint 前强制终止会重发请求。工具调用完成并保存观察后可以避免重复执行工具。

**为什么审批后仍检查补丁哈希？** 审批绑定具体 diff。工作副本在暂停期间发生变化时，先前的测试和批准不再适用于新补丁。

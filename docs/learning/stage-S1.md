# S1 学习记录：真实模型闭环

## 1. 本阶段解决的问题

S0 证明人可以用工具手动修复样例。S1 首次让真实模型读取仓库、选择工具、生成补丁、运行测试并给出结论。模型配置从项目根目录 `.env` 读取；真实密钥没有进入测试进程、报告或 Git 跟踪。

DeepSeek 的纯文本请求先返回 `OK`，但 agent 首轮工具请求报 HTTP 422：服务端不接受 `developer` 消息角色。将内部 `developer` 消息序列化为 Chat Completions 支持的 `system` 角色后，三个真实修复均通过。

## 2. 数据流、状态流与关键文件

`ModelConfig.from_env()` 读取 `.env`，`ModelClient.complete()` 把消息和工具 schema 发给模型。模型返回的工具调用经 `ToolRegistry` 参数校验后执行；工具结果再交回 agent。补丁后必须重新运行测试，旧的通过结果会作废。

- `codepilot/schemas.py`：把内部 `developer` 角色映射为 API 的 `system`。
- `codepilot/model.py`：OpenAI 兼容请求、工具调用解析和带脱敏的模型错误信息。
- `codepilot/agent.py`：推理、工具调用、观测和状态判定循环。
- `codepilot/tools/registry.py`、`codepilot/tools/edit.py`、`codepilot/tools/execute.py`：参数验证、精确文本替换和 pytest 运行。
- `evals/live_runner.py`：从干净 fixture 启动真实模型评测，保存 JSON、CSV、轨迹和测试日志。
- `reports/live-model-20261019-s1-verified/`：本阶段三项真实模型结果及测试证据。

## 3. 设计取舍

- 保留现有显式 agent loop 和 OpenAI 兼容 SDK；没有引入新框架。
- 修复 API 边界的角色序列化，不改 agent 内部消息语义。
- 报告补丁 SHA-256，并在 agent 自己的测试后独立重跑可见与隐藏测试。
- 主机测试只允许用于受信任的 fixture，并要求显式 `--approve-host-tests`。模型 key 不传给 pytest。
- 容器守护进程连接错误标记为 `execution`，不能误记成代码测试失败。
- API 错误保留类型和 HTTP 状态，同时脱敏 key；不把原始配置写入轨迹。

## 4. 失败路径与错误传递

1. API 不支持 `developer`：服务端返回 422。最初 agent 将它包装为笼统的 `model request failed`；探测请求定位到角色问题，修复序列化后通过真实工具调用验证。
2. Token 预算过低：三个补丁与测试已成功，但 7,000 token 预算在最终总结前触发 `budget_exceeded`。将实验预算设为 15,000 后，模型完成总结，任务返回 `success`。
3. Docker daemon：当前 Codex 进程不能读取 Docker Desktop 用户配置和命名管道。该失败现已归类为执行错误；本阶段在隔离的临时 fixture 副本上用本机 pytest 验证，并在结果中记录 `execution=host`。

## 5. 命令与验收证据

真实模型配置：`deepseek-v4-flash`，`https://api.deepseek.com`；直接最小请求返回 `OK`，报告 35 输入、13 输出 token。API temperature 参数未发送，因此结果写明服务端默认值未知。

三项独立任务都从失败基线启动。agent 可见测试、独立可见测试和隐藏测试均通过：

| 案例 | Agent 状态 | 步数 | Token | 补丁 SHA-256 前缀 |
|---|---:|---:|---:|---|
| `parse-config` | success | 6 | 11,308 | `c729f6ff000bd533` |
| `parse-port` | success | 6 | 9,859 | `edb72bd08f2a6bd5` |
| `timeout-config` | success | 6 | 8,693 | `8f94c7e47363e81f` |

命令：`python -m evals.live_runner --execution host --approve-host-tests --output-root reports/live-model-run --work-root .tmp/live-model-run`

本轮三案证据：`reports/live-model-20261019-s1-verified/results.csv`、每案 JSON、`test-logs/` 和对应 JSONL 轨迹。新增 runner 另以 parse-config 冒烟运行，结果 `1/1 accepted`，产物位于 `reports/live-model-20261019-s1-runner-smoke/`。测试命令：`D:\Anaconda3\envs\NN\python.exe -m pytest -q`，结果 **45 passed**；`python -m evals.live_runner --help` 和 `git diff --check` 也通过。

## 6. 10–20 分钟动手实验

1. 运行上述 live runner 命令，使用三个默认案例。
2. 打开 `results.csv`，确认模型、状态、步数、token 和补丁哈希。
3. 打开一个案例的 JSONL 轨迹，按顺序找 `model_finished`、工具调用和 `run_finished`。
4. 打开 `test-logs/parse-config.txt`，对比基线失败、修复后可见测试和隐藏测试。
5. 将 `--case-ids` 改为 `clamp-boundary`，观察同一模型是否能处理另一个边界案例。

预期现象：基线 pytest 失败；模型调用 `search_code`、`read_file`、`apply_patch`、`run_tests`，最后报告测试通过。若遇到 API 422，检查消息角色或参数兼容；若是 `budget_exceeded`，看累计 token 与最终轨迹，不要把它记作修复成功。

## 7. 面试追问

**为什么 developer 被映射成 system？** DeepSeek 的 Chat Completions 接口拒绝 `developer` 角色。映射只发生在 API 序列化边界，内部状态仍保留开发者指令语义。

**为什么模型说修好了还要再测？** 只有工具返回的测试结果能证明补丁有效。补丁一旦改变，旧测试结果立即失效；本阶段还独立重跑了可见和隐藏测试。

**补丁哈希证明了什么？** 它绑定结果报告到具体 diff 内容，方便比对复现；它不证明补丁正确或沙箱安全。

## 8. 尚未实现的边界

只实测了三个固定 fixture，没有达到项目原计划的完整稳定性评测。Docker 隔离路径未能在当前 agent 进程实测；host 模式仅用于受信任测试样例。还没有重复试验、成本估算、自动重试、checkpoint 恢复或生产级沙箱。评测结果不能外推为一般仓库的修复成功率。

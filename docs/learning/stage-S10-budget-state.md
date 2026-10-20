# S10：默认预算与状态转移

## 本阶段目标

让每个 CodePilot 任务默认有明确 token 上限，并集中约束暂停、继续和终态转移。

## 实现

- `Task.max_total_tokens` 与 CLI `--max-tokens` 默认 40,000；调用方仍可显式覆盖。
- `AgentState.transition()` 是 Agent 主循环的状态写入口。
- 正常运行可进入成功、失败、超时、预算耗尽、等待审批、等待用户或步数上限。
- `needs_approval` 和 `needs_user_input` 可恢复到 `running`；终态不可恢复或改写。

## 边界

此转换图限制 Agent 主循环，不代表所有外层持久化流程都自动恢复。模型请求中断且无响应时仍禁止盲目重发。

## 验收

新增测试覆盖默认 token 预算、暂停恢复及终态恢复拒绝；完整测试集验证既有审批流程。

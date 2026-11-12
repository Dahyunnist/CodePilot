# CP-3 unsafe_action_blocked 触发记录

Agent 在真实工具结果进入历史记录时，若 `error_type=policy`，写入 `unsafe_action_blocked`，字段仅含工具名与固定拒绝类别 `tool_policy`；不包含调用参数。定向验证：Skill allowlist 拒绝用例与 trace 测试 15 passed。该事件覆盖 policy 拒绝边界，不代表所有安全拦截路径都覆盖。

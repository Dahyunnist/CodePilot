# 共享 Trace 事件约定

`StandardTraceEvent` 定义 timeout、retry、budget_exceeded、unsafe_action_blocked、cancel、checkpoint_resume 六类标准事件。`validate_event_name` 校验名称格式，同时保留既有历史事件名兼容。JSONL 继续写 run_id/trace_id/span_id；字段脱敏逻辑不变。

`tests/test_tracing.py`：14 passed，含六类事件、旧事件兼容、非法名称拒绝与敏感字段脱敏。标准事件定义不表示每条执行路径都已产生该事件。

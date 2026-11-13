# CP-3 Trace 回放离线切片（2026-11-13）

新增 JSONL 顺序回放回归：模型响应后记录工具开始/结束；timeout 作为失败结果保留；下一轮重试后，越界 patch 被 `PathPolicyError` 拒绝；敏感 token 不进入 trace。现有 Agent 注入测试另行真实调用 `read_file` 与 `apply_patch`，断言外部写入未发生且 trace 保留拒绝类型。

运行：

```powershell
python -m pytest tests/test_tracing.py::test_trace_replay_preserves_timeout_retry_rejection_and_redaction_order tests/test_agent.py::test_prompt_injection_cannot_patch_outside_workspace_or_leak_into_trace -q
python -m pytest tests/test_tracing.py tests/test_agent.py -q
```

本切片只验证 scripted/offline trace 和安全拒绝路径；未运行真实模型任务、Docker 或 CP-2 SWE-bench 评测。CP-2 仍未达到真实仓库/模型验收。

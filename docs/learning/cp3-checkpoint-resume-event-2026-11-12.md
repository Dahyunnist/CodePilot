# CP-3 checkpoint_resume 触发点

CLI 仅在 `resume_durable_run` 成功返回 checkpoint 状态后写 `checkpoint_resume`。字段仅含阶段（approval/interrupted_node）和 outcome（waiting_approval/resumed）；不含 workspace 路径、patch 或状态内容。checkpoint 不存在或重复恢复时函数抛错，故不会发 checkpoint_resume；此前的 resume_requested 仍用于诊断请求失败。

未增加 retry/cancel 伪事件：模型 SDK retries 为 0，CLI 无取消接口。验证沿用 TraceLogger JSONL/schema 测试；真实 checkpoint 集成仍由 `tests/test_cli_e2e.py` 覆盖，需原生宿主验证。

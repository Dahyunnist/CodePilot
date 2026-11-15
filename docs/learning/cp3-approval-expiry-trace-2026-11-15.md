# CP-3 审批过期与跨恢复追踪（2026-11-15）

## 路线与现有覆盖

本轮按 2026-10-23 的 CP-3 路线审查；路线记录可在历史提交 `1882b64` 的 `docs/learning/stage-CP3-trace-safety-2026-10-23.md` 查看。它把统一 run/trace/span、脱敏、提示注入、路径边界、补丁变化后的审批失效、重复恢复与超时恢复列为目标，并注明多项安全控制已有回归。

当前代码已有 README/AGENTS 指令注入、`.env`/`.git` 拒读、越界 patch、路径穿越和 symlink 拒绝、审批期间补丁变化失效、重复恢复拒绝、Agent 工具超时终止、模型未知结果不重复请求，以及 timeout→拒绝 patch→后续测试的 JSONL 回放。此次没有复制这些功能或重复造工具。

审查发现一个实际缺口：审批只绑定补丁摘要和测试结果，没有时间期限。若补丁未变，旧 checkpoint 可以无限期等待批准。

## 修复

- 新审批窗口默认有效30分钟。请求时间、截止时间、补丁 SHA、审批 span ID 和父 span ID写入 run-state SQLite；LangGraph 节点重放时复用原记录，不续期、不重复记审批请求。
- 恢复批准时校验持久截止时间。过期时把批准转换为拒绝，写入 `approval_expired`，并以 `approval_expired` 结果结束；不执行恢复后的测试或源仓库写回。
- 通过批准后仍在测试重验结束、实际回写前再检查一次截止时间，避免长时间测试跨过期限后仍写入。
- 缺失、格式错误、无时区的截止时间，或审批记录与 checkpoint 补丁 SHA 不匹配时，拒绝批准。
- 审批请求与决定复用 JSONL 的逻辑 span ID/父 span ID。跨进程恢复没有旧进程的 OTel span 对象时，导出独立决定 span，并用 `codepilot.approval_span_id` 与原审批关联。Trace 仍不记录补丁正文、测试输出或源代码。
- CLI 待审批报告显示 UTC 截止时间。

## 离线验证

`tests/test_run_graph.py` 用固定模型结果、Git 差异和测试器替身验证：过期批准不写回；有效批准会重验并只写回一次；完成后重复恢复被拒；run→model→tool→patch→test→approval 的 JSONL span 父链与脱敏字段正确；待审批输出含截止时间。`tests/test_tracing.py` 覆盖重启后的 OTel 决定 span 关联。

同组还复跑既有 prompt injection、路径穿越/symlink、未知模型结果恢复和工具超时测试。结果：**30 passed，1 skipped**。唯一 skip 是 Windows junction 创建权限不足。没有真实模型、Docker 或 OTel collector 调用。

另尝试宿主 CLI 写回 E2E，但临时 Git 仓库初始化在本机 Git/MSYS 子进程失败，错误为 `NtCreateDirectoryObject(...): 0xC0000022`。这些 E2E 不计为通过；新增审批逻辑改由 SQLite checkpoint + mock Git/test runner 的 graph 集成测试覆盖。仍需在普通 Windows PowerShell 复核原 CLI 外部仓库写回 E2E。

```powershell
python -m pytest tests/test_tracing.py tests/test_run_graph.py tests/test_agent.py::test_prompt_injection_cannot_patch_outside_workspace_or_leak_into_trace tests/test_agent.py::test_agents_instruction_cannot_read_env_but_safe_repair_completes tests/test_agent.py::test_git_internal_path_injection_is_denied_and_safe_repair_still_succeeds tests/test_agent.py::test_resume_does_not_repeat_request_with_unknown_outcome tests/test_agent.py::test_agent_maps_tool_timeout_to_timeout_status tests/test_repository_tools.py::test_rejects_path_traversal_and_secrets tests/test_repository_tools.py::test_symlink_cannot_escape_repository -q --basetemp="$env:TEMP\cp3-offline"
```

CP-2 真实模型评测仍受 provider 累计用量和余额证据阻断。本轮仅离线验证 CP-3；不表示 CP-2 完成。

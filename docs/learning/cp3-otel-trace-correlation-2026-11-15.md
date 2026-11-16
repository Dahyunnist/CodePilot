# CP-3 OTel trace 关联 ID 回归（2026-11-15）

## 审计结论

路径越界/符号链接、工具输出不可信提示、常见凭证脱敏、审批变更失效和重复回写已有单元或 CLI 用例。本轮发现 OTel 关联缺口：JSONL 使用调用方 `trace_id`，但 OTel run/model/tool/writeback spans 只记录 `run_id`；自定义 trace ID 没有进入这些 spans 的属性。Patch span 已单独带 `codepilot.trace_id`，其他 span 缺失，无法用同一关联值从 JSONL 查到 OTel。

先加 `tests/test_tracing.py::test_otel_span_chain_carries_custom_trace_identity`，修改前失败：run/model/tool spans 中没有 `codepilot.trace_id=trace-cp3`。

## 最小修复与复核

在 OTel run、model、tool、writeback spans 增加 `codepilot.trace_id` 属性。保留 OTel 原生 trace/span 父子关系；该属性用于与 JSONL 自定义 ID 关联。没有改 JSONL schema，也没有设置无效或非标准 OTel trace ID。

验证结果：

- `tests/test_tracing.py`：**19 passed**。
- prompt injection、越界路径、内部路径与秘密读取：**5 passed**；Windows junction 用例 **1 skipped**（创建权限不足）。
- 三个审批/恢复 CLI E2E：受限沙箱首跑遇 MSYS `NtCreateDirectoryObject(...): 0xC0000022`，并非业务断言；原生宿主复跑 **3 passed in 8.70s**。

无 Docker、模型或 hidden gold 调用。测试使用 fake model、合成文件与临时 Git 仓库。没有真实 OTel collector 的端到端导出证据，也没有调用外部模型。

## 运行命令

```powershell
python -m pytest -p no:cacheprovider tests/test_tracing.py -q
python -m pytest -p no:cacheprovider tests/test_agent.py::test_readme_injection_denies_secret_read_without_blocking_safe_repair tests/test_agent.py::test_prompt_injection_cannot_patch_outside_workspace_or_leak_into_trace tests/test_agent.py::test_agents_instruction_cannot_read_env_but_safe_repair_completes tests/test_agent.py::test_git_internal_path_injection_is_denied_and_safe_patch_still_succeeds tests/test_repository_tools.py::test_rejects_path_traversal_and_secrets tests/test_repository_tools.py::test_symlink_cannot_escape_repository -q
python -m pytest -p no:cacheprovider tests/test_cli_e2e.py::test_cli_rejects_writeback_after_restart tests/test_cli_e2e.py::test_cli_invalidates_approval_if_patch_changes_while_paused tests/test_cli_e2e.py::test_cli_revalidates_tests_after_writeback_approval_resume -q --basetemp .tmp\cp3-approval-native
```

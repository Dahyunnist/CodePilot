# CP-3 学习记录：测试 span 父链

新增 `test_test_tool_span_parent_links_to_model_span`：检查 run_tests 的工具 span 以触发它的模型 span 为父级，并确认 tool_started/tool_finished 共享 span ID。

验证：新测试 1 passed；`tests/test_tracing.py` 6 passed。CLI 外部仓库回写 trace 测试仍受 CodexSandbox 的 Git for Windows/MSYS 子进程权限限制，错误为 `NtCreateDirectoryObject(...): 0xC0000022`，随后无法读取仓库。未将该项记为通过。测试须用 `--basetemp=.tmp\\pytest-basetemp` 避免沙箱默认临时目录错误。

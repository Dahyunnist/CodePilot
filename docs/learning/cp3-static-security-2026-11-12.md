# CP-3 独立安全负例补充

新增纯内存测试：恶意 tool-output 文本保持不可信且普通修复指令仍在 prompt；审批 checkpoint 不可直接跳到 success，必须经过 running/decision。

定向测试 2 passed。既有安全组结果仍为 20 passed、2 failed、1 skipped；两失败是 Codex MSYS clone `0xC0000022`，junction 因权限 skip。未将 host-only 失败改为 skip。原生 Windows PowerShell 全套命令：`conda activate NN; Set-Location E:\job\codepilot-lite\.tmp\release-safe; python -m pytest -q --basetemp=.tmp\pytest-native`。Host-only 门槛：WorkspaceManager Git clone、symlink/junction 能力、Docker E2E；需在原生宿主分别验证。

## CP-3 收尾测试复核（2026-11-12）

本机 Codex 环境安全独立组：`test_prompts.py test_state_transitions.py test_repository_tools.py test_execute.py test_tracing.py` 为 45 passed、1 skipped；唯一 skip 是 junction 创建 Access denied。`test_workspace.py` 为 3 passed、2 failed；两失败均因 `Git for Windows/MSYS NtCreateDirectoryObject(...): 0xC0000022`，不是改写为 skip。用户普通 PowerShell 已验证 CLI E2E 单项通过；Workspace clone 的宿主原生验证仍需运行。

全套 pytest 再次约 33% 后长时间无输出，工具未返回汇总；不能报告全套通过或精确总数。CP4 准备项：技能 schema v1 与 deterministic fixture 已有；真实技能消融、费用账本及当前余额仍缺。Docker、junction、Workspace Git clone 是 host-only 集成门槛。

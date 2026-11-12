# CP-3 独立安全负例补充

新增纯内存测试：恶意 tool-output 文本保持不可信且普通修复指令仍在 prompt；审批 checkpoint 不可直接跳到 success，必须经过 running/decision。

定向测试 2 passed。既有安全组结果仍为 20 passed、2 failed、1 skipped；两失败是 Codex MSYS clone `0xC0000022`，junction 因权限 skip。未将 host-only 失败改为 skip。原生 Windows PowerShell 全套命令：`conda activate NN; Set-Location E:\job\codepilot-lite\.tmp\release-safe; python -m pytest -q --basetemp=.tmp\pytest-native`。Host-only 门槛：WorkspaceManager Git clone、symlink/junction 能力、Docker E2E；需在原生宿主分别验证。

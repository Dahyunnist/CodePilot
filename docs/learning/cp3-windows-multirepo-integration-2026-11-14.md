# CP-3 Windows 多仓库集成小闭环（2026-11-14）

## 验收范围

用两个互不重叠的合成仓库验证 `ToolRegistry` 根目录隔离；再运行 CLI 的 scripted-model 修复与外部仓库审批回写集成测试。测试模型是确定性假模型，不发 API 请求。样例数据由测试临时夹具生成，不接触工作树临时目录、`.env` 或外部真实仓库。

定向命令：

```powershell
D:\Anaconda3\envs\NN\python.exe -m pytest -p no:cacheprovider tests/test_repository_tools.py::test_tool_registries_keep_two_repository_roots_isolated tests/test_cli_e2e.py::test_cli_repairs_demo_repository tests/test_cli_e2e.py::test_cli_can_apply_successful_patch_to_external_repository -q
```

`test_tool_registries_keep_two_repository_roots_isolated` 为 repo A、repo B 各建独立 `ToolRegistry`。A 对 `../repo-b/secret.py` 的读取须得到 `PathPolicyError`；B 仍可读取自己的文件。

两项 CLI 测试覆盖 scripted 模型的 read/search/test/patch/diff 流程，以及外部仓库先等待回写审批、批准后再应用补丁和复测。它们只验证单机临时合成仓库，不证明公司多仓库工作区、子模块、monorepo、并发写回或真实模型修复表现。

## 结果

- 普通 Windows 宿主运行：**3 passed, 8.78s**，退出码 0。命令使用 NN 环境与短 basetemp `E:\job\cp3-host-validation-native`。
- 主对话通过 `require_escalated` 在普通 Windows 宿主执行：`D:\Anaconda3\envs\NN\python.exe -m pytest -p no:cacheprovider --basetemp <本次唯一的 E:\job 子目录> tests/test_repository_tools.py -q`，**10 passed**。执行命令创建并使用该专用临时目录，验证路径后清理；本轮未重跑。
- Codex 沙箱对照：长 pytest 临时路径先触发 Windows `Filename too long`；改短路径后，repo 边界测试通过，但两项 CLI 子进程因 Git for Windows/MSYS `NtCreateDirectoryObject(...): 0xC0000022` 失败。普通宿主复测后通过，表明该次失败属于沙箱子进程限制；不据此修改产品代码。
- 样例由假模型驱动，模型请求数为 0。未运行 Docker 或真实模型。

`tests/test_repository_tools.py` 的 10 项只证明仓库工具路径策略与文件边界。它不证明 Agent 已在多个真实仓库完成修复，也不代表真实模型修复成功率或完整 CP-3 验收。

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

## CP-3 共享宿主短路径复测（2026-11-15）

用户在共享 `E:\job` 根 PowerShell 对 `tests/test_cli_e2e.py::test_cli_repairs_demo_repository` 做独立复测。使用全新短 basetemp 和进程级 `safe.directory` 配置；测试仍为 **1 failed，5.37s**。首要错误来自 Git for Windows `sh.exe`：`NtCreateDirectoryObject(...): 0xC0000022`。随后 `model.requests` 为空导致 `IndexError`，是 CLI 未进入模型流程后的次生断言失败，不是 API 错误。

该测试注入 `RepairScriptModel`，未请求模型 API。用户确认短 basetemp 已清理；本次未访问 `.tmp/` 或 `verification-artifacts/`。短路径没有消除问题，故不再归因于路径长度；进程级 `safe.directory` 也未解决 Git 子进程启动限制。此结果来自用户在共享宿主运行，独立于此前沙箱中的失败。未改测试或产品逻辑。

## Windows CI 复核入口（2026-11-15）

新增 `.github/workflows/windows-offline-regression.yml`，在 `windows-latest` 跑 CLI E2E、Workspace、repository tools、MCP、Agent、模型适配器和执行器测试。测试用例注入 scripted/fake model；没有模型 API 测试或真实外部服务请求。唯一排除项 `test_cp2_django_visible_preflight_hashes_and_docker_command_are_isolated` 会读取仓库 `.tmp/`；其余相关测试保留原断言。

Workflow 为每次运行创建新的 `$RUNNER_TEMP` basetemp，结束后清理；Git `safe.directory` 通过该步骤的进程环境变量注入并恢复，不改全局配置。当前尚未在 GitHub Actions 执行：本地普通 PowerShell 短路径复测仍被 Git for Windows 的 `NtCreateDirectoryObject(...): 0xC0000022` 阻断，因此不记录 Windows CI 通过。提交后需由用户推送或在 GitHub 手动触发 workflow 才能取得托管 Windows runner 结果。

本代理按 workflow 范围在当前宿主复测：

- `tests/test_cli_e2e.py`：**1 passed, 1 failed in 5.53s**。`test_cli_repairs_demo_repository` 的次生断言是 `model.requests` 为空；stderr 的首因仍为 Git for Windows `sh.exe` `NtCreateDirectoryObject(...): 0xC0000022`。
- `tests/test_workspace.py -vv -x`：**1 failed in 0.83s**。首测 `test_workspace_is_a_clean_clone_of_committed_state` 在 `WorkspaceManager.prepare()` 的 `git clone` 返回错误；栈终点 `codepilot/workspace.py:73`，同一 `NtCreateDirectoryObject(...): 0xC0000022`，后跟 `fatal: Could not read from remote repository.`。
- MCP 首测 `test_mcp_lists_only_allowlisted_tools_and_exposes_schema` 单独运行超过 20 秒，无 pytest 结果；已中断，当前不能判为通过或失败。没有发现模型/API 调用证据。
- workflow 范围和其余离线单元组也各尝试过一次；两组都超过 90 秒无汇总，被中断。它们不计通过，临时 basetemp 均已清理。

这些栈把 CLI 与 Workspace 的失败定位到 Git for Windows 启动其 `sh.exe` 子进程，不是 Agent 断言，也不是模型请求。MCP 的本机挂起原因尚未定位。Windows GitHub Actions 尚未运行，不能据此判断托管 runner 是否受同一宿主限制。不得把本机中断记录为通过；workflow 设有 20 分钟 job 超时。

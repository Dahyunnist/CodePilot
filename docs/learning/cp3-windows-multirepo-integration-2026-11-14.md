# CP-3 Windows 多仓库集成小闭环（2026-11-14）

## 验收范围

用两个互不重叠的合成仓库验证 `ToolRegistry` 根目录隔离；再运行 CLI 的 scripted-model 修复与外部仓库审批回写集成测试。测试模型是确定性假模型，不发 API 请求。样例数据由测试临时夹具生成，不接触工作树临时目录、`.env` 或外部真实仓库。

定向命令：

```powershell
python -m pytest -p no:cacheprovider tests/test_repository_tools.py::test_tool_registries_keep_two_repository_roots_isolated tests/test_cli_e2e.py::test_cli_repairs_demo_repository tests/test_cli_e2e.py::test_cli_can_apply_successful_patch_to_external_repository -q
```

`test_tool_registries_keep_two_repository_roots_isolated` 为 repo A、repo B 各建独立 `ToolRegistry`。A 对 `../repo-b/secret.py` 的读取须得到 `PathPolicyError`；B 仍可读取自己的文件。

两项 CLI 测试覆盖 scripted 模型的 read/search/test/patch/diff 流程，以及外部仓库先等待回写审批、批准后再应用补丁和复测。它们只验证单机临时合成仓库，不证明公司多仓库工作区、子模块、monorepo、并发写回或真实模型修复表现。

## 结果

- 普通 Windows 宿主运行：**3 passed, 8.78s**，退出码 0。命令使用 NN 环境与短 basetemp `.tmp\cp3-host-validation-native`。
- 主对话通过 `require_escalated` 在普通 Windows 宿主执行：`python -m pytest -p no:cacheprovider --basetemp $env:TEMP\cp3-validation tests/test_repository_tools.py -q`，**10 passed**。执行命令创建并使用该专用临时目录，验证路径后清理；本轮未重跑。
- Codex 沙箱对照：长 pytest 临时路径先触发 Windows `Filename too long`；改短路径后，repo 边界测试通过，但两项 CLI 子进程因 Git for Windows/MSYS `NtCreateDirectoryObject(...): 0xC0000022` 失败。普通宿主复测后通过，表明该次失败属于沙箱子进程限制；不据此修改产品代码。
- 样例由假模型驱动，模型请求数为 0。未运行 Docker 或真实模型。

`tests/test_repository_tools.py` 的 10 项只证明仓库工具路径策略与文件边界。它不证明 Agent 已在多个真实仓库完成修复，也不代表真实模型修复成功率或完整 CP-3 验收。

## CP-3 共享宿主短路径复测（2026-11-15）

用户在共享 `<WORKSPACE_PATH>` 根 PowerShell 对 `tests/test_cli_e2e.py::test_cli_repairs_demo_repository` 做独立复测。使用全新短 basetemp 和进程级 `safe.directory` 配置；测试仍为 **1 failed，5.37s**。首要错误来自 Git for Windows `sh.exe`：`NtCreateDirectoryObject(...): 0xC0000022`。随后 `model.requests` 为空导致 `IndexError`，是 CLI 未进入模型流程后的次生断言失败，不是 API 错误。

该测试注入 `RepairScriptModel`，未请求模型 API。用户确认短 basetemp 已清理；本次未访问 `.tmp/` 或 `verification-artifacts/`。短路径没有消除问题，故不再归因于路径长度；进程级 `safe.directory` 也未解决 Git 子进程启动限制。此结果来自用户在共享宿主运行，独立于此前沙箱中的失败。未改测试或产品逻辑。

## Windows CI 复核入口（2026-11-15）

新增 `.github/workflows/windows-offline-regression.yml`，在 `windows-latest` 跑 CLI E2E、Workspace、repository tools、MCP、Agent、模型适配器和执行器测试。测试用例注入 scripted/fake model；没有模型 API 测试或真实外部服务请求。唯一排除项 `test_cp2_django_visible_preflight_hashes_and_docker_command_are_isolated` 会读取仓库 `.tmp/`；其余相关测试保留原断言。

Workflow 为每次运行创建新的 `$RUNNER_TEMP` basetemp，结束后清理；Git `safe.directory` 通过该步骤的进程环境变量注入并恢复，不改全局配置。最初提交后尚未有托管运行；后续首次运行及其包发现失败见本节末的 CI 记录。

本代理按 workflow 范围在当前宿主复测：

- `tests/test_cli_e2e.py`：**1 passed, 1 failed in 5.53s**。`test_cli_repairs_demo_repository` 的次生断言是 `model.requests` 为空；stderr 的首因仍为 Git for Windows `sh.exe` `NtCreateDirectoryObject(...): 0xC0000022`。
- `tests/test_workspace.py -vv -x`：**1 failed in 0.83s**。首测 `test_workspace_is_a_clean_clone_of_committed_state` 在 `WorkspaceManager.prepare()` 的 `git clone` 返回错误；栈终点 `codepilot/workspace.py:73`，同一 `NtCreateDirectoryObject(...): 0xC0000022`，后跟 `fatal: Could not read from remote repository.`。
- MCP 首测 `test_mcp_lists_only_allowlisted_tools_and_exposes_schema` 单独运行超过 20 秒，无 pytest 结果；已中断，当前不能判为通过或失败。没有发现模型/API 调用证据。
- workflow 范围和其余离线单元组也各尝试过一次；两组都超过 90 秒无汇总，被中断。它们不计通过，临时 basetemp 均已清理。

这些栈把 CLI 与 Workspace 的失败定位到 Git for Windows 启动其 `sh.exe` 子进程，不是 Agent 断言，也不是模型请求。MCP 的本机挂起原因尚未定位。Windows GitHub Actions 尚未运行，不能据此判断托管 runner 是否受同一宿主限制。不得把本机中断记录为通过；workflow 设有 20 分钟 job 超时。

## Windows CI 包发现修复与复测（2026-11-15）

GitHub Actions 首次运行 [#43670637501](https://github.com/Dahyunnist/CodePilot/actions/runs/43670637501) 在依赖安装步骤失败；Windows runner 报 flat-layout 检出多个顶层包 `evals`、`docker`、`codepilot`，测试步骤被跳过。`pyproject.toml` 现在明确使用 `setuptools.build_meta`，包发现仅包含 `codepilot*`，排除 `evals*`、`docker*`、`tests*`。没有改为非 editable 安装，也没有放宽断言。

首次本机 editable 探测失败，后来在干净源码副本与隔离 Python 3.11 环境中复现并定位：默认 `TEMP`/`TMP` 指向 Codex 沙箱目录 `...\#!sandbox.{GUID}\Temp`；setuptools 72.1.0/79.0.1 在 `install.expand_dirs()` 的 `subst_vars()` 阶段把路径中的 GUID 当成变量名，抛出 `ValueError: invalid variable '<GUID>'`。相同源码和环境将 `TEMP`、`TMP` 改为普通短目录后，wheel 与 editable install 均成功。故这是当前宿主临时路径格式触发的问题，不是包发现配置缺陷；不应为此改包内容或移除 editable 安装。

隔离验收使用 Python 3.11 venv、`--no-deps --no-build-isolation` 和短 `<WORKSPACE_PATH>` 临时目录，不访问模型或外网：wheel 含 26 个 `codepilot/` 文件，没有 `evals/`、`docker/`、`tests/`；`pip install -e .` 成功，`codepilot.__file__` 指向临时源码副本，`codepilot --help` 与 `codepilot-mcp --help` 均退出 0。此前提交的包发现配置已由 GitHub Actions 原始 editable 安装验证通过。

远端 Windows Actions [run 43672009209](https://github.com/Dahyunnist/CodePilot/actions/runs/43672009209)，commit `82e2445`：依赖安装与完整离线回归步骤均成功。它覆盖 CLI E2E、Workspace、repository tools、MCP、Agent、模型适配器及执行器；未运行真实模型。

离线回归结果：Agent、模型适配器、执行器与 repository tools 合并运行，排除唯一会读取 `.tmp/` 的 CP-2 夹具测试后，**96 passed, 1 skipped, 1 deselected in 10.66s**。跳过项是 Windows junction 创建返回 Access denied。CLI/Workspace 在此前本机复测受 Git for Windows `sh.exe` `NtCreateDirectoryObject(...): 0xC0000022` 阻断；CLI 组 **1 passed, 1 failed**，未请求模型。MCP 本机首测曾挂起，未判为通过或失败；托管 Actions 已覆盖并通过这些测试。

验证操作偏差：有一条本机 pytest 命令漏写 workflow 的 CP-2 排除条件，意外触发 `test_cp2_django_visible_preflight_hashes_and_docker_command_are_isolated`。该测试尝试读取 `.tmp/cp2-single-preflight/one-task.json`，文件不存在，返回 `FileNotFoundError`；没有读到内容或写入文件。后续回归命令已明确排除此测试。此次属于指令偏差，不能记作该测试通过。

当前 editable 包发现、GitHub 托管 Windows 回归已通过。Codex 宿主默认 `TEMP`/`TMP` 路径下的本机 editable 构建仍会复现 setuptools GUID 错误；本机需先设置普通短临时路径。CLI/Workspace 在当前受限宿主的 Git `sh.exe` 权限问题和 MCP 本机挂起记录仍保留，Actions 成功不替代对其他宿主的复核。

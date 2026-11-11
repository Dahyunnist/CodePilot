# 升级路线审计（2026-11-11）

| 阶段 | 状态 | 仓库证据 | 缺口 |
|---|---|---|---|
| CP-1 | 部分 | `README.md`、`docs/DEMO_5MIN_CN.md`；现有测试含 `tests/test_agent.py`、`tests/test_execute.py` | 未逐项对照原方案验收标准；无本轮完整测试证据。 |
| CP-2 | 部分 | `evals/public_cases/` 已有冻结脚本；新增 `evals/public_issues/candidates.json` 与 schema | 3 条外部候选均 pending；许可证、base/fix SHA、可见/隐藏测试命令、容器复现、哈希均未核实。 |
| CP-3 | 未完成 | `docs/architecture.md`、`tests/test_repository_index.py`、`tests/test_context_selector_offline.py` | 未按方案核对完整验收与多仓库证据。 |
| CP-4 | 部分 | `codepilot/`、`tests/test_tracing.py`、`tests/test_live_runner.py` | 未逐字段核对 `run_manifest`/trace 规范；未验证远端证据及完整回放。 |

## 本轮记录

候选登记仅表示待复现，不是正式 benchmark。冻结前需核准许可证与来源 SHA，在 base 上确认可见测试失败、fix 上通过，并验证隐藏测试及 Docker 命令。失败样本保留并注明原因。新增 validator 的 pytest 命令：`python -m pytest tests/test_public_issue_manifest.py -q`；需先安装项目开发依赖 `python -m pip install -e ".[dev]"`。本机 `C:\Python314\python.exe` 缺 pytest；本轮未运行测试，不报告通过。

## 全套测试结果

2026-11-11 使用 D:\Anaconda3\envs\NN\python.exe -m pytest -q：59 passed，143 errors，148.32 秒。错误集中在 Windows 沙箱文件创建/路径权限（OSError），需查看 pytest 完整日志逐类区分环境错误与代码失败；不得将整套测试记为通过。定向 validator 测试此前 4 passed，CLI python -m codepilot --help 通过。

## Windows 沙箱测试边界（2026-11-11）

`git --version` 与标准库 `subprocess.run(['git', '-C', temp, 'init'])` 在当前进程通过；但 pytest 中 CLI E2E 子进程输出 `sh.exe: NtCreateDirectoryObject(...): 0xC0000022`，随后 `fatal: Could not read from remote repository.`，使 `tests/test_cli_e2e.py::test_cli_repairs_demo_repository` 因 `model.requests` 为空失败。该证据指向 CodexSandbox 下 Git for Windows/MSYS 的子进程限制，不足以判定产品缺陷。不要改生产代码规避。

宿主复测：在普通 Windows CMD 激活 NN 环境，进入仓库，运行 `python -m pytest tests/test_cli_e2e.py::test_cli_repairs_demo_repository -vv`。此前使用 pytest basetemp 指向 `.tmp/pytest-basetemp` 可避免临时目录不存在；未完成全套重跑。全套当前可信结果仅为先前 59 passed/143 errors（临时目录缺失因素混杂），后续 `-x` 有 48 passed/1 环境性失败。其余测试集尚未验证。

## 宿主原生 PowerShell 复核补充（用户回报，2026-11-11）

用户在普通 Windows PowerShell 使用 NN 环境复测 `tests/test_cli_e2e.py::test_cli_repairs_demo_repository`，结果 `1 passed in 3.37s`。这补足 Codex MSYS 子进程权限错误不能代表产品缺陷的证据；该单项真实 Git CLI E2E 已在宿主通过。此前 Codex 环境中的 `-x` 结果仍为 50 passed/1 sandbox failure，不替代完整套件。本条为用户提供的运行记录，当前会话未自行复跑。

分支核对：本地 HEAD 与记录的 `origin/publish/safe-source-20261024` 都为 `f3f22e7258b6216e8e1fa41ec35fd3da696e7281`。尚无新提交。CP-2 实际公开仓库 base/fix 实验、CP-1真实任务效果对比、CP-4真实模型配对效果仍未完成；费用账本和当前余额不可核验，继续暂停模型调用。

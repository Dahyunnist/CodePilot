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

2026-11-11 使用 python -m pytest -q：59 passed，143 errors，148.32 秒。错误集中在 Windows 沙箱文件创建/路径权限（OSError），需查看 pytest 完整日志逐类区分环境错误与代码失败；不得将整套测试记为通过。定向 validator 测试此前 4 passed，CLI python -m codepilot --help 通过。

## Windows 沙箱测试边界（2026-11-11）

`git --version` 与标准库 `subprocess.run(['git', '-C', temp, 'init'])` 在当前进程通过；但 pytest 中 CLI E2E 子进程输出 `sh.exe: NtCreateDirectoryObject(...): 0xC0000022`，随后 `fatal: Could not read from remote repository.`，使 `tests/test_cli_e2e.py::test_cli_repairs_demo_repository` 因 `model.requests` 为空失败。该证据指向 CodexSandbox 下 Git for Windows/MSYS 的子进程限制，不足以判定产品缺陷。不要改生产代码规避。

宿主复测：在普通 Windows CMD 激活 NN 环境，进入仓库，运行 `python -m pytest tests/test_cli_e2e.py::test_cli_repairs_demo_repository -vv`。此前使用 pytest basetemp 指向 `.tmp/pytest-basetemp` 可避免临时目录不存在；未完成全套重跑。全套当前可信结果仅为先前 59 passed/143 errors（临时目录缺失因素混杂），后续 `-x` 有 48 passed/1 环境性失败。其余测试集尚未验证。

## 宿主原生 PowerShell 复核补充（用户回报，2026-11-11）

用户在普通 Windows PowerShell 使用 NN 环境复测 `tests/test_cli_e2e.py::test_cli_repairs_demo_repository`，结果 `1 passed in 3.37s`。这补足 Codex MSYS 子进程权限错误不能代表产品缺陷的证据；该单项真实 Git CLI E2E 已在宿主通过。此前 Codex 环境中的 `-x` 结果仍为 50 passed/1 sandbox failure，不替代完整套件。本条为用户提供的运行记录，当前会话未自行复跑。

分支核对：本地 HEAD 与记录的 `origin/publish/safe-source-20261024` 都为 `f3f22e7258b6216e8e1fa41ec35fd3da696e7281`。尚无新提交。CP-2 实际公开仓库 base/fix 实验、CP-1真实任务效果对比、CP-4真实模型配对效果仍未完成；费用账本和当前余额不可核验，继续暂停模型调用。

## 全套测试状态复核（2026-11-12）

全套 `pytest -q --basetemp=.tmp\\pytest-final` 未获得完整终态汇总，运行过程在约 34% 出现多项失败并长时间无输出。限时 `-x` 复现首错：50 passed、1 failed、10.58 秒；失败为 `tests/test_cli_e2e.py::test_cli_repairs_demo_repository`，Codex MSYS 子进程报 `NtCreateDirectoryObject(...): 0xC0000022`。用户随后在原生 Windows PowerShell 报告同一单项 1 passed in 3.37s。因此不能把 Codex 首错视为产品失败，也不能把全套称为通过；仍需原生宿主执行全套。

CP-1 新增 deterministic fixture 定向测试 3 passed。该结果是机制测试，不代表模型修复效果。

## CP-1..CP-4 路线状态更新（2026-11-13）

本节按当前安全发布分支证据更新；历史测试记录保留，不以新提交倒推旧测试结果。

| 阶段 | 当前状态 | 已有离线证据 | 未完成验收 |
|---|---|---|---|
| CP-1 | 部分完成 | 确定性上下文机制、重复证据与同任务配对 fixture；见 `docs/learning/cp1-*.md`。 | 未在真实任务上比较修复质量、上下文效果或成本；fixture 不代表模型效果。 |
| CP-2 | 部分完成 | 候选清单审计、固定 HF revision 与 LFS SHA、20 题本地 freeze/verify；见 `docs/learning/stage-CP2-freeze.md`。 | 尚未完成逐 base commit 许可文件审计、仓库复现、可见/隐藏测试和真实模型评测。 |
| CP-3 | 部分完成 | 静态安全负例、命令策略、trace 与 checkpoint 恢复的定向验证；见 `docs/learning/cp3-*.md`。 | 未完成普通 Windows 宿主上的完整集成验收；多仓库真实任务和外部仓库完整回写仍缺本轮证据。 |
| CP-4 | 部分完成 | 离线技能消融与 schema 边界回归；见 `docs/learning/cp4-*.md`。 | 三仓六次真实模型配对实验未运行；没有成功率、费用或耗时结论。 |

CP-2 历史清单的 `dataset_source_sha256=5cb74f...` 未被重写；它不是当前 Parquet 字节哈希。2026-11-13 用户宿主已提供官方 Parquet，当前本地 freeze 的源 SHA 为 `438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3`，20 题子集 SHA 为 `8fb7c6b9a93a3eaef1d0c55839e8d5420ad222447cac7b247735faf23927941d`。完整边界见 `docs/learning/stage-CP2-freeze.md`。

相关可离线校验：`python -m pytest tests/test_cp2_dataset_fetch.py tests/test_benchmark_manifest_integrity.py tests/test_lite_candidate_audit.py -q`。2026-11-13 执行结果为 8 passed；此测试只验证清单结构、来源固定值和冻结脚本行为，不下载数据、不运行 Agent 或模型。README 中 HF 文件页链接固定到同一完整 revision；真实网络可达性与下载完整性仍需用户执行下载和 SHA 命令后确认。未推送分支。

## CP-2 离线进展补充（2026-11-13）

早期 socket 权限错误和缓存目录未找到记录保留为历史。后续用户在宿主成功下载数据并完成本地 freeze/verify。上下文预算机制已有 `tests/test_agent.py` 的仓库规模缩窗、额度与上下文窗口分离、工具观察截断测试；这些只验证确定性预算/截断行为，不代表 SWE-bench 修复能力或模型效果。模型评测、真实仓库修复实验仍未运行。

## 预算/费用门槛复核（2026-11-13）

CP-1 新增 fail-closed 回归：未来 patch/test/final 保留额度不适配总额度时，Agent 返回 `budget_exceeded`/`budget`，且模型调用列表为空。上下文预算仍只由离线机制测试证明；没有真实模型任务或质量/费用结果。

CP-2 20 题公开数据冻结已完成，但独立仓库构建、baseline、visible/hidden evaluator 尚未跑。当前工作区未确认可用密钥、余额或成本账本，因此不调用模型。CP-4 manifest 的历史授权上限为 6 次 × $0.06 = $0.36（低于 $0.50 总上限），但该上限不证明当前余额足够，也不自动授权本轮运行；其物化/基线预检仍 pending。禁止把已有公开题称作 blind holdout。

阶段状态：CP-1 部分完成；CP-2 数据冻结完成但真实基准未完成；CP-3 离线追踪、安全与恢复回归部分完成；CP-4 离线 schema/技能用例部分完成，真实模型配对未运行。可行下一步：在宿主完成单仓库 visible-only Docker preflight；随后确认独立评测预算授权和当前余额，再启动一次受限模型 pilot。

## ContextSelector 去重契约（2026-11-13）

新增回归固定重复 SHA 压缩行为：旧证据替换为 SHA 指针，最新证据原文保留。现有实现已满足，不需改生产代码。该切片不证明真实任务质量提升。

CP-3 项目指令注入回归：AGENTS.md 要求读取 `.env` 时，真实 Agent/ToolRegistry 行为测试确认路径拒绝、key 不进 trace/模型消息，且合法补丁与可见测试仍成功。

CP-2 候选集只读元数据审计：20/20 均 pending，缺 issue、fix SHA、可见/隐藏命令及 base 许可证证据；独立 validator 禁止被标 runnable。冻结不等于真实仓库可复现。

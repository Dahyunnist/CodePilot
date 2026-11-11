# 升级路线审计（2026-11-11）

| 阶段 | 状态 | 仓库证据 | 缺口 |
|---|---|---|---|
| CP-1 | 部分 | `README.md`、`docs/DEMO_5MIN_CN.md`；现有测试含 `tests/test_agent.py`、`tests/test_execute.py` | 未逐项对照原方案验收标准；无本轮完整测试证据。 |
| CP-2 | 部分 | `evals/public_cases/` 已有冻结脚本；新增 `evals/public_issues/candidates.json` 与 schema | 3 条外部候选均 pending；许可证、base/fix SHA、可见/隐藏测试命令、容器复现、哈希均未核实。 |
| CP-3 | 未完成 | `docs/architecture.md`、`tests/test_repository_index.py`、`tests/test_context_selector_offline.py` | 未按方案核对完整验收与多仓库证据。 |
| CP-4 | 部分 | `codepilot/`、`tests/test_tracing.py`、`tests/test_live_runner.py` | 未逐字段核对 `run_manifest`/trace 规范；未验证远端证据及完整回放。 |

## 本轮记录

候选登记仅表示待复现，不是正式 benchmark。冻结前需核准许可证与来源 SHA，在 base 上确认可见测试失败、fix 上通过，并验证隐藏测试及 Docker 命令。失败样本保留并注明原因。新增 validator 的 pytest 命令：`python -m pytest tests/test_public_issue_manifest.py -q`；需先安装项目开发依赖 `python -m pip install -e ".[dev]"`。本机 `C:\Python314\python.exe` 缺 pytest；本轮未运行测试，不报告通过。

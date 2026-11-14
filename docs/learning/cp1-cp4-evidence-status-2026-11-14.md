# CP-1 至 CP-4 证据状态与 CP-1 历史配对审计（2026-11-14）

## 阶段状态

| 阶段 | 代码/评测入口 | 可复核证据 | 尚缺验收 |
|---|---|---|---|
| CP-1 上下文预算 | `codepilot/agent.py`、`codepilot/context_selector.py`；`evals/context_selector_offline.py` | 机制 fixture 比较同一字符计数器；历史 `reports/cp1-selector-pair/` 有 2 个同任务双配置结果。定向机制测试 8 passed。 | 两份历史 pair 都未通过任务验收；token 上限及 selector 版本未完整冻结。尚无可支持普遍效果结论的配对样本。 |
| CP-2 真实仓库 benchmark | `evals/cp2_benchmark.py`、`benchmark-v1.json` | 15 个开发集任务、5 个仓库；gold 仅留 SHA；visible-only runner 和预算 gate 有契约测试。 | 15/15 可见测试未物化/基线验证；xarray-4493 缺本机镜像 digest；预算账本未与供应商累计用量对账。整个集合 fail closed。 |
| CP-3 安全与 trace | `codepilot/security.py`、`codepilot/tracing.py`、Agent 负例测试 | 2026-11-13 定向安全组 43 passed；覆盖注入、路径拒绝、凭证脱敏、trace 与安全修复续行。 | 这是确定性/假模型验证；未完成生产 OTLP collector 或真实模型攻击评测。 |
| CP-4 Skill | `codepilot/skills.py`、`evals/skills/ablation.py` | schema/allowlist 的离线测试；消融脚本固定输出 `model_calls=0`。历史模型报告留有若干尝试记录。 | 真实尝试均因预算停止，未得到接受修复；没有可用于比较两个 Skill 成效的成功率结论。 |

## CP-1 两组历史 live pair

两组报告各有 baseline 与 selector 一行；模型、Git SHA、工作区 diff、执行方式、Docker image、任务 metadata hash、技能和主预算字段一致。`compare_runs` 现在可回放旧 manifest：缺失的 `verification_mode` 按旧默认 `full` 解释，并明确报告配置完整性与 selector 版本是否 pin。

| 任务 | baseline token / 成本 / 耗时 | selector token / 成本 / 耗时 | 验收 |
|---|---:|---:|---|
| `django__django-11001` | 22,699 / $0.004217 / 270,278 ms | 19,668 / $0.004598 / 68,213 ms | 两组均 `budget_exceeded`，均未接受；selector 少 3,031 tokens，成本多 $0.000381。 |
| `pydata__xarray-4094` | 18,703 / $0.002825 / 49,902 ms | 22,458 / $0.002451 / 50,752 ms | 两组均 `budget_exceeded`，均未接受；selector 多 3,755 tokens，成本少 $0.000374。 |

两组严格配对比较的 `selector_wins=0`、`baseline_wins=0`、`ties=2`。旧 manifest 没有显式 token-per-request、completion-token、费用预留和 selector 版本字段；结果 `paired_configuration_complete=false`、`context_selector_version_pinned=false`。耗时受单次 API/宿主波动影响，不用于效果结论。该 n=2 描述性记录不能证明 selector 提升或降低成功率。

## 可复现命令与边界

```powershell
python -m pytest -p no:cacheprovider tests/test_live_runner.py::test_paired_comparison_requires_same_cases_and_reports_exact_test tests/test_cp1_context_offline.py tests/test_context_selector_offline.py -q
```

CP-1 离线机制测试：**8 passed**。没有新的模型请求。CP-2 仍 fail closed；未读取、修改或提交 `django_10924/`。

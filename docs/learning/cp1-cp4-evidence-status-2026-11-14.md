# CP-1 至 CP-4 证据状态与 CP-1 历史配对审计（2026-11-14）

## 阶段状态

| 阶段 | 代码/评测入口 | 可复核证据 | 尚缺验收 |
|---|---|---|---|
| CP-1 上下文预算 | `codepilot/agent.py`、`codepilot/context_selector.py`；`evals/context_selector_offline.py` | 预算预留、超长工具输出截断/原因、同 SHA 去重组合回归；适用 Agent/selector/CP1/runner 测试 **86 passed**。学习记录见 `docs/learning/cp1-context-budget-2026-11-11.md`。 | 机制测试使用字符上限与假模型；两份历史 live pair 均 `budget_exceeded`。没有真实任务成功率或 token/cost 收益结论。 |
| CP-2 真实仓库 benchmark | `evals/cp2_benchmark.py`、`benchmark-v1.json` | seaborn-3010 与 seaborn-2848 均有单题 baseline→官方修复可见测试证据；2848 source sidecar 与完整 visible test 文件 SHA 绑定已验证，base 1 failed、fix 1 passed。详见两份 `cp2-seaborn-*-reproduction/preflight` 记录。 | 冻结 v1 不改；仅两题有公开补丁复现证据，未运行 CodePilot Agent/模型或 hidden tests。其余题、账本和 15 题完整验收仍缺。 |
| CP-3 安全与 trace | `codepilot/security.py`、`codepilot/tracing.py`、Agent/CLI/registry 测试 | 新增 OTel spans 携带 JSONL 自定义 trace ID 回归；tracing 19 passed，安全/路径 5 passed，审批恢复宿主 3 passed。详细记录见 `docs/learning/cp3-otel-trace-correlation-2026-11-15.md`。 | 无真实 OTel collector/外部模型攻击或企业多仓任务证据；本轮 Windows junction 权限 skip，受限沙箱 Git E2E 错误需以宿主结果为准。 |
| CP-4 Skill | `codepilot/skills.py`、`evals/skills/ablation.py` | 输入契约、schema/allowlist/预算/退出条件回归 **9 passed**；确定性双 fixture 报告记录在 `docs/learning/cp4-skill-offline-2026-11-15.json`，fixture SHA 已绑定，`model_calls=0`。详见 `docs/learning/cp4-skill-input-contract-offline-2026-11-15.md`。 | 离线演示仅校验约束投影，不是模型行为或修复效果。真实模型尝试因预算停止，未得到接受修复；没有 Skill 成效的成功率、成本或耗时结论。 |

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

## CP-3 并行多仓库与宿主复核更新（2026-11-14）

新增 `tests/test_repository_tools.py::test_concurrent_tool_registries_do_not_mix_repository_results`：两个独立 `ToolRegistry` 通过线程屏障同时读取不同仓库的同名文件，断言结果不串仓。新测与相关工具、Agent 并行顺序及 checkpoint 用例定向组 **4 passed**；扩大组 **12 passed、1 skipped**（Windows junction 创建权限不足）。既有测试还覆盖 CLI 审批后回写、暂停后补丁变化作废、批准后重新验证测试。

本轮宿主组合复核为 **5 passed、2 failed**。两项失败均在临时 Git 仓库 `.git/config` 读取时遇 `Permission denied`，不是 Agent 断言失败。单项复核随后被自动审批器拒绝，未重试。此前宿主原生 CLI 回写组 **3/3 passed**，仓库工具组 **10 passed**；后者由本代理运行并清理临时仓库，不是用户运行。证据均为合成仓库/假模型，不代表真实模型成功率、生产 OTLP 或公司多仓库验收。

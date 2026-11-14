# CP-1 至 CP-4 证据状态与 CP-1 历史配对审计（2026-11-14）

## 阶段状态

| 阶段 | 代码/评测入口 | 可复核证据 | 尚缺验收 |
|---|---|---|---|
| CP-1 上下文预算 | `codepilot/agent.py`、`codepilot/context_selector.py`；`evals/context_selector_offline.py` | 机制 fixture 比较同一字符计数器；历史 `reports/cp1-selector-pair/` 有 2 个同任务双配置结果。定向机制测试 8 passed。 | 两份历史 pair 都未通过任务验收；token 上限及 selector 版本未完整冻结。尚无可支持普遍效果结论的配对样本。 |
| CP-2 真实仓库 benchmark | `evals/cp2_benchmark.py`、`benchmark-v1.json` | 15 题元数据；公开切片已有 base/fix 证据。seaborn-3010 新增单题证据：镜像 digest、base 父提交、BSD-3-Clause 许可证核对通过，公开 PR 测试逻辑在 base 复现预期缺陷；详见 `docs/learning/cp2-seaborn-3010-baseline-preflight-2026-11-14.md`。 | 冻结 v1 状态/hash 不变；base 镜像自带测试未包含 `test_missing_data`，原选择器退出 5，新增公开测试逻辑仅在临时容器路径复现。修复后验收、15 题完整 visible baseline、账本余额和 Agent 修复验收仍缺。 |
| CP-3 安全与 trace | `codepilot/security.py`、`codepilot/tracing.py`、Agent/CLI/registry 测试 | 安全负例、trace/checkpoint；Agent 并行调用与顺序结果；双仓 registry 隔离及新增并发隔离回归。此前宿主 CLI 外部仓库流程 3/3、registry 测试 10 passed。 | 本轮组合宿主复核 5 passed、2 failed；两项失败在 Git 读取 `.git/config` 时遇权限拒绝，不能归因产品。重跑遭自动审批器拒绝。尚无生产 OTLP、真实模型攻击或真实公司多仓任务。 |
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

## CP-3 并行多仓库与宿主复核更新（2026-11-14）

新增 `tests/test_repository_tools.py::test_concurrent_tool_registries_do_not_mix_repository_results`：两个独立 `ToolRegistry` 通过线程屏障同时读取不同仓库的同名文件，断言结果不串仓。新测与相关工具、Agent 并行顺序及 checkpoint 用例定向组 **4 passed**；扩大组 **12 passed、1 skipped**（Windows junction 创建权限不足）。既有测试还覆盖 CLI 审批后回写、暂停后补丁变化作废、批准后重新验证测试。

本轮宿主组合复核为 **5 passed、2 failed**。两项失败均在临时 Git 仓库 `.git/config` 读取时遇 `Permission denied`，不是 Agent 断言失败。单项复核随后被自动审批器拒绝，未重试。此前宿主原生 CLI 回写组 **3/3 passed**，仓库工具组 **10 passed**；后者由本代理运行并清理临时仓库，不是用户运行。证据均为合成仓库/假模型，不代表真实模型成功率、生产 OTLP 或公司多仓库验收。

# CP-4 Skill 输入契约与离线验收（2026-11-15）

## 目的

为两个内置修复 Skill 明确调用方应提供的信息，并把输入契约纳入模型提示和离线评测报告。此改动不扩大工具权限，也不声称提升模型修复率。

## Skill 契约

| Skill | 必需输入 | 可选输入 | 工具与限制 |
|---|---|---|---|
| `pytest-failure-triage` | 任务/失败描述、目标仓库、pytest 命令 | 已有失败日志 | 只可调用 Skill 白名单工具；最多 10 步、3 次测试尝试、18,000 tokens；测试全通过才可报告完成。 |
| `api-contract-check` | API 行为或兼容性目标、目标仓库、相关测试命令 | 接口入口、schema、调用方线索 | 只可调用 Skill 白名单工具；最多 12 步、4 次测试尝试、24,000 tokens；行为不明确时询问，缺少验证条件时停止。 |

Agent 提示现在显式包含输入契约。测试覆盖两个 Skill 的字段、提示呈现、白名单和预算/退出约束。

## 确定性离线对比

运行 `python -m evals.skills.ablation`，读取固定的 `evals/skills/paired-smoke.json`。报告记录输入契约、Skill schema、工具白名单、固定工具轨迹和 fixture SHA。没有发起模型请求：`model_calls=0`。本次 2 个样例均满足白名单约束。

报告：`docs/learning/cp4-skill-offline-2026-11-15.json`。Fixture SHA-256：`d064b30c392fb33c0bdc68b9472182cda07b1b47c7f29171abe079d634396093`。

该 fixture 固定了两组工具选择，启用 Skill 前后工具数量相同。它只能证明约束投影和报告生成可复现，不能证明模型遵循 Skill、修复成功率提高或成本/耗时下降。

## 验证

```powershell
python -m pytest -p no:cacheprovider tests/test_skills.py tests/test_skill_ablation.py -q
python -m evals.skills.ablation
```

结果：**9 passed**；离线报告含 2 个样例，`model_calls=0`。

真实模型配对比较未运行。此前记录的预算上限不等于当前余额或本轮模型调用授权；没有新的费用、成功率、耗时结论。

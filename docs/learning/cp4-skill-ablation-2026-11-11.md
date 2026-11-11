# CP-4 确定性技能消融 fixture

新增 `python -m evals.skills.ablation`，读取既有两个固定案例并输出 JSON：每例列出 no-skill/skill 工具选择、allowlist 约束结果和工具数。输出声明 `deterministic_fixture=true`、`model_calls=0`。两组当前选择相同且均满足约束；这只是脚本化 fixture，不是 LLM 实测，也不证明技能提升。

验证：`python -m pytest tests/test_skill_ablation.py -q --basetemp=.tmp\\pytest-basetemp`，1 passed；CLI 输出样本数 2。

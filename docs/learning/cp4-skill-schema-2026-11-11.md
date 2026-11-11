# CP-4 Skill schema 版本记录

内置两个 RepairSkill 增加 `schema_version=1`。loader 只接受精确整数 1；未知版本和布尔值均拒绝，避免未来 schema 被静默误读。该字段是 Python skill 元数据，不是外部 SKILL.md frontmatter。

验证：`tests/test_skills.py` 5 passed，覆盖现有加载/allowlist和版本 1 接受、版本 2 拒绝。未实现 ablation runner；确定性 fixture 仍不是 LLM 实测。

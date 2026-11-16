# CP-4 Skill schema 版本记录

内置两个 RepairSkill 增加 `schema_version=1`。loader 只接受精确整数 1；未知版本和布尔值均拒绝，避免未来 schema 被静默误读。该字段是 Python skill 元数据，不是外部 SKILL.md frontmatter。

验证：`tests/test_skills.py` 5 passed，覆盖现有加载/allowlist和版本 1 接受、版本 2 拒绝。未实现 ablation runner；确定性 fixture 仍不是 LLM 实测。

## 离线执行契约补充（2026-11-13）

新增真实 Agent/SkillTools 回归：预算仅 1 token 时在模型调用前 fail-closed；模型声称完成但未运行完整测试时，Agent 不返回 success。既有集成用例继续覆盖未知工具被拒、白名单内测试工具可继续完成。此为离线契约行为，不说明 Skill 启用能提升模型成功率或降低成本；真实对照需余额与单独授权，当前仍 blocked。

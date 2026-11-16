# CP-4 技能版本边界回归

S3 检查发现 symlink、敏感文件与 trace 脱敏已有用例；补 CP-4 小边界：Python `bool` 是 `int` 子类，schema_version 必须精确整数 1，避免 `True` 被误认版本 1。新增回归不改业务逻辑。

验证：`tests/test_skills.py` 6 passed。全套 `pytest -x` 在 50 passed 后首个失败为 CLI E2E 的 Git/MSYS `NtCreateDirectoryObject(...): 0xC0000022`；用户曾在原生 PowerShell 验证该 CLI 单项通过。不能称全套通过。

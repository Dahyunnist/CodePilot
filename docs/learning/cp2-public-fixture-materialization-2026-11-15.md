# CP-2 公开夹具物化记录（2026-11-15）

本轮为冻结的 15 个 CP-2 任务准备精确 base 仓库与公开回归测试。每个样例记录上游 commit、Docker image config digest、许可证文件哈希、可见测试 SHA-256 和源码清单 SHA-256。测试补丁来自对应上游公开 PR；未读取 Gold patch、hidden test，不调用模型。

夹具完整性报告：`evals/public_cases/cp2/reports/fixture-integrity-2026-11-15.json`，15/15 通过。完整性检查允许 Python 运行缓存（`__pycache__`、`.pyc`、`.pytest_cache`），仍拒绝其他额外文件及源码哈希变更。

当前证据只说明公开测试在冻结 base 上能复现缺陷，不代表 CodePilot Agent 已修复成功。真实模型预算 smoke 因本机 Docker 镜像预检阻断，不能计为通过；账单门禁仍保持阻断。

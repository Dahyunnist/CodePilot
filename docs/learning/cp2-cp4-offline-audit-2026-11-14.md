# CP-2 / CP-4 离线验收审计（2026-11-14）

## 本轮范围

只核对已提交的 CP-2 benchmark manifest 与 CP-4 pilot manifest；运行静态契约测试和 CP-4 脚本化消融 fixture。没有 API 请求、Docker 仓库构建或隐藏测试。

## CP-2

`evals/public_cases/cp2/benchmark-v1.json` 标记为开发集，包含 15 题、5 个公开仓库。每题冻结题面哈希、base commit、许可证元数据、gold patch SHA-256、可见测试规格和 Docker image digest 状态。14 个 image digest 在本机核验；xarray-4493 镜像缺失。15 题的可见测试仍是规格草案，没有物化或基线验证，因此 runner 必须阻断真实评测。

manifest 配对维度是 ContextSelector 开/关。比较器要求相同模型、运行环境、预算、任务元数据和验证模式。该设计没有产出真实模型成功率，不是 SWE-bench 官方得分。

## CP-4

既有三仓库 Skill pilot 记录仍为待预检。`evals.skills.ablation` 的输出是 `deterministic_fixture=true`、`model_calls=0`；它只能证明离线工具选择/约束 fixture 可运行，不能证明 Skill 提升模型修复率。

预算账本基于本地报告估算，不能与供应商累计 usage 对账。故当前没有足够证据启动真实模型配对；不消耗额外 API 预算。

## 复核

本轮检查 `tests/test_benchmark_manifest_integrity.py` 与 `tests/test_skill_ablation.py`。测试结果及提交 SHA 以工作报告为准。未跟踪的 `django_10924/` 未读取、修改或提交。

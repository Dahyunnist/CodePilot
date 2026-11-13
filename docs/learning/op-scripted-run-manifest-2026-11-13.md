# Scripted 评测运行清单（2026-11-13）

`evals.runner` 新运行在 CSV/摘要落盘前创建并校验 `run_manifest.json`。schema 包含项目、Git SHA、数据集身份/哈希/split、模型、prompt/tool/runtime、预算、scorer/gold 来源、成本、run/trace ID、时间与状态。无法适用的 tool schema、runtime、token、scorer 字段使用 `null`。

脚本基线明确标为 `model_id=scripted-oracle`、`cost_usd_estimate=0`；不冒充真实模型运行。Git SHA 必须为 40 位十六进制，非空 SHA 必须为 64 位十六进制，未知/缺失字段在 writer 创建目录或文件前拒绝。历史报告不回写；新报告通过 runner 写入独立报告目录。

验证：`python -m pytest tests/test_run_manifest.py -q`。合成用例覆盖有效清单、无效 Git/hash 与未知字段拒绝。未调用模型或 Docker。

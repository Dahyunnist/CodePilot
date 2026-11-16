# Scripted 评测运行清单（2026-11-13）

`evals.runner` 新运行在 CSV/摘要落盘前创建并校验 `run_manifest.json`。schema 包含项目、Git SHA、数据集身份/哈希/split、模型、prompt/tool/runtime、预算、scorer/gold 来源、成本、run/trace ID、时间与状态。无法适用的 tool schema、runtime、token、scorer 字段使用 `null`。

`dataset_sha256` 现在对按 `case_id` 排序、键排序、紧凑 UTF-8 JSON 序列化的完整 `case.json` rows 求 SHA-256，不再只哈希 ID。清单中的 run/trace ID 表示 batch；CSV 为每题写同值 `evaluation_run_id` 与 `trace_id`，trace event 的 `trace_id` 同样使用 batch ID，`run_id` 保留每题运行 ID。

脚本基线明确标为 `model_id=scripted-oracle`、`cost_usd_estimate=0`；不冒充真实模型运行。Git SHA 必须为 40 位十六进制，非空 SHA 必须为 64 位十六进制，未知/缺失字段在 writer 创建目录或文件前拒绝。历史报告不回写；新报告通过 runner 写入独立报告目录。

验证：`python -m pytest tests/test_run_manifest.py -q`。合成用例覆盖有效清单、无效 Git/hash 与未知字段拒绝。未调用模型或 Docker。

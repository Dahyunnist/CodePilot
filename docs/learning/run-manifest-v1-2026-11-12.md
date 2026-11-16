# Run Manifest v1 与共享 Trace 事件

`evals/manifests/run_manifest_v1.schema.json` 和 validator 约束每次评测身份、数据/代码/提示/工具/scorer 哈希、运行环境、预算、gold 来源、成本、时间与状态。`cp1_fixture_run_v1.json` 是离线机制 fixture 示例，model_id=none、成本为 0，不代表真实 benchmark run。

Trace 统一沿用 run_id/trace_id/span_id；事件字典建议使用 `timeout`、`retry`、`budget_exceeded`、`unsafe_action_blocked`、`cancel`、`checkpoint_resume`。当前 event coverage 尚未逐项落地，schema/validator 不会伪称这些运行已发生。Validator 拒绝 credential/API key 等敏感字段。

测试命令：`python -m pytest tests/test_run_manifest_v1.py -q`。

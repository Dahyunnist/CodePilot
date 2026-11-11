# CP-2 SWE-bench Lite 数据获取

`python -m scripts.fetch_cp2_dataset` 默认只打印计划；显式 `--fetch` 才请求固定 revision `b0dde10` 的 Parquet 文件。数据写入 ignored `.tmp/cp2-swebench-lite-v1`。可选解析依赖由 `requirements-bench.txt` 固定。freeze 记录分离 `source_parquet_sha256` 与规范化 20 题 `subset_json_sha256`，不覆盖旧 JSON 字节 SHA。下载成功不等于任务执行成功；本次未下载数据、未运行 20 题，也未加载隐藏测试到 Agent 工作区。

测试：`python -m pytest tests/test_cp2_dataset_fetch.py -q`，2 passed。dry-run 已验证。许可证仍需按每个上游仓库及数据集条款逐项复核。

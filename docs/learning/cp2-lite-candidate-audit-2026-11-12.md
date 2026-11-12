# CP-2 SWE-bench Lite 候选审计

从冻结 manifest 生成 `auditable-candidates-v1.json`，包含 20 个唯一 task ID、仓库、base commit、许可声明、gold/test patch SHA、隐藏测试路径、测试计数和 Docker 镜像。原 `issue_url` 为空；由 task ID 后缀推导 GitHub issues URL，统一标 `derived_unverified`，没有联网验证可达性。`gold_patch_sha256` 是 gold patch 哈希，不是修复 commit SHA。

这只是 SWE-bench Lite metadata candidate pool，不是 SWE-bench Verified、盲测或可运行集。当前 `.tmp` 无 Parquet 文件，原数据下载曾因 WinError 10013 失败；任务未物化、依赖/许可证未在 base SHA 核查、模型未运行。可重复命令：`python -m evals.public_cases.audit_lite_candidates`；测试 `python -m pytest tests/test_lite_candidate_audit.py -q`。

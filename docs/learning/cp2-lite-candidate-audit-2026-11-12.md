# CP-2 SWE-bench Lite 候选审计

从冻结 manifest 生成 `auditable-candidates-v1.json`，包含 20 个唯一 task ID、仓库、base commit、许可声明、gold/test patch SHA、隐藏测试路径、测试计数和 Docker 镜像。原 `issue_url` 为空；由 task ID 后缀推导 GitHub issues URL，统一标 `derived_unverified`，没有联网验证可达性。`gold_patch_sha256` 是 gold patch 哈希，不是修复 commit SHA。

这只是 SWE-bench Lite metadata candidate pool，不是 SWE-bench Verified、盲测或可运行集。当前 `.tmp` 无 Parquet 文件，原数据下载曾因 WinError 10013 失败；任务未物化、依赖/许可证未在 base SHA 核查、模型未运行。可重复命令：`python -m evals.public_cases.audit_lite_candidates`；测试 `python -m pytest tests/test_lite_candidate_audit.py -q`。

2026-11-12 校正：task ID 后缀可能是 PR 编号，不能冒充 issue 编号。候选导出现在单列 `source_pr_url`；只有源 manifest 明确提供时填写 `issue_url`，否则置 null 并标 `unverified_missing`；`related_issue_url` 保持 null，直到核实 PR 关联 ticket。测试禁止把推导 URL 写进 issue_url。

## 单候选只读复核（2026-11-13）

选取 `django__django-10924`。候选与 frozen-selection 的 repo、BSD-3-Clause 声明、base commit、gold patch SHA 对齐；candidate `test_patch_sha256` 与 selection `hidden_test_patch_sha256` 对齐；PR 来源可追溯到 `https://github.com/django/django/pull/10924`。Issue URL 明确缺失并标 `unverified_missing`。清单没有 fix commit SHA、可见/隐藏测试命令或在 base commit 对应许可证文件的复核证据；`gold_patch_sha256` 只是补丁摘要，不是 fix commit。隐藏侧只有 patch SHA、路径列表和测试计数元数据；本次未读取 patch 内容。

结论：候选元数据可审计，但此题仍不能标为可复现/可运行。20 题冻结集均不能仅凭 metadata 宣称通过真实仓库验收；待补 base 时点许可、可追溯 fix commit、明确测试命令及可隔离的 visible/hidden baseline。回归命令：`python -m pytest tests/test_lite_candidate_audit.py -q`。本次未下载、解包或执行任何上游代码。

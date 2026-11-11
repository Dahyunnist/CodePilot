# CP-2 冻结任务集完整性记录

复用 `evals/public_cases/cp2/frozen-selection.json`：SWE-bench Lite，5 个公开 Python 仓库、20 个任务。源数据版本、SHA-256、仓库/任务分布和 Docker 镜像均以原 manifest 为准；该集合是冻结评测输入，不表示 CodePilot 已执行 20 题。

CP-4 另有三仓六次配对实验 manifest。其模型调用预算上限为 0.50 美元，但预检状态仍为 `pending_materialization_and_visible_hidden_baselines`。本轮不调用真实模型，不能由历史预检或离线测试推断当前余额。

验证：`python -m pytest tests/test_benchmark_manifest_integrity.py -q --basetemp=.tmp\\pytest-basetemp`。测试仅校验 manifest 内部计数、仓库集合和未执行/待预检边界。

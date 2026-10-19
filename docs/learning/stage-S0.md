# S0：状态固化与基线验收

## 目标与结论

S0 把当前多文件修复能力固化成可复查基线。固定评测共 12 个案例；DeepSeek 真实模型在 7 个复杂案例上通过 7/7。该结果仅代表本项目构造的固定案例，不代表真实公司仓库或 SWE-bench 的泛化成功率。

## 数据流与关键代码

1. `evals/live_runner.py` 从每个案例的 `repo/` 复制干净基线，初始化 Git，再用 `WorkspaceManager` 为 Agent 建隔离工作副本。
2. Agent 只收到中文任务、工具描述和工作副本工具结果。真实模型入口在 `codepilot/model.py`；运行中的 token 用量写入 `codepilot/agent.py` 的 JSONL trace。
3. `case.json` 同时保存脚本模型的预设 patch，供 `evals/runner.py` 中的 `ScriptedRepairModel` 做确定性工具流回归。`live_runner` 不把 `case.patches` 传给 Agent 或模型；隐藏测试只在 Agent 结束后由评测器单独挂载并运行。
4. Agent 测试通过后，评测器再次独立运行可见测试和隐藏测试。逐例 JSON、CSV、summary、测试日志和 trace 写在报告目录。
5. `ModelClient` 读取 DeepSeek usage 中的输入、缓存命中输入和输出 token；`live_runner` 按 DeepSeek 对应时段费率估算费用。账单实际金额以提供商为准。

## 设计取舍

- 当前 gold patch 用于确定性评测，不进入真实模型的消息历史；不能把 `scripted-oracle` 的表现当成模型能力。
- 每次运行都从基线建立新副本，避免上次改动污染本次结果。
- `--apply-to-repo` 只在成功测试后回写，并要求源仓库干净、HEAD 未漂移，且先执行 `git apply --check`。
- 本轮 7/7 评测证明的是给定 fixture、提示与测试条件下的结果；真实 Issue 覆盖和仓库规模仍需另行评估。

## 两条失败路径

1. **测试或预算失败**：Agent 测试未通过、独立可见/隐藏测试失败，或时间/token 预算耗尽时不满足成功验收；`--apply-to-repo` 不会回写。
2. **源仓库状态不安全**：回写前发现未提交/未跟踪变更、HEAD 漂移或补丁无法通过 `git apply --check`，回写会拒绝。不要为绕过检查而覆盖工程师本地修改。

## 复现实验

在仓库根目录、`NN` Conda 环境运行：

```powershell
python -m pytest -q
python -m evals.runner --execution docker --output .tmp/s0-evals.csv --work-root .tmp/s0-eval-work --reports-root .tmp/s0-eval-reports
python -m evals.live_runner --execution docker --case-ids multi-file-discount multi-bug-invoice notification-batch-performance bulk-audit-write-performance atomic-csv-import cursor-pagination retry-transient-only --max-total-tokens 35000 --max-elapsed 240 --output-root reports/s0-live --work-root .tmp/s0-live-work
```

S0 记录：完整单测 **73 passed**；Docker scripted-oracle **12/12**；真实 DeepSeek **7/7 accepted**；总计 **125,881 tokens**，费用估算 **$0.009210 USD**，案例累计全流程耗时 **92.3 秒**。保存的逐例数据位于 `reports/live-model-20261019-complex/`。费用按运行时非高峰价格计算；中国法定节假日和账单取整等差异以实际账单为准。

## 10–20 分钟亲手实验

1. 检查 `evals/cases/atomic-csv-import/`：先看 `case.json` 和初始源码，再看可见与隐藏测试的断言。
2. 在 `evals/cases/atomic-csv-import/repo/` 单独执行 `python -m pytest tests -q`，确认基线失败；不要手动套用 `case.json` 中的 gold patch。
3. 运行真实模型命令时只指定 `atomic-csv-import`，检查结果 JSON、CSV、trace 和测试日志；确认 Agent 读取和修改的是临时工作副本。
4. 对一次成功结果，在临时 Git 仓库使用 `--apply-to-repo`；再制造未提交文件，验证回写前置检查会拒绝运行。

## 面试追问

1. 为什么脚本模型可以读取 gold patch，而真实模型不能？评测器如何保证这两个路径隔离？
2. 为什么要在 Agent 内测试之外，再单独跑可见和隐藏测试？
3. 如果回写前源仓库 HEAD 改变，如何判断补丁是否还能安全应用，为什么不能直接强制覆盖？

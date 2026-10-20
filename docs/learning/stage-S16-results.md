# S16：预算停止后的独立验证与新公开 holdout

## 预算后独立验证

S15 的 Agent 因 Token 预算结束，但当时保存的补丁通过可见和隐藏测试。旧流程没有清晰标出“Agent 未完成、补丁独立通过”的结果；验证还可能沿用 Agent 工作副本里的测试文件或 pytest 配置。

本阶段先增加测试，再改运行器：

- 从冻结基线创建全新验证副本。
- 只叠加生产源文件变更；测试、pytest 配置、`conftest.py` 和 `sitecustomize.py` 等仍来自基线。
- 在这个副本运行可见与隐藏测试。
- 报告记录 `post_budget_verification` 和验证副本路径。
- 预算后测试通过只标记 `passed_after_budget_stop`。Agent 状态不是 `success` 时，`accepted` 仍为 `false`。

实现和测试提交：`ca50856 隔离预算中断后的独立验证`。先运行新增测试，确认测试因实现缺失而失败；实现后新增测试通过；全量测试 **112 passed**。

用已保存的 S15 Requests 补丁复核实际验证路径，没有重跑模型，也没有改写 S15 holdout：隔离副本可见测试 `1 passed`，隐藏测试 `1 passed`；`_accepted_for_benchmark` 仍返回 `false`。S15 正式结果维持 **0/1 accepted**。

## S16 新 holdout

冻结任务为 urllib3 issue [#3636](https://github.com/urllib3/urllib3/issues/3636)，上游修复见 [PR #4960](https://github.com/urllib3/urllib3/pull/4960)。案例基于 urllib3 2.5.0 PyPI 源码包，SHA-256 固定于元数据。可见测试、隐藏测试、来源校验和准备脚本在第一次模型调用前提交：`38a8d44 冻结 urllib3 解压缓冲公开 holdout`。

| 指标 | 结果 |
|---|---:|
| 正式验收 | **0/1** |
| Agent 状态 | `budget_exceeded` |
| 基线 | 可见测试失败，确认缺陷被复现 |
| Token | 35,507（输入 34,263，输出 1,244） |
| 估算费用 | `$0.002066 USD` |
| Agent / 全流程耗时 | 10.5 / 16.5 秒 |
| 步数 / 工具调用 | 6 / 10 |
| Agent 测试调用 | 0 |
| 补丁 | 未产出 |
| 预算后独立验证 | `not_run`，没有补丁可验证 |

真实模型在第六步需要新请求时，输入预留已无法放入剩余预算。Agent 没有完成修复，也未运行测试。此结果是失败，不能推断代码修复正确。完整请求轨迹、JSON、CSV 和测试日志在 `reports/public-s16-urllib3-3636/`，该目录保持本地未跟踪。

## 结论

预算后隔离验证通过了保存的真实补丁路径测试。S16 新任务仍未通过模型验收，显示大仓库上下文成本会挤占 Agent 后续修复和测试步骤。下一轮应优先减少每轮无关源码上下文，并给 Agent 测试和最终回复保留预算；S16 已暴露，不能再当 holdout 重跑。

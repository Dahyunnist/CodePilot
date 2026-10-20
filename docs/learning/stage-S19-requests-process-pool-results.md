# S19：Requests 多进程异常序列化结果

## 真实模型结果

冻结提交 `b4456c8` 后，`requests-6628` 只调用一次真实模型。首轮任务即成功：**1/1 accepted**。未修复基线失败；Agent 测试、独立可见测试和独立隐藏进程池测试全部通过。

模型为 `deepseek-v4-flash`，Docker 镜像 `codepilot-requests-runner:s19-20261020`，不可变镜像 ID：`sha256:212c1ac230b762dc874f413e345364f3cf9cd42f2923be1b20bf6fdf94106e0c`。单项额度 100,000 Token、16 步。实际使用 44,214 Token，并在第 10 个模型轮次后调用测试。

| 案例 | 首轮通过 | 最终接受 | Token（输入/缓存输入/输出） | 费用估算 | Agent / 全流程耗时 | 工具调用（读/搜/测） |
|---|---:|---:|---:|---:|---:|---:|
| Requests #6628 | 是 | 是 | 44,214（42,202 / 26,112 / 2,012） | $0.003699 | 19.1 / 25.0 秒 | 12（5 / 0 / 1） |

模型只改 `requests/exceptions.py`，为 `JSONDecodeError` 增加 `__reduce__`，显式调用 `CompatJSONDecodeError.__reduce__`。这与上游合并修复 [PR #6629](https://github.com/psf/requests/pull/6629) 一致。公开 [issue #6628](https://github.com/psf/requests/issues/6628) 描述异常 pickle 失败会损坏进程池；隐藏测试验证 worker 错误能传回主进程，且进程池继续执行任务。

## 结论与边界

这项结果证明 Agent 在一个目标明确、单文件的公开缺陷上能首次修复，并通过进程池隐藏测试。它不能代表多文件、大仓库、复杂性能要求或生产级可靠性。公开问题也可能已进入训练数据。S18 三项仍为 0/3；不能用本次成功抵消失败。

下一阶段扩充不同仓库的新 issue，并优先选跨模块/多文件、性能或行为约束任务。每项先冻结并独立验证；预算采用 100k Token 起步，再按真实轨迹调整。

## 成本账本与证据

本机 `reports/**/*.csv` 可见估算累计 `$0.899795`；相对 `$4.00` 总上限，账面还余 `$3.100205`。这不含仓库报告外调用，也不是 DeepSeek 账单余额。逐案 JSON、CSV、JSONL 轨迹和测试日志位于本机 `reports/public-s19-actual-20261020/`，由 `.gitignore` 排除。

冻结与复现：[S19 案例冻结记录](stage-S19-requests-process-pool-frozen.md)。

## 验证

- Requests 未修复基线：pickle round-trip 失败，报 `TypeError`，缺少 `doc` 和 `pos`。
- 上游金标准：可见测试和隐藏进程池测试均通过。
- Agent：`agent_test_ok=true`、`independent_visible_ok=true`、`hidden_ok=true`。
- 项目测试：`117 passed in 34.61s`。
- 没有重跑 S17、S18 或 S19 案例。

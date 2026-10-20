# S15：Requests 公开 holdout 结果

## Holdout 运行

冻结任务为 Requests issue [#6628](https://github.com/psf/requests/issues/6628)，对应上游修复 PR [#6629](https://github.com/psf/requests/pull/6629)。在首个模型调用前，案例、测试、源码校验和 Docker 镜像定义已提交。运行后没有改动任务说明、测试或验收条件。

| 项目 | 结果 |
|---|---:|
| 模型 | `deepseek-v4-flash` |
| 配置 Token 上限 | 40,000 |
| 模型实际 Token | 36,466（输入 31,653，输出 4,813） |
| 估算费用 | `$0.003383 USD` |
| Agent 时间 / 全流程 | 25.3 / 31.8 秒 |
| 模型步骤 / 工具调用 | 6 / 7 |
| 读文件 | 3 次，5,203 字符 |
| Agent 自测 | 未在模型运行中执行；请求预算预留后停止 |
| 独立可见测试 | 1/1 通过 |
| 独立隐藏 ProcessPool 测试 | 1/1 通过 |
| Patch SHA-256 | `558f2518205694550c61aaa5a66bf09d127ad4c0c81a670b8a1b1a0d3a059da9` |

**正式 holdout 结果仍记为 `0/1 accepted`。** Agent 产出补丁后，两个独立测试都通过；随后我在保留的补丁副本上手动运行冻结的 Agent 测试命令，Docker 中 `1/1` 通过。这个手动复核证明补丁功能通过，但不改写首次 holdout 的 Agent 状态或验收分数。

模型补丁为 `requests/exceptions.py` 增加 `JSONDecodeError.__reduce__`，序列化 `(msg, doc, pos)` 并保留异常实例状态。首次运行与手动验证文件保留在 `reports/public-s15-holdout-final/`；该目录包含原始 trace、JSON/CSV 和测试日志。源码通过 PyPI 归档 SHA-256 固定，Docker 使用固定基础镜像和依赖版本。

## 解释

这个 holdout 证明模型能定位多重继承导致的异常 pickle 问题，并产出通过可见和多进程隐藏测试的补丁。正式分数仍失败，因为 40k 请求预算在 Agent 自测前耗尽。不得把手动补跑算作模型运行成功，也不再重跑这道已暴露任务作为 holdout。

S15 后续应增加“预算允许执行一次完整测试”的任务级最低预留策略，或在任务预算启动时告知模型测试成本；估算输入仍依赖近似 Token 换算，因此实际 usage 检查继续保留。

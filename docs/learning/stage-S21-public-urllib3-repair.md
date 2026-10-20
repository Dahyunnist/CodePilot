# S21：真实模型修复 urllib3 #3653

## 结论

CodePilot 在公开 urllib3 2.5.0 源码副本中完成了 bytes 键兼容修复。真实模型补丁通过 Agent 定向测试、独立可见测试和隐藏测试，**1/1 accepted**。补丁仅改 `src/urllib3/_collections.py`，见[模型生成补丁](stage-S21-public-urllib3-3653.patch)。

补丁已提交到隔离的 urllib3 评测工作区：`12a4ae6 修复 HTTPHeaderDict bytes 键访问`。CodePilot 仓库另行提交 Agent 熔断阈值与本报告。

urllib3 全量回归完成，但有 2 项失败：1 项在 Python 3.11 基线上也会失败；另 1 项是并发敏感测试，完整套件中失败、单独重跑时基线和补丁版均通过。结果没有被记为全量通过。

## 公开问题与失败复现

- 项目：urllib3，版本 2.5.0，来源：[urllib3 官方变更记录](https://github.com/urllib3/urllib3/blob/main/CHANGES.rst)。PR #3653 增加 `HTTPHeaderDict` 的 bytes 键读取、删除和成员判断。
- 源码归档：`urllib3-2.5.0.tar.gz`，SHA-256：`3fc47733c7e419d4bc3f6b3dc2b4f890bb743906a30d56ba4a5bfa4bbff92760`。它与 S20 冻结案例记录一致。
- 评测增加 `getlist(bytes)` 覆盖；保持 `str` 行为、大小写不敏感和非字符串成员查询行为。
- Docker 基线在模型运行前失败：`headers[b"WARNING"]` 抛出 `KeyError: b'warning'`。

任务要求模型只检查 `src/urllib3/_collections.py` 中 `HTTPHeaderDict.__getitem__`、`__delitem__`、`__contains__`、`getlist`，以及 `benchmark_tests/test_issue_3653.py`。要求沿用 `__setitem__` 和 `add` 已有的 Latin-1 解码行为，不改其他模块；证据够后立即补丁和测试。

## 前次预算为何阻塞

S20 原始 urllib3 重跑累计到 43,601 Token 后停止。原因不是单次上下文超限：Agent 已为后续测试和收尾保留 11,058 Token，当前请求无法再满足保留额。输入累计 42,227 Token，缓存输入 26,624 Token；模型反复读取同一实现文件，预算被历史请求消耗。

4,000 字符上下文只允许每个工具观察最多 1,333 字符，源码方法被截断。8,000 字符配置将观察上限提高到 2,666 字符，但模型仍分段重读。因此本轮把任务约束到一个公开行为、一个源码文件和一个指定测试，并将上下文提高到 10,000 字符；单次观察上限为 3,333 字符。源码仓库只有 123 个文件，10,000 字符也是 Agent 对该规模设置的有效上限。

## 真实模型运行

模型：`deepseek-v4-flash`；执行：Docker，镜像 `codepilot-public-runner:20261020`。两次调用均使用冻结的公开源码，没有向模型提供私有数据或 API 凭证。

| 运行 | 参数与结果 | Token（输入/缓存/输出） | 实际时段估算 | 峰时估算 |
|---|---|---:|---:|---:|
| 窄任务初试 | 8k 上下文；第 4 轮触发用户输入熔断；无补丁 | 12,835（12,110 / 8,448 / 725） | $0.001010 | $0.002019 |
| 实修 | 10k 上下文、45k Token、12 步；9 步成功并通过验收 | 38,588（36,712 / 27,520 / 1,876） | $0.002587 | $0.005174 |

每次模型运行的峰价估算都低于 `$0.03`。成功运行的 Agent 耗时 18.8 秒，完整评测耗时 33.6 秒；9 次工具调用包括 3 次读文件、1 次搜索、2 次补丁、2 次测试和 1 次差异检查。

预算上界按峰价保守计算：最多 12 步、每步最多 512 个输出 Token，因此输出最多 6,144 Token。45,000 总 Token 中，其余 38,856 全按未缓存输入计价：`(38,856 × $0.30 + 6,144 × $1.20) / 1,000,000 = $0.019030`。缓存输入只会降低该上界。

复跑命令：

```powershell
python -m evals.live_runner --cases .tmp/public-s21-repair/cases --case-ids urllib3-3653-narrow --execution docker --docker-image codepilot-public-runner:20261020 --max-total-tokens 45000 --context-budget-chars 10000 --max-steps 12 --max-elapsed 240 --output-root reports/public-s21-urllib3-narrow-retry2-20261020 --work-root .tmp/public-s21-urllib3-narrow-retry2-work-20261020
```

## 验收与全量回归

| 检查 | 结果 |
|---|---|
| 修改前定向基线 | 失败，bytes 键读取抛 `KeyError` |
| Agent 定向测试 | 1 passed |
| 独立可见测试 | 1 passed |
| 独立隐藏测试 | 2 passed |
| CodePilot 自身回归 | 122 passed，37.10 秒 |
| urllib3 全量测试 | 1,840 passed、329 skipped、4 xfailed、2 failed，96.74 秒 |

全量测试使用 urllib3 自己的 `uv.lock` 安装 57 个开发依赖，并在无网络 Docker 容器运行。冻结 benchmark 为避免携带 TLS 测试密钥，排除了 4 个公开上游测试夹具；初次全量运行因此出现 `cacert.pem` 缺失并被中断。归档 SHA 已核对后，仅向独立验证副本恢复这 4 个上游测试夹具，再运行全量测试。它们没有进入模型上下文或 CodePilot 源码。

全量运行的两项失败：

1. `test_ssltransport.py::SingleTLSLayerTestCase::test_start_closed_socket` 在未修改的 2.5.0 基线和补丁版都失败。Python 3.11 把 `check_hostname requires server_hostname` 的 `DeprecationWarning` 当成错误。这是基线环境问题。
2. `test_pyopenssl.py::TestHTTPS_TLSv1_2::test_http2_probe_blocked_per_thread` 在补丁版完整套件运行时失败，线程断言观察到线程 ID 重用。随后在原始基线和补丁副本中分别单独重跑，两者都通过；记录为并发敏感的非确定性结果，不归因于本补丁。

一次未补齐测试夹具的全量尝试在 398.9 秒时被终止，约运行到 77%；轨迹显示缺失的 `dummyserver/certs/cacert.pem`。这次失败保留在本报告及本地 `reports/public-s21-urllib3-narrow-retry2-20261020/` 运行记录中。

真实模型轨迹、失败初试轨迹和测试输出已归档在 [`evidence/s21-urllib3-3653`](evidence/s21-urllib3-3653)。真实评测 CSV 与完整报告保留在被 Git 忽略的 `reports/public-s21-urllib3-narrow-retry2-20261020/`；S20 熔断失败仍记录于 [S20 报告](stage-S20-public-issues-results.md)。

## 学习

这次实修表明，重复探索熔断需留出足够修复轮次。阈值从 4 轮调整为 6 轮；连续 2 轮只读时仍提醒模型。明确目标文件、方法、测试和已有兼容写法后，模型在第 4 步完成补丁，接着运行定向测试和完整验收。单靠扩大 Token 上限不能解决证据被截断或任务范围不清的问题。

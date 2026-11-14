# CP-2 配对评测离线框架（2026-11-14）

## 冻结范围

`evals/public_cases/cp2/benchmark-v1.json` 冻结 15 个公开 SWE-bench Lite 案例，分布于 Django、pytest、xarray、seaborn、scikit-learn 五个仓库。记录含题面、base commit、许可证文件哈希、公开 PR、gold patch 哈希（仅哈希）、可见测试规格，以及 model、scorer、runtime、budget 的身份哈希。

该子集标为开发集，不能称作 blind holdout。冻结来源为固定 revision `b0dde1093fe417d83b7184254edf8199c1f0dff5`；任务 base/题面哈希与已清洗的本地子集逐条核对。隐藏测试未读取或运行，gold 补丁正文未读取或送入模型。

## 配对与评分

`evals/cp2_benchmark.py` 定义关闭/启用 ContextSelector 的配对；每题使用相同 prompt、base、可见测试、模型、runtime 与 token/时间上限。失败时保留每变体 JSONL trace、逐题 JSON 结果及 CSV；聚合器按 task ID 对齐两组，保留失败并计算通过差、成本差、耗时差和失败类别。

`evals/live_runner.py --verification-mode visible_only` 只跑 Agent 测试和独立公开可见测试，不读取/哈希/运行隐藏 oracle。该模式结果只代表可见验收，不是 SWE-bench 官方分数。

## 预算闸门与状态

预算账本以本机 73 个结果 CSV 的 92 个有成本 run ID 汇总，估算 `$0.484753`；另计一个 partial 记录 `$0.001120`。相对 `$0.50` cap，估算余量 `$0.014127`。DeepSeek 余额接口仅报告余额/可用性，不提供账户累计 usage，因此账本未与服务端用量对账。15 题双变体按 runner 默认峰值上限的最坏预留超过 cap 余量，真实模型调用被 fail-closed 拒绝。

本轮只验证 manifest、配对协议、预算拒绝与离线 CSV 汇总。未运行 15 题 Agent，不报告真实模型修复率、费用或耗时。

## 复现步骤

以下命令都从仓库根目录执行。`freeze` 与 `ledger` 都采用独占写入，目标文件已存在时会拒绝覆盖；要更新数据版本，应建立新版本文件并重新审计，不能悄悄改写旧锁。

```powershell
python -m evals.cp2_benchmark freeze
python -m evals.cp2_benchmark ledger
python -m evals.cp2_benchmark plan
```

当前 `plan` 预期返回阻断状态：本机预算未和供应商账单对账、配对最坏预留高于余额，而且可见测试/容器基线尚未全部就绪。这是 fail-closed 结果，不是 runner 故障。只有所有阻断项都经独立证据解决后才可运行 `python -m evals.cp2_benchmark run`；真实模型请求仍需单独核预算并获得明确授权。

## 失败路径

1. 选择清单缺任务、仓库许可不在 allowlist 时，冻结器报错，不写部分 manifest。
2. manifest 的模型哈希不匹配、容器 digest 缺失、可见测试未验证、题目数据缺失或含隐藏 oracle 字段时，`plan` 返回阻断；`run` 再次检查，不能绕过。
3. 账本文件从历史结果 CSV 估算费用；它不代表供应商账单，也不会用缓存余额宣称当前可用。剩余费用不足则停止，不发送模型请求。
4. 配对评测在每个变体写入 traces/results；失败样本保留在汇总中，不能把缺失结果当成功。

## 亲手实验与面试追问

在临时副本中从 `frozen-selection.json` 移除一个已选 task，再把副本传给 `freeze_manifest`；预期报 `selection lacks selected tasks`，不改真实冻结文件。面试追问：为什么同时冻结题集、Agent 代码、scorer、runtime 和 model？因为只固定问题本身不足以保证配对比较，任何一项变化都可能成为结果差异的混淆因素。

## 验证

定向测试：`tests/test_cp2_benchmark.py`、`tests/test_live_runner.py`、`tests/test_benchmark_manifest_integrity.py`，31 passed。宿主权限下的全量回归：283 passed in 43.28s。受限执行环境的全量回归在本地 MSYS Git clone 时出现 `0xC0000022`，并未完成；该限制已通过宿主全量回归复核。

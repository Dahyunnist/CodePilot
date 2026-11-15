# CP-2/S1 无模型演练与预算核对（2026-11-15）

## 结论

本轮没有调用模型、Docker 或外部服务。15题冻结清单的任务 ID、问题文本哈希、gold 补丁哈希、任务记录哈希、汇总哈希和选择文件哈希均自洽，gold 补丁内容没有读取或输出。

CP-2 仍不可启动真实评测。项目授权上限为 `$0.50`，本机可见的原始结果 CSV 为 0，DeepSeek 余额与累计用量未对账。因此累计估算 `$0.000000` 只表示本机没有可见 CSV，**不代表账户余额，也不代表可花预算**；`spendable_remaining_usd` 为 `null`，模型调用保持关闭。

按每请求最多 22,000 输入 token、512 输出 token、每任务最多 8 步计算，单次最坏预留为 `$0.0577152`。15题各跑 baseline 和 treatment 两组，计划总预留 `$1.731456`，超过 `$0.50` 上限。当前 manifest/case/source/image/test/工件门槛还有 106 项阻断，其中不少是同一根因在多个校验层重复报告，不能视为 106 个独立缺陷。

## 冻结输入核对

- 任务数：15；唯一任务数：15；与 CP-2 代码内任务 ID 顺序一致。
- selection 文件 SHA-256 与 manifest 记录一致：`f5455478b96a55ed2504a90fe113c483185ef9e62f4ec3cd65281034818f7700`。
- 每题问题文本与冻结 selection 相同，文本 SHA-256 和 gold SHA-256 均匹配。
- 15个任务记录 SHA-256、任务记录汇总 SHA-256、gold 汇总 SHA-256 均通过。
- 旧 manifest 与当前重新生成的 manifest 不要求整份对象相等；旧文件含历史人工证据字段。此处只验证已冻结文件的内部一致性，不覆盖旧冻结文件，也不把静态 exact-base 声明当作宿主实测证据。

## 无模型演练覆盖

新增离线回归验证以下边界：

1. 实际 `run_pairs()` 使用当前 manifest 与账本预检；预算未知、case 缺失时返回阻断码 `2`，输出包含“未发送模型请求”，不创建输出目录，live runner 调用计数为 0。
2. 通过 monkeypatch 替代计划器和 live runner，演练 baseline 成功、treatment 失败的配对编排；两个结果目录里的 JSONL 轨迹及 CSV 均保留，配对摘要包含成功/失败结果。此项只证明文件编排，不证明真实 runner 的模型轨迹内容。
3. 输出目录必须全新。预先存在时，driver 抛出 `FileExistsError`，不启动 runner，也不覆盖目录里的旧文件。
4. Agent 达到 `max_steps=2` 时，假模型请求数恰为 2；SDK retries 为 0 的既有测试继续覆盖重试关闭。

这组演练不是 CP-2 成功评测，也没有 Docker 运行、公开测试 baseline 或模型质量结论。真实开启前仍须补齐并复核：provider 用量/余额账本、可支配额度、exact-base 镜像与许可证据、15题独立 visible-only 测试及 baseline、case 物化、工件哈希和 xarray-4493 镜像摘要。预算仍须满足整轮最坏预留，或由负责人明确缩小并重新冻结评测范围。

## 测试记录

使用 Python 环境执行，无模型/网络/Docker：

```powershell
python -m pytest tests/test_cp2_benchmark.py tests/test_live_runner.py tests/test_benchmark_manifest_integrity.py tests/test_agent.py::test_loop_stops_at_max_steps -q --basetemp="$env:TEMP\cp2-s1-offline"
```

结果：`59 passed in 4.34s`。

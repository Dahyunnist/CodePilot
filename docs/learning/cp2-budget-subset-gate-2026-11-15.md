# CP-2 三题预算子集与严格预算门禁（2026-11-15）

## 决策

原有15题冻结清单保持不变。本阶段另冻结 CP-2 预算候选 `budget-subset-3-v1.json`：Django 10924、pytest 5103、seaborn 2848，各来自独立上游仓库。选择恰好3题，是满足“至少3个独立任务”约束的最小子集。子集只保存任务 ID、仓库、base commit、问题哈希、gold 哈希、可见测试规格哈希和镜像摘要；不含 gold 补丁内容。

子集记录父 manifest 的 SHA-256，并对自身做 canonical SHA-256。子集 SHA-256：`dd03fa16cbcc3690490fe84b03676fa1b2ea2c10d0e66ecd0206aa7962ec463b`。它是**预算预检清单**，不是已通过 CP-2 runnable gates 的新评测 manifest。原15题的 exact-base、测试物化、baseline、来源和运行镜像阻断仍有效。

## 峰价预留

子集保持 baseline/treatment 两组。每题每组最多8个 Agent step；SDK retries 为0。因此最多请求数为：

`3题 × 2组 × 8步 = 48次模型请求`

以每次最多22,000个 uncached input tokens、512个 completion tokens，并按峰价 `$0.30/M` 与 `$1.20/M` 计：

`48 × (22,000 × $0.30 + 512 × $1.20) / 1,000,000 = $0.3462912`

这是保守的整轮 campaign 预留，不是预测实际账单。保留项目授权 cap `$0.50`，不因子集而提高。按零累计支出时，预算算术上可容纳该预留；**当前不能据此发起模型请求**，因为本地账本缺原始 CSV，且 provider 累计用量、DeepSeek 当前余额与证据文件均未知。

## 门禁规则

`plan` 和 `budget-plan` 均采用 fail-closed 规则。放行预算检查必须同时满足：

1. ledger 声明 provider 用量已对账，且 `usage_evidence_status` 为 `provider_reconciled`。
2. `provider_cumulative_spend_usd` 是有限、非负数；本地 CSV 推算字段 `known_cumulative_estimated_cost_usd` 不能替代它。`provider_balance_status` 必须为 `verified`，`provider_balance_usd` 必须是有限、非负数。
3. provider 用量和余额各有仓库内相对路径及 SHA-256；路径不能逃出仓库、不能是符号链接，文件内容必须匹配摘要。
4. `累计项目支出 + 本轮完整最坏费用预留 <= $0.50`。
5. provider 当前余额至少覆盖完整 campaign 预留。

缺余额、provider 累计账单或证据文件时，预检只列阻断原因，不执行模型。账本里的 `spendable_remaining_usd`、本地费用估算或“余额充足”文字不能替代上述字段与文件哈希。`authorized_project_cap_usd` 也不会覆盖代码中的 `$0.50` 固定授权上限。

## 无模型预检

先看冻结子集、请求上限与费用，再检查账本：

```powershell
python -m evals.cp2_benchmark budget-plan
```

命令只读子集、父 manifest、账本和账本声明的证据文件；账本不存在时，只在内存中扫描现有报告，不会生成或修改账本，也不会调用模型或 Docker。当前预期非零退出，原因是 provider 用量、余额及证据缺失。只有完整证据录入并且预检通过，预算门禁才放行；还需通过原 `plan` 的镜像、visible-only case 和 baseline 等运行门禁。

## 验证范围

新增离线测试覆盖：最小三仓库子集与自哈希、48次请求及峰价预留、未知余额/缺证据拒绝、累计支出超过 cap 拒绝、余额不足拒绝、累计支出与余额均足够时的预算门禁通过。测试使用临时文件和假数据，不向 provider 发送请求，不启动 Docker。原始15题冻结文件不改写。

```powershell
python -m pytest tests/test_cp2_benchmark.py tests/test_live_runner.py tests/test_benchmark_manifest_integrity.py tests/test_agent.py::test_loop_stops_at_max_steps -q --basetemp="$env:TEMP\cp2-budget-offline"
```

结果：`67 passed`。只读 `budget-plan` 返回退出码 `2`，明确阻断于 provider 用量对账、余额、证据文件和 provider 累计支出缺失；没有请求模型，也没有写 ledger。

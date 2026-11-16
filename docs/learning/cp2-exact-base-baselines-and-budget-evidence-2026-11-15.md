# CP-2 exact-base 基线与预算证据门禁（2026-11-15）

## 可见测试基线

复核 `evals/public_cases/cp2/smoke/baseline-2026-11-15.json` 后，旧文字中的三项“预期基线失败”没有证据支持：三条记录当前都是 `status=blocked`、退出码 125。Docker 镜像预检未成功，因此没有完成摘要比较，也没有执行测试命令。当前可报告的是 3 项阻塞、0 项已执行基线测试；不能引用旧失败摘要，也不能称基线测试已复现。

用下面命令重新生成一次离线报告：

```powershell
python scripts/run_cp2_base_smoke.py
```

runner 校验预算子集哈希、题目元数据、来源清单哈希、可见测试哈希、镜像 config digest 和容器内 base commit/tree。容器只用 `--pull=never --network none`。任一前置校验失败、Docker 启动失败或超时都会记为 `blocked`；只有确实执行测试命令并得到非零退出码，才记为 `expected_baseline_failure`。零退出码会记为 `unexpected_base_pass`。报告不调用模型，不尝试修复。

用户已拉取的 seaborn-3010 镜像不属于当前三题预算子集；不能拿它替代 seaborn-2848 镜像或摘要。该离线基线也不等于 Agent 修复成功率或完整 CP-2 配对评测。

## 预算证据门禁

不将账单导出、项目/API key 别名、金额或原始文件哈希写入仓库。只有完整的 provider 用量、余额与 FX 证据通过校验后，预算门禁才可放行。

`build_budget_ledger` 会把该摘要作为部分证据引用；`validate_budget_ledger` 会验证摘要文件哈希，并明确报告完整累计支出仍未知。部分金额不会写入 provider 累计美元数，也不能放行模型调用。

`validate_budget_ledger` 现在要求以下内容同时成立：

1. usage、balance、FX policy 三份仓库内 JSON 证据文件通过路径安全检查和 SHA-256 校验。
2. usage 明确归属项目 API key；账号总额不能分摊给项目。
3. usage 声明完整历史覆盖，并带起止日期；证据 JSON 与 ledger 的归属、日期、原始金额和币种一致。
4. balance 证据匹配原始金额和币种；FX policy 证据匹配政策 ID、方法、汇率、来源和生效日期。
5. usage 与 balance 原币币种一致，折算美元金额与原额乘汇率一致；再检查授权 cap 和整轮 campaign reserve。

单测只使用临时 JSON 与合成汇率，不代表 DeepSeek 的真实 FX 政策，也没有因此放行真实模型调用。真实账本缺少项目级历史归属或汇率政策时，仍须阻断。

# CP-2 exact-base 基线与预算证据门禁（2026-11-15）

## 可见测试基线

在本机已缓存镜像上，对预算子集三题执行 exact-base 可见测试。容器使用 `--pull=never --network none --rm`；可见测试从宿主机只读挂载，先切换到冻结 base commit，再复制到临时容器。测试输出和镜像摘要记录在 `evals/public_cases/cp2/smoke/baseline-2026-11-15.json`。

| 任务 | 结果 | 失败摘要 |
| --- | --- | --- |
| Django 10924 | 预期基线失败，2 tests | `TypeError`：`scandir` 收到 function |
| pytest 5103 | 预期基线失败，1 failed / 71 deselected | `test_unroll_expression` 诊断断言失败 |
| seaborn 2848 | 预期基线失败，1 failed / 72 deselected / 12 warnings | `test_hue_order` 抛出 `TypeError` |

三题镜像 config digest 与冻结预算子集一致，且各镜像含对应 base commit。退出码 1 是缺陷复现的预期结果，不是 Agent 修复成功。没有调用模型、生成修复补丁、统计模型成本或执行 Agent 评分。因此这些记录只证明公开测试在冻结基线可运行并复现失败，不能证明 Agent 能修复三题。

仓库中的 runnable case 目录仍缺上游 `repo/`，所以 CP-2 正式 runner 仍无法对三题执行完整 baseline-treatment 配对。此次容器操作不写回宿主源码。

## 预算证据门禁

`validate_budget_ledger` 现在要求以下内容同时成立：

1. usage、balance、FX policy 三份仓库内 JSON 证据文件通过路径安全检查和 SHA-256 校验。
2. usage 明确归属项目 API key；账号总额不能分摊给项目。
3. usage 声明完整历史覆盖，并带起止日期；证据 JSON 与 ledger 的归属、日期、原始金额和币种一致。
4. balance 证据匹配原始金额和币种；FX policy 证据匹配政策 ID、方法、汇率、来源和生效日期。
5. usage 与 balance 原币币种一致，折算美元金额与原额乘汇率一致；再检查授权 cap 和整轮 campaign reserve。

单测只使用临时 JSON 与合成汇率，不代表 DeepSeek 的真实 FX 政策，也没有因此放行真实模型调用。真实账本缺少项目级历史归属或汇率政策时，仍须阻断。

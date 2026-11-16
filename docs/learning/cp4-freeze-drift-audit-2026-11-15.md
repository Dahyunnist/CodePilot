# CP-4 冻结输入漂移审计（2026-11-15）

## 结果

在隔离 worktree 运行 CP-4 Skill、冻结协议、共享 live manifest 和离线配对比较器定向测试：**16 passed，1 failed**。失败来自 `tests/test_cp4_skill_freeze.py::test_cp4_protocol_and_all_evaluation_inputs_are_frozen` 的输入哈希断言。

冻结协议 `evals/skills/cp4-paired-protocol-2026-11-15.json` 仍有完整自身摘要，配对关系测试通过；但它绑定的两个源码文件已变化：

| 文件 | 冻结 SHA-256 | 当前 SHA-256 |
|---|---|---|
| `codepilot/agent.py` | `043b5ba4e228b50d146b1c4cd3779c3dd1798983fa624ce6aa847be79cccba20` | `69ea1739a0d52d550e9db3aaf5237fda67f7c652151eaab461031f81a591b477` |
| `evals/live_runner.py` | `5011e22b56bcc7f9efcc5c9693f779107e3cf35cf9fd3afe509ea21d2f7b16fe` | `40a56f947e486dc37208062315c0e0fa4585ba68e0bd4ea65b9f52e56058a5de` |

这表示旧 CP-4 配对协议不能证明当前源码配置仍与冻结实验相同。此审计没有重写协议、重新冻结哈希、运行模型或 Docker，也没有声称 Skill 效果提升。要进行未来配对实验，应在独立版本中重新审阅全部输入并冻结新协议；旧协议保持原样，避免改写历史证据。

## 其余离线覆盖

同一命令中，Skill allowlist/输入契约、shared live manifest 脱敏/计数/成本、以及离线配对比较器均通过。真实余额与费用门禁仍未解除，真实模型评测仍暂停。

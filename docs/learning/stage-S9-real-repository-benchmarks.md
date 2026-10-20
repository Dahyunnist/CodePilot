# S9：真实仓库、多缺陷和性能基准

## 范围

新增固定版本的 Click 上游回归案例：仓库 `pallets/click`，提交 `1d038f270701498433cb432f54db89f95f07a845`，官方 Git tree `3c2036983ac4e0120b5946244f36351b4a276f34`。下载 ZIP 的 SHA-256 为 `f3999c7e787a93e159eb78a97db7a768a441509795a23f3a060bde24362ff38d`。准备脚本校验 Git tree 后才建立评测副本，并把可见回归测试和隐藏测试放在评测目录；模型只获得仓库副本。

案例针对 [Click issue #3145](https://github.com/pallets/click/issues/3145)：公开 `Context.lookup_default()` 不应泄漏内部 `UNSET`，同时 `Parameter` 内部仍需区分缺省值和显式 `None`。上游修复见 [PR #3224](https://github.com/pallets/click/pull/3224)。

Click 为真实上游仓库，不是 CodePilot 合成小夹具。其 `src/` 布局要求 pytest 的 `PYTHONPATH` 指向 `src`；主机和 Docker 执行器现在均自动处理此布局。准备命令：

```powershell
python evals/public_cases/prepare_click_3145.py --source <Click-8.3.1源码目录> --output .tmp/public-cases/click-3145
python -m evals.live_runner --cases .tmp/public-cases --case-ids click-3145 --execution docker
```

## 真实模型结果

DeepSeek V4 Flash、Docker、固定 Click 源码，共 6 次探索运行，均未满足 Agent 的完整成功条件。模型有时达到 Token 上限，有时达到步数上限。六次合计 740,083 Tokens、估算费用 `$0.127312`、评测累计耗时约 255.9 秒。

| 运行 | 状态 | Token | 费用 USD | 全流程秒 | 独立可见测试 | 隐藏测试 |
|---|---|---:|---:|---:|---|---|
| run1 | budget_exceeded | 33,513 | 0.007536 | 14.2 | 未运行 | 未运行 |
| run1b | budget_exceeded | 70,050 | 0.007244 | 26.2 | 未运行 | 未运行 |
| run1c | max_steps | 94,633 | 0.013853 | 43.4 | 未通过 | 通过 |
| v2-run1 | budget_exceeded | 114,442 | 0.023385 | 44.7 | 未运行 | 未运行 |
| v3-run1 | max_steps | 169,651 | 0.031824 | 62.7 | 通过 | 通过 |
| v3-run2 | budget_exceeded | 257,794 | 0.043470 | 64.8 | 未运行 | 未运行 |

v3-run1 写入了与上游修复一致的补丁，独立可见和隐藏测试都通过；Agent 未在步数预算内完成自测和最终答复，所以按当前“完整任务成功”标准仍计失败。六次样本显示，该 Agent 在 Click 这样的成熟仓库中存在明显的工具循环和上下文成本问题；不能把独立补丁通过说成端到端成功。运行轨迹和测试记录在 `reports/public-click3145-*`。

## 多缺陷与性能案例

另用真实模型在 Docker 运行三类跨模块案例，均通过 Agent 测试、独立可见测试和隐藏测试：

| 案例 | 类型 | Token | 估算费用 USD | Agent 秒 | 全流程秒 |
|---|---|---:|---:|---:|---:|
| `multi-bug-invoice` | 跨模块金额与 API 契约，多缺陷 | 55,180 | 0.005657 | 19.5 | 22.8 |
| `bulk-audit-write-performance` | 批量写入、幂等、整批校验 | 37,304 | 0.003382 | 15.4 | 18.5 |
| `notification-batch-performance` | 批量查询、去重、顺序与停用状态 | 29,053 | 0.002657 | 12.3 | 14.9 |

三项合计 121,537 Tokens、估算 `$0.011696`、全流程累计 56.1 秒。完整报告、逐轮轨迹和测试日志在 `reports/live-model-20261020-s9-real-cases/`。另有 S8 的 `multi-bug-invoice` 成功样本，可供跨阶段对照。

## 外部仓库回写

S3 已在 `E:\job\.tmp\codepilot-s3-external-repo` 验证完整流程：外部仓库建基线、独立工作区修复、Docker 测试、暂停等待、由第二个 CLI 进程批准并回写、回写后在源仓库复测。补丁只改 `config_parser.py`，最终 3 项测试通过；完整记录见 `docs/learning/stage-S3-project-context.md` 和 `reports/live-model-20261020-s3-writeback-external/`。

## 阶段结论与后续

- 当前可在中小型多文件案例上处理多个相互关联的缺陷和可量化性能目标；三个新增真实模型案例均通过。
- 成熟上游仓库案例揭示了真实限制：重复检索与重读会把成本推高到数十万 Token，步数上限也会阻止 Agent 在验证通过后正常收尾。
- 后续优先做轨迹级评分和工具策略离线比较，使用冻结的训练、验证、测试划分；未在独立留出案例上稳定胜出前，不宣称已实现强化学习能力。

## 验证

- NN 环境完整测试：`D:\Anaconda3\envs\NN\python.exe -m pytest -q`，**96 passed**。
- Git whitespace 检查：`git diff --check` 通过。

# S3 阶段记录：项目约定、跨模块修复与外部仓库写回

## 阶段目标

让 Agent 在大型项目任务中遵守仓库约定、跨模块修改并独立验证结果；真实模型评测同时记录成功、预算失败、Token、估算成本与耗时；核实从项目目录外的仓库启动任务、等待审批、批准写回的完整流程。

## 已完成

- `task_prompt()` 读取任务仓库根目录的 `AGENTS.md`，将其作为项目约定传给模型。内容上限 12,000 字符；文件不存在、不可读或解析到仓库外时不注入。提示明确项目文件不可信，不能覆盖系统安全规则。
- 新增提示测试：正常读取、长度上限、越界符号链接拒绝、无约定文件时照常运行。
- `multi-bug-invoice` 加入模块边界说明：请求校验、金额计算、发票编排分属不同模块；模型需要遵守百分比及 Decimal 契约。
- 对跨模块、多缺陷、性能与分页案例跑 DeepSeek V4 Flash + Docker；独立可见测试与隔离隐藏测试分别验收。
- 在 `E:\job\.tmp\codepilot-s3-external-repo` 建立独立 Git 仓库，完整执行模型修复、Docker 测试、暂停等待审批、第二次 CLI 进程批准写回、外部仓库复测。源文件补丁 SHA-256 为 `c729f6ff000bd533ef1da31d509ab76fae3c2604831fc401172767a056b7b7b5`；回写后外部仓库 `tests` 为 3 passed，差异只包含 `config_parser.py`。

## 真实模型结果

模型为 `deepseek-v4-flash`，Docker 镜像 `codepilot-runner:0.1`，温度由服务商默认值决定。成本按当次 usage 和 DeepSeek 非高峰价估算，实际账单以平台为准。每个案例独立副本，基线必须失败，Agent、可见测试和隐藏测试都通过才算验收。

| 案例 | 设置 | Agent 状态 | 验收 | Token | 估算成本 USD | Agent 耗时 | 全流程耗时 |
|---|---:|---|---:|---:|---:|---:|---:|
| atomic-csv-import | 25k | success | 通过 | 20,515 | 0.001289 | 12.9 秒 | 16.6 秒 |
| cursor-pagination | 25k | success | 通过 | 18,451 | 0.001515 | 13.3 秒 | 17.4 秒 |
| notification-batch-performance | 25k | success | 通过 | 17,937 | 0.001244 | 9.9 秒 | 14.1 秒 |
| multi-bug-invoice，第 1 次 | 25k | budget_exceeded | 未通过 | 28,477 | 0.002550 | 18.9 秒 | 23.9 秒 |
| multi-bug-invoice，第 2 次 | 25k | budget_exceeded | 未通过 | 28,598 | 0.002701 | 18.9 秒 | 24.0 秒 |
| multi-bug-invoice，第 3 次 | 40k | budget_exceeded | 未通过 | 40,663 | 0.002958 | 21.2 秒 | 26.5 秒 |
| multi-bug-invoice，第 4 次 | 60k | success | 通过 | 25,987 | 0.002256 | 14.3 秒 | 19.1 秒 |

四个复杂案例汇总为 4/4 通过；其中发票案例前三次在收尾模型请求后耗尽设置的预算，检查时补丁已通过 Agent、独立可见和隐藏测试。提高上限后任务完成。四次发票运行成本约 0.010465 USD，7 次案例合计约 0.014513 USD。Token 与单次耗时有明显波动，需用多次运行报告，而不是只报最好结果。

项目目录外仓库回写实测：12,756 Tokens，非高峰估算 $0.000708，Agent 8.1 秒、测试 1.2 秒、CLI 总流程约 10 秒（包含批准的第二进程）。外部源仓库最终复测 3 passed。一次性外部仓库保留于 `E:\job\.tmp\codepilot-s3-external-repo`，未提交到 CodePilot 仓库。

## 开源问题与评测边界

调查了 Click 上游 issue [#3145](https://github.com/pallets/click/issues/3145)：Click 8.3.0/8.3.1 的 `Context.lookup_default()` 在无默认值时返回 `Sentinel.UNSET`，调用方预期得到 `None`。上游通过 [PR #3224](https://github.com/pallets/click/pull/3224) 修复，后续 8.3.2 发布说明含此变更。

这轮未能取得 Click 8.3.1 完整仓库源码，因此没有把 issue 复现称为真实仓库 Agent 评测，也没有声称通过 SWE-bench。当前复杂评测是本仓库的受控多文件 fixture；它能验证工具循环和隐藏测试，但不能替代带锁定 commit、容器镜像与官方任务 harness 的真实上游仓库评测。SWE-bench 的任务集和 harness 见[官方仓库](https://github.com/SWE-bench/SWE-bench)。

## 产物

- `reports/live-model-20261020-s3-run1/`：首轮四案例完整数据；包含三次通过与一次预算停止。
- `reports/live-model-20261020-s3-run2/`、`run3/`、`run4/`：发票相同任务重复与预算阶梯实验。
- `reports/live-model-20261020-s3-writeback-external/`：外部仓库写回 CLI 报告、轨迹与状态数据库。
- 每个真实模型运行保留 CSV、JSON、JSONL 轨迹、测试日志和补丁哈希。

## 10 分钟动手实验

1. 在临时仓库根目录写 `AGENTS.md`，约束金额必须用 `Decimal`，再用 CLI 运行发票案例。
2. 从轨迹查看 Agent 是否读取约定、跨模块改动并运行全部测试。
3. 用 25k、40k、60k Token 上限分别运行，比较预算终止、最终状态、成本与隐藏测试。
4. 在仓库外创建干净 Git 项目，加 `--apply-to-repo`；先检查待审批差异和 SHA，再用新的 CLI 进程批准或拒绝。
5. 修改源仓库 HEAD 或等待期间改变补丁后尝试审批，确认系统拒绝过期写回。

## 面试追问

**为什么 `AGENTS.md` 不能覆盖系统提示？** 它来自仓库内容，可能被提交者或依赖污染；它可以提供模块边界和测试命令，但不是授权来源。

**为什么 Agent 测试通过仍可能标为失败？** 最终模型调用也计入 token；达到预算时运行会停止。验收需同时看状态、独立可见测试和隔离隐藏测试，不能只看补丁或单次工具结果。

**为什么还不能说支持生产级大型代码库？** 当前上下文只有根目录约定，没有分层 `AGENTS.md`、依赖图、跨服务架构索引或公司研发知识检索；评测也不是完整 SWE-bench 官方 harness。要用于真实生产，还需安全、权限、代码所有权、可观测性及大量代表性仓库验证。

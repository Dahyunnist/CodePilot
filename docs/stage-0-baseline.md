# S0 基线审计

审计日期：2026-10-18；配置补充：2026-10-19

仓库提交：`1aef0bc`（`feat: add isolated execution and repeatable evaluation`）

审计范围：仓库文档、核心模块、测试、固定评测记录、Git 工作区。

## 当前工作区

- 初始审计时 `git status --short --branch` 输出 `## master`，工作区干净。
- 项目已包含 CLI、显式 Agent Loop、模型适配器、工具注册与校验、干净 Git 工作副本、Docker pytest、JSONL trace、Markdown 报告、5 个固定案例和测试。
- 依用户要求补上 `.env` 加载：`codepilot/config.py` 读取项目根 `.env`，现存进程环境变量优先；没有重建已有模块。
- 手动修复实验在 `.tmp/s0-manual-parse-config` 独立 Git 副本完成；原始 fixture 保持未修改。

## 数据流

```text
CLI 参数和环境配置
  -> WorkspaceManager：从源仓库已提交 HEAD 克隆干净副本
  -> Task + ToolRegistry + ModelClient + TraceLogger
  -> Agent：请求模型 -> 校验/调度工具 -> 把 ToolResult 作为 observation -> 再请求模型
       | list/search/read/patch/diff -> 工作副本
       ` run_tests -> pytest 策略检查 -> Docker 或获批的 host 子进程
  -> 最新测试状态 + Git diff + trace -> RunResult
  -> CLI 输出 + reports/runs/<run_id>.md
```

核心位置：`cli.py` 组装依赖；`agent.py` 管循环、预算、审批和终态；`model.py` 归一化模型回复；`tools/registry.py` 校验不可信工具参数并分发；`tools/repo.py`、`tools/edit.py`、`tools/execute.py` 实际操作；`workspace.py` 建副本；`tracing.py` 写事件；`report.py` 渲染结果；`evals/runner.py` 管固定集和独立隐藏测试。

## 构建与测试证据

| 检查 | 本轮实际结果 | 证据与限制 |
|---|---|---|
| `D:\Anaconda3\envs\NN\python.exe -m pytest -q` | `42 passed in 7.62s` | 项目全量测试通过，包含 `.env` 回归测试 |
| `docker version` | Client 29.1.3；Server Docker Desktop 4.55.0，Engine 29.1.3 | 此次直接查询确认 daemon 响应 |
| `.env` 配置冒烟检查 | 通过 | 临时 `.env` 可提供模型名与 key；同名进程环境变量优先。未打印或读取真实 key |
| 用户本机固定集复跑（2026-10-19） | `reports/eval_results.csv` 为 5/5；五例 visible/hidden 均通过，每例 6 steps、0 tokens | 模型为 `scripted-oracle`，温度 0，版本 `explicit-loop-v1`；验证评测链路，不代表真实模型能力 |
| 代理会话固定集尝试 | `reports/s0-baseline-20261019.csv` 为 0/5 | Docker 子进程无法读取用户配置并访问 Named Pipe，pytest 容器未启动；这是执行边界失败，不是有效模型评测 |
| 先前固定集记录 | 原 `reports/eval_results.csv` 也为 5/5 | 用户本机本次运行已更新主 CSV 和 demo trace；旧 trace 仍在 `reports/traces/` |
| 演示初始失败 | `evals/cases/parse-config/baseline-output.txt` 保存 `1 failed, 2 passed` | 失败为 `test_empty_input_returns_empty_config`；这是 fixture 初始状态证据，不是当前项目测试结果 |
| 用户本机复现实验（2026-10-19） | 在 `evals/cases/parse-config/repo` 运行 `python -m pytest -q`，得到 `1 failed, 2 passed in 0.09s` | 与预期一致，唯一失败是 `test_empty_input_returns_empty_config`；这是 fixture 基线，不是项目根测试 |
| 手动修复实验 | 临时副本基线 `1 failed, 2 passed in 0.04s`；改一行后 `3 passed in 0.01s` | 唯一代码差异是把 `if not line and text:` 改为 `if not line:`；副本 commit 为 `71fabf6`，原 fixture 未改 |

没有安装依赖。用户在 Conda `NN` 复现 fixture 初始失败；项目全量测试通过；用户终端 Docker daemon 可访问并完成 5/5 scripted 固定评测。代理会话自身两次启动 Docker 子进程都受配置文件/Named Pipe 访问边界限制，分别保存在 `reports/s0-baseline-20261019.csv` 和 `reports/s0-retry-20261019.csv`，不与用户本机评测混为一谈。

## 已实现与缺口

已实现：显式 while-loop；工具 schema 与 Pydantic 参数校验；仓库内路径约束、精确单次文本替换；pytest 命令策略、超时和输出截断；独立 clone；Docker 的无网络、只读容器根、非 root、资源限制；host 测试审批；补丁成功后清除旧通过测试状态；JSONL 轨迹、差异和报告；隐藏测试在 Agent 完成后独立运行；`python-dotenv` 加载项目根 `.env`，且不覆盖已存在的进程变量。

尚未实现或未证实：真实模型修复能力与至少 3 个真实任务；运行级模型/版本/随机性等完整实验记录；生产级沙箱、恶意仓库防护和多租户隔离；checkpoint 恢复。固定评测的 5/5 仅证明 scripted 工具序列与评测链路。

## 简历候选表述与证据

- 可陈述：实现 Python 仓库修复 Agent 原型，包含显式工具循环、隔离工作副本、受限 pytest、独立隐藏测试和轨迹报告。依据：当前源码和测试覆盖。
- 可陈述：模型配置支持从项目根 `.env` 载入；环境变量优先。依据：代码、冒烟检查和通过的项目回归测试。
- 可陈述但须注明：固定评测链路中，`scripted-oracle` 在 5 个固定案例取得 5/5。依据：现存 CSV、Markdown 与 trace；不是本轮复跑，不是模型能力指标。
- 不可陈述：真实模型成功率、真实模型完成 3 个任务、SWE-bench 分数、企业级安全或生产可靠性。当前没有相应证据。

## 故障演示

任务输入：`parse_config` 对空字符串抛错。临时副本中改 `if not line and text:` 为 `if not line:`；验收为 `parse_config("") == {}` 且三个测试通过。修复前唯一失败是 `test_empty_input_returns_empty_config`；非法配置行仍保留行号错误。原始 fixture 没有改动。Agent 演示指令：`parse_config crashes on empty input; fix it`。README 的 CLI 示例命令是演示模板；尚未证明真实模型能完成该任务。

## 风险清单

1. 项目 pytest 和用户本机固定集均通过；代理工具会话的 Docker 子进程受用户目录 ACL 限制，故代理环境的 0/5 不能作为产品指标。
2. `scripted-oracle` 将每例预设工具调用和补丁写在 case 元数据中；它测的是链路，不是推理泛化。
3. Docker bind mount 中的工作副本仍可被测试代码写入；Docker、内核和 Git 仍在信任边界内。
4. `WorkspaceManager` 只克隆已提交内容，源仓库未提交改动不会进入任务副本；报告和 CLI 可能显示仓库内容，不能将其视为脱敏输出。
5. S1 目标“至少 3 个真实模型任务”尚未达成；不应据此写入简历。

## 后续阶段进展

以上结论记录 S0 完成时的状态。用户随后授权进入 S1；三项真实模型修复已完成，结果、限制和证据见 `docs/learning/stage-S1.md` 与 `reports/live-model-20261019-s1-verified/`。S1 结果不能改写为 S0 的能力证明。

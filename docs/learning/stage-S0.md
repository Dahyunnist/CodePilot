# S0 学习：基线审计与复现

## 1. 本阶段解决的问题

目标是确认修复 Agent 已有哪些真实能力，以及测试能否在当前环境复现。仓库已有显式 Loop 和固定评测骨架；使用用户给出的 Conda `NN` 解释器后，项目全量测试通过。Docker daemon 直查成功，但固定评测启动的 Docker 子进程受当前执行边界阻断。既有 5/5 记录来自 `scripted-oracle`，只能说明脚本化工具链工作过。

前后行为：最初审计没有代码变化。按用户要求补充模型配置后，`ModelConfig.from_env()` 会加载项目根 `.env`；系统进程已有的变量保持优先。审计确认项目测试可在 `NN` 运行，但当前工具会话不能稳定访问 Docker context 与 Engine。

## 2. 数据流与关键文件

```text
cli.py -> workspace.py -> agent.py <-> model.py
                                |
                                v
                      tools/registry.py
                  /         |         \
             repo.py      edit.py    execute.py -> pytest
                  \         |         /
                ToolResult observation -> AgentState
                                |
                 tracing.py + report.py -> RunResult
                                |
                     evals/runner.py -> hidden tests
```

- `codepilot/cli.py`：解析任务和预算，组装 workspace、模型、工具、trace。
- `codepilot/config.py`：先从项目根 `.env` 加载设置，再读取进程环境；`override=False` 保证显式环境变量优先。
- `codepilot/agent.py`：循环请求模型，执行工具，把结果追加为 tool message；未测试先结束为失败；成功补丁会使旧测试通过状态失效。
- `codepilot/tools/registry.py`：校验参数，按工具名分发。错误转成失败 `ToolResult`。
- `codepilot/tools/execute.py`：仅接受 pytest 形式命令；host 用子进程，Docker 用固定 argv；超时、退出码和截断输出进入 `ToolResult`。
- `codepilot/workspace.py`：从已提交 Git 状态克隆唯一任务副本，不复制未提交文件。
- `evals/runner.py`：每个 fixture 建固定提交；先确认可见测试失败，再运行 Agent；Agent 结束后挂载隐藏测试。

## 3. 关键设计取舍

- 显式 `while` loop 足以表达当前 reason-act-observe 和终止条件。没有因“Agent”名义引入 LangGraph；现有证据未显示需要图编排、checkpoint 或恢复。
- 用 `python-dotenv` 处理 `.env` 语法，避免自行解析引号和注释；只读项目根文件，避免误读目标仓库中的配置。`.env` 仍由 `.gitignore` 排除。
- 精确且唯一匹配的文本替换避免整文件覆盖；匹配为 0 次或多次都失败，防止猜测性编辑。
- 固定 scripted 流程先检验 workspace、工具、隐藏测试、trace 与报告的接线；它不是可替代真实模型评估的基线。
- S0 不安装依赖，也不更换环境；安装会影响可复现性。应先恢复 README 指定环境再执行验证。

## 4. 两条失败路径

1. **参数不合规**：模型工具参数进入 `ToolRegistry.execute` → Pydantic 验证失败 → 返回 `error_type="validation"` 的 `ToolResult` → Agent 将 JSON observation 放回消息历史 → 模型可据此调整。异常不必直接打断进程。
2. **测试仍失败或超时**：pytest 非零退出返回 `test_failure`，Agent 可收到结果继续决策；超时返回 `error_type="timeout"`，Agent 终止并标记 `timeout`。Docker daemon 无法启动则是执行错误，本轮无法实际观察 pytest 容器内路径。

## 5. 测试命令与实际证据

- 用 `D:\Anaconda3\envs\NN\python.exe -m pytest -q` 运行项目全量测试：`42 passed in 7.62s`。
- `docker version` 直接返回 Server Docker Desktop 4.55.0、Engine 29.1.3，说明 daemon 当时有响应。
- 代理会话固定集尝试记录 `0/5`：Docker 子进程无法读取用户目录配置或连接 Named Pipe，容器 pytest 没启动。这不是有效评测结果。
- 用户在本机 `(NN)` 终端复跑固定集：`5/5 passed`。当前 `reports/eval_results.csv` 记录五例 visible/hidden 全通过，模型 `scripted-oracle`、每例 6 steps、0 tokens。它验证评测链路，不证明真实模型能力。
- 用户本机在 Conda `NN` 的 fixture 目录运行 `python -m pytest -q`：`1 failed, 2 passed in 0.09s`，唯一失败为 `test_empty_input_returns_empty_config`，符合故意缺陷预期。该结果没有运行项目根测试。
- 用户粘贴的 `docker` 输出是 CLI 帮助；没有 daemon 版本或容器评测结果。
- 配置冒烟检查通过；全量 pytest 的 42 项也通过，包含 `.env` 加载和变量优先级回归。
- 历史结果：`reports/eval_results.csv` 记 5/5 scripted 成功，每案 6 步，0 tokens。不能称为真实模型成绩。
- fixture 初始证据：`evals/cases/parse-config/baseline-output.txt` 记录 1 failed、2 passed，失败名为 `test_empty_input_returns_empty_config`。

## 6. 用户亲手实验（约 15 分钟）

先打开 `evals/cases/parse-config/repo/config_parser.py` 和对应测试，解释空字符串为何会经 `split("\n")` 变成一行空文本，再触发 `ValueError`。在本机项目环境中运行：

```powershell
python -m pytest -q
```

手动实验已在 `.tmp/s0-manual-parse-config` 独立副本完成。先复现 `1 failed, 2 passed in 0.04s`，再把 `if not line and text:` 改成 `if not line:`，重跑 `python -m pytest tests -q` 得到 `3 passed in 0.01s`。测试文件没改，原始 fixture 也没改。`git diff` 只有这一个源码行差异。

## 7. 面试追问与参考回答

**问：Agent 和一次 LLM API 请求差在哪？**

答：Agent 有控制循环。模型提出结构化工具调用，程序验证并执行，把 observation 返回模型，再按测试、预算和终止规则决定下一步。模型本身不会直接执行本地工具。

**问：为什么 5/5 不等于模型成功率？**

答：固定 `scripted-oracle` 预先知道每案搜索词、路径、补丁和工具顺序。它验证评测设施，不测模型定位、编辑或策略能力，也没有模型随机性样本。

**问：如何避免旧测试结果误证新补丁？**

答：成功的 `apply_patch` 会清空 Agent 的 `last_test`。模型必须针对当前工作副本重新运行测试后才能以成功终止。当前实现通过状态失效约束，但还没有持久化补丁哈希与测试绑定记录。

## 8. 尚未实现或证实

在 S0 结束时，真实模型任务、完整运行元数据、补丁哈希与测试结果绑定、checkpoint 恢复和生产级沙箱均未完成或未证实。用户随后授权进入 S1；S1 的三项真实模型任务和当前限制见 `docs/learning/stage-S1.md`。S1 结果不属于 S0 验收证据。

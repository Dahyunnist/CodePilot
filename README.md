# CodePilot Lite

面向 Python 仓库的轻量修复 Agent。它通过 OpenAI 兼容接口调用模型，使用受限工具检查和修改干净的 Git 工作副本，在受限 Docker 容器中运行 pytest，并记录补丁、测试结果、轨迹和报告。

5 分钟演示、架构、安全边界和准确项目成果见[中文演示指南](docs/DEMO_5MIN_CN.md)。S14–S16 预算管理与公开 holdout 记录见[阶段结果](docs/learning/stage-S16-results.md)。

## 架构

```text
CLI -> 干净 Git 工作副本 -> Agent 循环 -> ModelClient
                                 |                |
                                 |                +-- 文本或工具调用
                                 v
                            ToolRegistry
          项目约定 / 项目图 / 符号调用检索 / 定向与完整测试
                                 |
                        Docker pytest + ToolResult
                                 |
                         JSONL 轨迹 + 报告
```

Agent 会在模型完成、错误、超时、预算用尽、需要审批或达到 `max_steps` 时停止。只有当前工作副本的最新测试通过，任务才算成功。应用新补丁会使之前的测试结果失效。

Agent 会按目标目录读取继承的 `AGENTS.md`，用 Python AST 项目图与带文件哈希的搜索证据定位代码。`suggest_tests` 和 `run_selected_tests` 可缩短迭代；最终仍必须运行完整配置测试。

## 环境准备

使用已有 Conda 环境：

```powershell
conda activate NN
cd E:\job\codepilot-lite
python -m pytest -q
```

首次构建受限测试镜像。该命令需要下载依赖，因此 Docker 必须能访问网络：

```powershell
docker build -f docker\runner.Dockerfile -t codepilot-runner:0.1 .
```

把项目目录中的 `.env.example` 复制为 `.env`，再填写模型配置。程序会自动读取项目根目录的 `.env`；同名进程环境变量优先。`.env` 已加入 Git 忽略规则，不要提交真实密钥。

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

DeepSeek 示例：

```env
LLM_API_KEY=填入你的密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_TIMEOUT_SECONDS=60
LLM_MAX_COMPLETION_TOKENS=1024
```

## 运行固定评测

以下命令从十二个干净 fixture 运行搜索、读取、基线测试、补丁、可见测试、隐藏测试，并生成轨迹和 CSV。案例覆盖跨文件契约与金额修复、多缺陷发票、批量导入原子性、游标分页、瞬时错误重试，以及以查询/写入调用次数为指标的性能目标：

```powershell
python -m evals.runner --docker-image codepilot-runner:0.1
```

该评测使用 `scripted-oracle`，温度为 `0.0`。它验证评测和工具流程，不衡量真实模型的推理能力。查看 `reports/eval_results.csv` 和 `reports/failure-analysis.md`。

## 用真实模型评测复杂修复

先确认当前目录是 `E:\job\codepilot-lite`、Conda 环境为 `NN`，并且 Docker Desktop 已启动且镜像已构建。运行：

```powershell
python -m evals.live_runner `
  --execution docker `
  --output-root reports/live-model-run `
  --work-root .tmp/live-model-run
```

默认命令会在三个基础 fixture 上运行真实模型。要运行所有复杂多文件、多缺陷和性能案例，可指定：

```powershell
python -m evals.live_runner `
  --execution docker `
  --case-ids multi-file-discount multi-bug-invoice notification-batch-performance bulk-audit-write-performance atomic-csv-import cursor-pagination retry-transient-only `
  --max-total-tokens 35000 `
  --max-elapsed 240 `
  --output-root reports/live-model-complex `
  --work-root .tmp/live-model-complex
```

模型 API 请求由本机发出；基线、修复后可见测试和隐藏测试由 Docker 容器执行。容器不联网。每项会生成 JSON 结果、JSONL 轨迹和测试日志，`results.csv` 和 `summary.md` 汇总通过/失败、输入/缓存/输出 Token、Agent 与全流程耗时、按模型费率估算的 API 费用，以及补丁 SHA-256。费用是估算值，实际账单以提供商平台为准。报告不会写入 API key。真实模型调用会产生 API 用量费用。

### 报告归档与本机运行日志

可复现的评测定义和 fixture 保存在 `evals/`；可分享的阶段结论保存在 `docs/learning/`。确定性评测的 `reports/eval_results.csv`、`reports/eval_results.md` 和 `reports/failure-analysis.md` 继续跟踪。新的 `reports/live-model-*`、`reports/public-*`、`reports/runs/` 和 `reports/traces/` 目录由 `.gitignore` 排除；这些原始运行记录可能包含本机绝对路径、测试输出、JSONL 对话轨迹或 SQLite 状态库，应留在本机。已有 Git 跟踪的历史文件不会因新增忽略规则自动取消跟踪。分享实验结果时，把经过审查的摘要写入 `docs/learning/`，并将可复现任务定义放入 `evals/`；不要提交原始本机日志。

成功时终端会显示 `Live model evaluation: 3/3 accepted`。若 Docker 无法连接，先运行 `docker version` 检查 Client 和 Server，再重试；若仍失败，可把命令输出和 `reports/live-model-run/results.csv` 发回排查。

### 单任务真实模型运行

准备一个临时 Git 仓库：

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
Copy-Item -Recurse evals\cases\parse-config\repo .tmp\parse-config-demo
cd .tmp\parse-config-demo
git init
git add .
git commit -m "初始故障样例"
cd ..\..
```

运行修复任务：

```powershell
python -m codepilot run `
  --repo .tmp\parse-config-demo `
  --task "parse_config 对空输入报错；请修复" `
  --test-command "python -m pytest tests -q" `
  --max-steps 8 `
  --max-test-attempts 3 `
  --max-elapsed 120
```

退出码：`0` 表示成功，`1` 表示 Agent 或测试失败，`2` 表示输入或配置无效，`3` 表示等待回写审批。默认只修改独立工作副本，源仓库保持不变。检查终端显示的工作副本路径、JSONL 轨迹、Markdown 报告和 Git 差异。

### 修复 CodePilot 目录之外的项目

`--repo` 可以指向任意本机 Git 仓库，包括 CodePilot 安装目录之外的公司项目。Agent 的搜索、读取、补丁和测试都针对该仓库的独立工作副本；默认不会写入源仓库。添加 `--apply-to-repo` 后，测试通过会暂停并等待人工审批：

```powershell
python -m codepilot run `
  --repo E:\work\company-service `
  --task "修复订单折扣金额计算错误" `
  --test-command "python -m pytest tests -q" `
  --apply-to-repo
```

审批时会显示补丁差异、基线提交和 SHA-256。运行状态保存在 `reports/run-state.sqlite`，Agent 每轮还会保存消息和工具结果；进程中断后用 `resume --continue-run` 接续。审批通过或拒绝：

```powershell
python -m codepilot resume --run-id <运行ID> --approve
python -m codepilot resume --run-id <运行ID> --reject
```

若进程在 Agent 工作时意外退出，运行 `python -m codepilot resume --run-id <运行ID> --continue-run --state-db reports/demo.sqlite` 接续。每轮消息与工具结果都保存在 SQLite；若中断发生在模型响应到达、检查点落盘之前，该轮模型请求可能重发。

回写前会检查源仓库干净且 HEAD 与工作副本基线一致，并核对等待期间补丁 SHA-256 未变化，再用 `git apply --check` 检查补丁。源仓库有未提交或未跟踪文件、运行期间被改动、补丁变化或无法干净应用，都会拒绝回写。Agent 测试失败时也不会进入审批。

主机模式只用于可信仓库的回退，需要显式审批：

```powershell
python -m codepilot run <其他参数> --execution host --approve-host-tests
```

真实模型评测也可用主机模式，但只应对受信任的 fixture 使用：

```powershell
python -m evals.live_runner `
  --execution host `
  --approve-host-tests `
  --output-root reports/live-model-run `
  --work-root .tmp/live-model-run
```

### 通过 MCP 调用 Agent 工具

`--tool-backend mcp` 会启动本地 MCP stdio 子进程。Agent 通过官方 Python SDK 的 `tools/list` 获取 schema，再以 `tools/call` 搜索、读取和运行测试；精确补丁和 Git 差异仍由宿主 ToolRegistry 处理。

```powershell
python -m codepilot run `
  --repo E:\work\company-service `
  --task "修复订单折扣金额计算错误" `
  --test-command "python -m pytest tests -q" `
  --tool-backend mcp
```

外部 MCP 客户端也可单独连接仓库工具服务：

```powershell
python -m codepilot.mcp_server `
  --repo E:\work\company-service `
  --test-command "python -m pytest tests -q" `
  --execution docker
```

stdio 协议占用标准输入和输出；诊断写到标准错误。服务只公开搜索、读取、差异、测试状态和隔离测试。它不公开源仓库回写。主机测试必须在启动服务时明确加 `--approve-host-tests`；Docker 测试无需主机授权。

## 工具边界

- 文件路径必须留在 `--repo` 指定的目标仓库内；目标仓库本身可以位于 CodePilot 安装目录之外。
- `.git`、`.env`、`*.key` 和 `*.pem` 文件不可读取或修改。
- `apply_patch` 只替换唯一匹配的 UTF-8 文本块。
- 命令工具只允许运行 pytest，不调用 shell。
- Docker 测试容器无网络、根文件系统与仓库挂载只读、删除额外 Linux capabilities、使用非 root 用户，并限制 CPU、内存、进程数和运行时间。pytest 临时文件写入受限的 `/tmp`。
- 每次运行都从已提交代码创建独立工作副本。
- 主机测试使用最小环境，不会收到模型 API key。
- 测试、搜索、读取和差异输出都有长度上限。
- 模型不能提交代码、删除文件、安装软件包或执行任意命令。

Docker 和命令白名单能降低风险，但不构成生产级沙箱。详见 `docs/security-limitations.md`。

## 运行状态

- `success`：最新测试通过，模型正常结束。
- `failed`：模型、工具或测试失败。
- `timeout`：工具执行超时。
- `budget_exceeded`：时间、token 或测试次数预算耗尽。
- `needs_approval`：主机操作尚未获批。
- `max_steps`：模型达到最大步骤数。

## 主要模块

- `codepilot/model.py`：OpenAI 兼容请求和响应适配。
- `codepilot/agent.py`：显式的推理、行动、观察循环和停止规则。
- `codepilot/tools/base.py`：工具基类、共享运行上下文、schema 生成和参数校验。
- `codepilot/tools/builtins.py`：内置工具类及默认工具清单。
- `codepilot/tools/registry.py`：工具实例与简单函数注册、`read_tools()` 元数据读取、审批和按名分发。
- `codepilot/tools/repo.py`：受限文件列表、搜索和读取。
- `codepilot/tools/edit.py`：精确文本替换和 Git 差异。
- `codepilot/tools/execute.py`：pytest 策略、超时、输出捕获和截断。
- `codepilot/workspace.py`：干净本地副本生命周期。
- `codepilot/tracing.py`：不写入源码或密钥值的 JSONL 轨迹。
- `codepilot/cli.py`：命令解析、依赖装配、退出码和报告。
- `evals/runner.py`：固定案例重置、修复、隐藏测试验证和 CSV 输出。
- `evals/live_runner.py`：真实模型固定案例运行和证据记录。

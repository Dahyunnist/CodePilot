# CodePilot Lite

面向 Python 仓库的轻量修复 Agent。它通过 OpenAI 兼容接口调用模型，使用受限工具检查和修改干净的 Git 工作副本，在受限 Docker 容器中运行 pytest，并记录补丁、测试结果、轨迹和报告。

## 架构

```text
CLI -> 干净 Git 工作副本 -> Agent 循环 -> ModelClient
                                 |                |
                                 |                +-- 文本或工具调用
                                 v
                            ToolRegistry
                   搜索 / 读取 / 补丁 / 测试 / 差异
                                 |
                        Docker pytest + ToolResult
                                 |
                         JSONL 轨迹 + 报告
```

Agent 会在模型完成、错误、超时、预算用尽、需要审批或达到 `max_steps` 时停止。只有当前工作副本的最新测试通过，任务才算成功。应用新补丁会使之前的测试结果失效。

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

以下命令从五个干净 fixture 运行搜索、读取、基线测试、补丁、可见测试、隐藏测试，并生成轨迹和 CSV：

```powershell
python -m evals.runner --docker-image codepilot-runner:0.1
```

该评测使用 `scripted-oracle`，温度为 `0.0`。它验证评测和工具流程，不衡量真实模型的推理能力。查看 `reports/eval_results.csv` 和 `reports/failure-analysis.md`。

## 用真实模型复核三项修复

先确认当前目录是 `E:\job\codepilot-lite`、Conda 环境为 `NN`，并且 Docker Desktop 已启动且镜像已构建。运行：

```powershell
python -m evals.live_runner `
  --execution docker `
  --output-root reports/live-model-run `
  --work-root .tmp/live-model-run
```

这会使用 `.env` 中的模型配置，在三个干净 fixture 上运行真实模型。模型 API 请求由本机发出；基线、修复后可见测试和隐藏测试由 Docker 容器执行。容器不联网。每项会生成 JSON 结果、JSONL 轨迹和测试日志，汇总写入 `results.csv`，包含模型名、token 数、状态、测试结果和补丁 SHA-256。报告不会写入 API key。真实模型调用会产生 API 用量费用。

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

退出码：`0` 表示成功，`1` 表示 Agent 或测试失败，`2` 表示输入或配置无效。源仓库不会被直接修改。检查终端显示的工作副本路径、JSONL 轨迹、Markdown 报告和 Git 差异。

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

## 工具边界

- 文件路径必须留在目标仓库内。
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
- `codepilot/tools/registry.py`：工具 schema、`read_tools()` 元数据读取、参数校验和分发。
- `codepilot/tools/repo.py`：受限文件列表、搜索和读取。
- `codepilot/tools/edit.py`：精确文本替换和 Git 差异。
- `codepilot/tools/execute.py`：pytest 策略、超时、输出捕获和截断。
- `codepilot/workspace.py`：干净本地副本生命周期。
- `codepilot/tracing.py`：不写入源码或密钥值的 JSONL 轨迹。
- `codepilot/cli.py`：命令解析、依赖装配、退出码和报告。
- `evals/runner.py`：固定案例重置、修复、隐藏测试验证和 CSV 输出。
- `evals/live_runner.py`：真实模型固定案例运行和证据记录。

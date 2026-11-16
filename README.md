# CodePilot Lite

面向 Python 仓库的代码修复 Agent 原型。它通过 OpenAI 兼容接口调用模型，使用注册工具搜索、读取和修改仓库文件，在独立 Git 工作副本中运行 pytest，并记录 JSONL 轨迹和结果。

本候选仅包含已审查运行源码、依赖清单、必要测试和 CP-3/CP-4 阶段摘要。它不包含隐藏测试、holdout、历史 reports、账单导出或完整评测集。

## 架构

```text
工程师任务
  -> CLI 与 ModelClient
  -> Agent: 请求 -> 校验工具调用 -> 执行工具 -> 观察 -> 继续或结束
  -> 独立 Git 工作副本
  -> 受限 Docker pytest
  -> RunResult、JSONL trace、补丁差异
```

`ToolRegistry` 负责向模型提供工具 schema，并校验和分发调用。Agent 只在最新完整测试通过后报告成功。外部仓库写回需单独审批和复核。

## 环境准备

需要 Python 3.11 或更高版本，以及 Docker Desktop Linux 容器模式。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
```

编辑本机 `.env`：

```env
LLM_API_KEY=填入本机密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_TIMEOUT_SECONDS=60
LLM_MAX_COMPLETION_TOKENS=1024
```

`.env` 已被 Git 忽略。不要把密钥放入命令行、测试容器或提交内容。API 请求会产生费用。

首次运行 Docker 测试前构建受限镜像：

```powershell
docker build -f docker\runner.Dockerfile -t codepilot-runner:0.1 .
```

## 运行 Agent

```powershell
python -m codepilot run `
  --repo <目标仓库> `
  --task "修复指定问题并运行相关测试" `
  --test-command "python -m pytest tests -q" `
  --execution docker `
  --docker-image codepilot-runner:0.1
```

运行副本与源仓库隔离。模型只能调用已注册工具；测试命令受 pytest 策略限制。Trace 不保存源码、补丁正文、标准输出、标准错误或密钥值。测试容器无网络并受资源限制，但 Docker Desktop 和宿主内核仍处于信任边界。

## CP-3/CP-4 离线验证

```powershell
python -m pytest `
  tests/test_agent.py `
  tests/test_cli_e2e.py `
  tests/test_repository_tools.py `
  tests/test_run_graph.py `
  tests/test_security.py `
  tests/test_skills.py `
  tests/test_skill_ablation.py `
  tests/test_tracing.py -q
```

CP-4 固定 fixture 只验证 Skill 输入契约、工具白名单、预算和退出条件投影。它不调用模型，不能证明真实修复成功率、费用或耗时。

## 许可与阶段状态

原项目没有提供项目级 `LICENSE` 文件或明确许可声明。本候选不擅自添加许可；发布或允许第三方复用前，项目所有者需要确定许可。

CP-2 真实模型与 baseline 评测仍被项目级用量、余额和完整预算证据阻断。此候选不含 CP-2 隐藏测试或账单对象。

架构与安全边界见[架构说明](docs/architecture.md)和[安全限制](docs/security-limitations.md)。阶段证据见[净发布候选摘要](docs/learning/release-cp3-cp4-summary-2026-11-16.md)。

# CodePilot Lite：5 分钟演示

## 演示目标

用一个小型真实模型修复展示完整循环：读取任务仓库、查找代码、修改工作副本、Docker 测试、保留轨迹与报告。模型 API 在本机调用；pytest 在隔离 Docker 中执行。

## 开始前

- 打开 Docker Desktop。
- 激活 `NN` 环境。
- 确认项目根目录 `.env` 已配置 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL`。演示不显示或复制密钥。
- 确认镜像 `codepilot-runner:0.1` 已构建。

## 时间安排

### 0:00–0:30：检查环境

```powershell
cd <path-to-CodePilot>
conda activate NN
python -c "import sys; print(sys.executable)"
docker version
```

展示 `NN` 的 Python 路径，以及 Docker Client 和 Server 均有版本信息。

### 0:30–1:15：跑确定性回归

```powershell
python -m evals.runner --docker-image codepilot-runner:0.1
```

展示固定案例结果。这里的 `scripted-oracle` 用于验证工具流程，不代表真实模型推理成绩。

### 1:15–3:30：运行一次真实模型修复

```powershell
python -m evals.live_runner `
  --case-ids parse-config `
  --execution docker `
  --docker-image codepilot-runner:0.1 `
  --max-total-tokens 18000 `
  --max-steps 8 `
  --max-elapsed 120 `
  --output-root reports/demo-five-minute `
  --work-root .tmp/demo-five-minute
```

展示 Agent 轨迹里的搜索、读取、补丁和测试调用。模型运行会产生 API 费用；预算上限用于限制单次演示用量。

### 3:30–4:30：检查结果

打开 `reports/demo-five-minute/summary.md` 和 `results.csv`。每个案例的 JSONL 轨迹、补丁、测试日志、Token 用量、估算费用及耗时都在同一报告目录。

Agent 在独立 Git 工作副本里修改。普通评测不会写源仓库。真实模型结果可能成功，也可能因预算、模型输出或测试失败；报告原样记录结果。

### 4:30–5:00：展示外部仓库审批写回

外部仓库完整流程已在 S3 实测：仓库位于 CodePilot 项目目录之外；Agent 在副本修复并通过 Docker 测试；CLI 暂停等待审批；第二个 CLI 进程批准后检查源仓库状态、HEAD、补丁 SHA 和 `git apply --check`；最后在源仓库复测通过。记录见 `docs/learning/stage-S3-project-context.md` 与 `reports/live-model-20261020-s3-writeback-external/`。

## 架构与信任边界

```text
工程师
  │ 中文任务、仓库路径、测试命令
  ▼
CLI ──读取配置──> 本机 ModelClient ──HTTPS──> 模型服务
  │                    ▲
  │                    │ 工具调用/回复
  ▼                    │
Agent 循环 ──> ToolRegistry：搜索、读取、项目图、补丁、pytest
  │                    │
  ├── SQLite 检查点 + JSONL 轨迹
  │
  ├── Git 基线与独立工作副本
  │       └── 独立验证副本：基线测试 + 生产源码补丁
  │                 └── Docker：断网、非 root、只读、资源限制
  │
  └── 可选回写：暂停 → 人工批准 → 基线/补丁复核 → 写入源仓库
```

- API key 由本机模型进程读取，不挂载进测试容器。
- Agent 不能运行任意 shell 命令；工具验证仓库内路径，测试命令限制为 pytest。
- Docker 容器断网、只读、非 root，并设置 CPU、内存、进程和时间限制。
- 预算后独立验证从干净基线建立副本。Agent 修改的测试或 pytest 配置不会进入该副本。
- 外部仓库默认不写入。回写需人工批准，并验证仓库干净、HEAD 未变、补丁哈希未变且可通过 `git apply --check`。
- Docker 与命令白名单能降低风险，不等于生产级沙箱。接入公司仓库前仍需本地安全审查、权限设计和代表性评测。

## 可用于简历的准确表述

- 构建 Python 代码修复 Agent 原型：支持 OpenAI 兼容模型、工具注册与 ReAct 工具循环、SQLite 检查点、JSONL 轨迹、独立工作副本和 pytest 验证。
- 实现人工审批的外部仓库补丁回写，并对源仓库状态、HEAD、补丁哈希及 `git apply --check` 做校验；S3 实测回写后 3 项测试通过。
- 建立公开上游缺陷评测流程：冻结源码归档、可见/隐藏测试与 Docker 环境；S13 两个复测案例通过，S15 与 S16 holdout 正式验收均为 0/1，未将预算后手动验证记为 Agent 成功。
- 当前仍是研究原型，不宣称已达到生产级大型代码库可靠性；真实任务中仍存在上下文 Token 预算耗尽问题。

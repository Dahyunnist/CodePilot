# S0 基线审计

## 数据流

```text
CLI Task/config -> WorkspaceManager 克隆提交态 -> Agent 显式循环
-> ModelClient -> ToolRegistry 参数校验/审批 -> 工具读改
-> Docker pytest -> 当前补丁哈希与测试结果判定 -> RunResult
-> Markdown/终端报告 + JSONL Trace + 可审查 diff
```

关键位置：`codepilot/cli.py` 解析与编排；`codepilot/workspace.py` 建立干净工作副本；`codepilot/agent.py` 控制循环、预算和成功判定；`codepilot/model.py` 负责 OpenAI 兼容调用；`codepilot/tools/registry.py` 与 `tools/` 定义工具；`tools/execute.py` 只接受受限测试命令并构造 Docker 调用；`run_graph.py` 持久化审批/恢复；`tracing.py` 写 JSONL；`report.py` 生成 Markdown。

## 已实现与边界

已实现工具注册和 schema、workspace 隔离、读取/补丁/测试工具、模型/工具追踪、Docker 资源约束、预算状态、patch 后清除旧测试结论、审批门和 checkpoint 恢复。现有 Docker 不是强安全沙箱；宿主 Git/内核仍在信任边界。cancel 接口不存在，重试设为 0。

## 基线测试证据

在 Codex Windows 沙箱，分组安全测试 `test_prompts.py test_state_transitions.py test_repository_tools.py test_execute.py test_tracing.py`：45 passed、1 skipped；skip 是 junction 权限拒绝。`test_workspace.py`：3 passed、2 failed，失败来自 Git for Windows/MSYS `NtCreateDirectoryObject(...): 0xC0000022`。用户已报告原生 PowerShell CLI E2E 通过，但完整原生 pytest 尚未回报。不能将这些结果合并成全套通过。

脚本化 oracle 的 5/5 仅验证评测链路。CP-2 SWE-bench Lite 20题 metadata 尚未物化；没有项目真实任务总体成功率或真实模型成本结论。

## 本阶段风险/缺项

模型调用错误分类已有基础，但全套 Windows 测试仍需宿主复核。Trace 有 JSONL sink，无独立持久化 fallback。安全审批、Docker 和 checkpoint 已有路径，但 cancel 不支持。CP-1 机制 fixture 只反映 synthetic evidence；CP-2 数据需要用户完成下载与 SHA freeze；真实模型评测需先核实成本账本及预算。

## 用户可复现实验

激活 Conda `NN` 后运行：`python -m pytest -q --basetemp=.tmp\\pytest-native`。预期需关注完整汇总；若 Workspace clone 报 MSYS 权限错误，请贴首个完整 traceback。先不要把 scripted-oracle 结果计作模型能力。

## 面试追问

1. 为什么成功必须绑定最新测试？补丁改变源码后旧测试结论即失效。
2. Docker 安全边界是什么？资源受限容器降低风险，但宿主 Docker Desktop/内核仍可信。
3. 工具如何限制模型？注册表用 Pydantic schema 校验参数，敏感动作要求审批，测试命令走白名单。

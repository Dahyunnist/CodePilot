# CP-3：独立测试与 Agent 轨迹关联

## 数据流

每个评测案例先创建 `TraceLogger`，再运行冻结基线测试。基线、Agent 运行、独立可见测试和独立隐藏测试共享同一 `run_id` 与 `trace_id`。测试阶段各有独立 span，并挂到案例评测根 span。

阶段事件只记录阶段名、case ID、执行模式、结果状态、退出码、耗时、错误类型和测试命令 SHA-256。事件不记录测试命令原文、工作区路径、stdout、stderr、题目 gold 或密钥。持久化测试日志也只保留输出长度与 SHA-256。独立测试异常只记录异常类型，然后继续向上抛出。

## 生命周期

`evaluation_started` 创建案例根 span。Agent 的 `run_started` 复用根 span。Agent 结束时，`run_finished` 不会提前关闭评测根 span。独立测试结束后，`evaluation_finished` 关闭根 span。

当基线无法运行或失败型任务的基线意外通过时，评测会保留同一案例 ID、运行 ID 和 trace 文件，并以 `blocked` 结束。此状态不会计为 Agent 成功或测试失败。

恢复任务时，只有检查点保存了工作区 SHA-256 且当前工作区仍匹配，才复用先前的成功测试结果。旧检查点缺少 SHA 或工作区已改变时，系统清除旧结果、记录失效原因并重新测试，避免把未经验证的补丁当作已通过。

## 验证

运行 CP-3 相关 Agent 与执行测试：

```powershell
python -m pytest tests/test_agent.py tests/test_execute.py -q
```

本轮 77 项通过。上下文预算、CP-2 基准、沙箱命令、安全路径及关键工具并发回归组合为 157 项通过、1 项因宿主不允许创建 Windows junction 跳过。该结果不代表完整仓库测试全部通过。

新增用例检查基线、可见测试和隐藏测试的 ID、父子 span、异常类型及敏感输出不进入 trace；恢复用例覆盖工作区变更和旧检查点缺少 SHA 两种情况。完整 CLI E2E 本轮有 7 项被宿主 Git/SSH 命名对象权限阻断；不能据此宣称 CLI 全通过。

## 亲手实验

在具备 Docker Engine 的 PowerShell 中，使用 CP-2 的安全发布工作树运行：

```powershell
python -m pytest tests/test_live_runner.py -q
```

若准备执行真实评测，先按账本与费用门禁确认余额，再使用已冻结、可运行的 Docker 基线。查看生成的 `reports/traces/<run-id>.jsonl`，核对同一 `trace_id` 下的 `baseline`、Agent 工具事件、`independent_visible` 与 `independent_hidden` 阶段。不要提交评测输出、`.tmp` 或 `verification-artifacts`。

## 面试追问

- 为什么独立测试需要和 Agent 工具调用分开记录？
- 为什么 trace 存命令哈希而不存命令和测试输出？
- 基线被环境阻断时，如何避免把它误计为 Agent 失败？
- 为什么 `run_finished` 不能关闭整个评测 trace？

## 边界

本阶段只验证本地事件关联和元数据脱敏，不证明 Docker 执行成功，不验证 OpenTelemetry exporter 的端到端导出，也不包含模型修复评测。真实基线仍须由用户主机运行。

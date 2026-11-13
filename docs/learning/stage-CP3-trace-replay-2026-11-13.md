# CP-3 Trace 回放离线切片（2026-11-13）

新增 JSONL 顺序回放回归：模型响应后记录工具开始/结束；timeout 作为失败结果保留；下一轮重试后，越界 patch 被 `PathPolicyError` 拒绝；敏感 token 不进入 trace。现有 Agent 注入测试另行真实调用 `read_file` 与 `apply_patch`，断言外部写入未发生且 trace 保留拒绝类型。

运行：

```powershell
python -m pytest tests/test_tracing.py::test_trace_replay_preserves_timeout_retry_rejection_and_redaction_order tests/test_agent.py::test_prompt_injection_cannot_patch_outside_workspace_or_leak_into_trace -q
python -m pytest tests/test_tracing.py tests/test_agent.py -q
```

本切片只验证 scripted/offline trace 和安全拒绝路径；未运行真实模型任务、Docker 或 CP-2 SWE-bench 评测。CP-2 仍未达到真实仓库/模型验收。

## `apply_patch` 的 OTel 子 span

Agent 执行 `apply_patch` 时，在通用工具 span 内创建 `codepilot.workspace.patch` 子 span。开始事件只记工具名和 trace 身份；完成事件只记成功状态与错误类型，不记 patch 正文、文件内容或参数。这样可在 trace 中区分“工具调用失败”和“工作区 patch 被策略拒绝”。

```text
run span
└─ model call span
   └─ tool.execute span (apply_patch)
      └─ workspace.patch span
```

成功时 patch span 正常结束。工具返回拒绝时，span 标记错误状态并保留 `PathPolicyError` 等类型。工具执行抛出异常时，Agent 记录 `tool_error` 后继续向上抛出；上层仍负责将任务标记失败。

复现：

```powershell
D:\Anaconda3\envs\NN\python.exe -m pytest tests/test_tracing.py tests/test_agent.py -q -p no:cacheprovider --basetemp=.tmp\pytest-cp-patchspan-final
```

结果：**64 passed**；`git diff --check` 通过。新增集成回归同时覆盖成功与路径拒绝，并核对子 span 父链和 patch 正文脱敏。此为 FakeTracer 离线验证，不等同于连接真实 OTLP Collector 的端到端验收。

亲手实验：将测试中的成功结果改为 `ToolResult(ok=False, error_type="PathPolicyError")`，运行单个参数化测试；观察子 span `codepilot.error_present`，并确认 JSONL 与 OTel 属性均无 patch 正文。恢复改动后重跑整组测试。

面试追问：

1. 为什么额外加子 span？让 patch 的开始/结束和父工具调用分层，方便定位失败阶段，同时保留 trace 因果关系。
2. 为什么不记录 diff 或 patch？代码可能含业务秘密、密钥或恶意注入文本；排障只需状态、耗时和错误分类。
3. FakeTracer 能证明什么？它验证 Agent 调用路径、父子关系、结束状态和脱敏属性；它不能证明 OTLP 网络导出、Collector 存储或生产采样行为。

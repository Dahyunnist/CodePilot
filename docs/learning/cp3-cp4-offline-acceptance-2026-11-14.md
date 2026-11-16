# CP-3 / CP-4 离线验收补充（2026-11-14）

## 追踪覆盖

JSONL 是本地持久记录；每条事件写入后才尝试镜像到 OpenTelemetry。导出器异常现在会被隔离，不能反向中断 Agent。可复核字段为 `run_id`、`trace_id`、`span_id`、`parent_span_id` 和事件顺序。默认 `trace_id` 等于 `run_id`，调用方也可单独传入 trace ID。

| 工作环节 | JSONL 事件 / span | 记录边界 |
| --- | --- | --- |
| Agent 运行 | `run_started` / `codepilot.run`，`run_finished` 关闭 | 任务 ID、状态、用量等摘要 |
| 模型调用 | `model_budget_reserved` / `codepilot.model.call`；`model_finished` 或 `model_failed` 结束 | token 与状态摘要；不记录 prompt 或回复正文 |
| 工具选择和执行 | `tool_started`、`tool_finished` / `codepilot.tool.execute` | 工具名、参数键、有限路径摘要、耗时、退出码和错误类别；不记录完整参数、stdout/stderr |
| 补丁 | `patch_started`、`patch_finished` / `codepilot.workspace.patch` | 父级工具 span、成功状态、错误类别；不记录 diff 或补丁正文 |
| 测试 | `run_tests` 工具事件 | 作为工具执行记录，包含成功/失败、退出码、耗时和错误类别 |
| 写回审批和执行 | `writeback_approval_requested/decided`、`writeback_started/finished` / 两类 writeback span | 审批决定和结果摘要，不记录补丁内容 |

密钥字段写 `[REDACTED]`，私密正文类字段写 `[OMITTED]`；模型与工具原始正文不会进入 trace。新增回放覆盖 read → 测试超时 → 越界补丁被拒 → 再次测试成功，并模拟 OpenTelemetry 导出器故障，验证 JSONL 仍完整保留因果顺序、错误类别与父子关系。它是离线确定性测试，不是 collector 可用性或真实模型效果证明。

## CP-4 Skills 可复现演示

运行 `python -m evals.skills.ablation` 可得到两个冻结案例的 JSON 报告。每例包括任务说明、测试命令、仓库路径、Skill 目标、工具白名单、退出条件、步数/测试次数/token 上限，以及固定 no-skill/skill 工具序列和约束检查结果。输出固定声明 `deterministic_fixture=true`、`model_calls=0`。当前固定序列只是演示输入与策略约束的对照，不测量模型行为、修复成功率、成本或耗时，也不据此声称 Skill 有效。

## 验收命令

```powershell
python -m pytest tests/test_tracing.py tests/test_skill_ablation.py -q --basetemp=.tmp\pytest-cp3-cp4
python -m evals.skills.ablation
```

本轮不调用 API、不运行 Docker、不读取或改动未跟踪的外部 `django_10924/` 样例目录。

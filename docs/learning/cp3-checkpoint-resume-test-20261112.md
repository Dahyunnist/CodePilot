# CP-3 Checkpoint 恢复事件验证

## 数据流

CLI `resume` 先记录 `resume_requested`，再调用持久化恢复函数。只有恢复返回状态后，CLI 才记录 `checkpoint_resume`；成功状态标为 `resumed`，审批中断标为 `waiting_approval`。

## 失败路径

1. 有效审批 checkpoint 恢复成功：轨迹恰有一条 `checkpoint_resume`。
2. 状态库中没有 checkpoint：CLI 返回错误并记录请求事件，不伪报恢复成功。
3. 同一 checkpoint 被重复恢复：保留现有拒绝行为，不重复执行回写。

事件只含运行 ID、恢复阶段和 outcome，不记录仓库路径、补丁或原始 checkpoint 状态。

## 复现

```powershell
python -m pytest -q tests/test_cli_e2e.py -k "can_apply_successful_patch_to_external_repository or missing_checkpoint_does_not_emit_checkpoint_resume"
```

本轮结果：2 passed。使用临时 Git 仓库和 scripted model；没有发送真实模型请求。它证明 CLI 恢复事件边界，不证明跨进程崩溃恢复的完整故障覆盖。

## 亲手实验

先运行上述成功恢复用例，查看临时 trace 中的 `checkpoint_resume`。再运行缺失 checkpoint 用例，确认只有 `resume_requested`，没有恢复成功事件。

## 面试要点

- 为什么在恢复函数返回前不能记 `checkpoint_resume`？
- 如何区分审批挂起与真正恢复？
- 哪些 checkpoint 字段可能包含秘密，为什么轨迹不直接序列化它们？

# CP-1 离线上下文预算记录

工具输出超过 Agent 观测上限时，ToolResult 现在记录 `truncation_reason=agent_context_observation_limit`、裁切前后字符数。原始工具执行结果未修改；字段只由 Agent history 限长副本填充。确定性样本测试保留 stdout 首尾，校验原始/保留计数。

验证命令：`python -m pytest tests/test_agent.py::test_tool_observations_are_bounded_for_model_context tests/test_agent.py::test_future_budget_names_patch_test_and_final_reserves tests/test_context_selector_offline.py -q --basetemp=.tmp\\pytest-basetemp`，结果 3 passed。预算预留仍为 patch/test/final = 512/1024/512 tokens；离线样本不代表真实模型任务通过率。

## CP-1 组合回归补充（2026-11-14）

审计确认这些行为已有实现，无需改生产代码：未来输出保留 patch/test/final 共 512/1024/512 tokens；预算不够时 Agent 在模型调用前 fail closed；超长工具输出保留首尾，填 `truncation_reason=agent_context_observation_limit`、原始/保留字符数，并在文本中写明截断及原文长度；相同 SHA 的旧工具消息替换为哈希指针，最新消息保留全文。

新增一条组合回归 `tests/test_context_selector_offline.py::test_cp1_budget_truncation_and_duplicate_sha_contract`，同时断言预算预留、输出上限/省略原因/首尾保留、重复 SHA 指针和最新证据保留。新增测试 **1 passed**。修改仅涉及测试和学习记录。

复核基线：修改前相关 CP-1 测试 **11 passed**。首次扩大组 `tests/test_agent.py`、`tests/test_context_selector_offline.py`、`tests/test_cp1_context_offline.py`、`tests/test_live_runner.py` 为 **85 passed、1 failed**；失败是 Codex 临时目录复制合成 Git `.git/objects` 时文件消失。单项改用全新 `E:\job\cp1-context-single-20261114` 后 **1 passed**。随后全组改用全新 basetemp 后 **86 passed in 251.48s**：

```powershell
D:\Anaconda3\envs\NN\python.exe -m pytest -p no:cacheprovider tests/test_agent.py tests/test_context_selector_offline.py tests/test_cp1_context_offline.py tests/test_live_runner.py -q --basetemp E:\job\cp1-context-suite-20261114
```

没有调用模型；测试使用确定性 fixture/fake model。两个新建 basetemp 目录均保留，未接触仓库 `.tmp/` 或 `verification-artifacts/`。

限制：这些测试证明代码机制和 Windows 测试路径，不证明真实模型 tokenization、修复成功率或 selector 对真实任务的净收益。CP-1 仍部分完成；历史两组 live pair 均 `budget_exceeded`。

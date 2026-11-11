# CP-1 离线上下文预算记录

工具输出超过 Agent 观测上限时，ToolResult 现在记录 `truncation_reason=agent_context_observation_limit`、裁切前后字符数。原始工具执行结果未修改；字段只由 Agent history 限长副本填充。确定性样本测试保留 stdout 首尾，校验原始/保留计数。

验证命令：`python -m pytest tests/test_agent.py::test_tool_observations_are_bounded_for_model_context tests/test_agent.py::test_future_budget_names_patch_test_and_final_reserves tests/test_context_selector_offline.py -q --basetemp=.tmp\\pytest-basetemp`，结果 3 passed。预算预留仍为 patch/test/final = 512/1024/512 tokens；离线样本不代表真实模型任务通过率。

# CP-3 命令授权拒绝测试

补充拒绝性回归：向 `run_tests` 提交任意 Python `-c` 写文件命令，验证策略返回 `policy` 且副作用标记文件未创建。白名单 Django runner 仍接受；现有 timeout 用例仍通过。本测试只验证命令策略拒绝，不模拟外部副作用成功。

命令：`python -m pytest tests/test_execute.py::test_run_tests_rejects_command_with_side_effect_before_execution tests/test_execute.py::test_normalize_test_command_accepts_bounded_django_runner tests/test_execute.py::test_run_tests_reports_timeout -q --basetemp=.tmp\\pytest-basetemp`。结果 3 passed。

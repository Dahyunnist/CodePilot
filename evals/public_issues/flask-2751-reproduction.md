# Flask #2751 离线最小复现

来源：Flask #2751（已关闭历史问题），官方代码对照：
- 问题：https://github.com/pallets/flask/issues/2751
- Flask 1.0.1：`flask/cli.py` 的 `routes_command` 在空规则上执行 `max(...)`。
- Flask 1.0.2：先检查空规则，输出 `No routes were registered.` 后返回。

本测试 `test_flask_2751_minimal.py` 抽取上述两段控制流，以 Click 命令验证空输入的异常与修复行为。它是离线最小行为复现，不是安装 Flask 1.0.1/1.0.2，也不是 Flask 仓库 E2E。历史依赖安装因受限包索引失败，未声称完整上游复现。

复现命令（项目 Conda NN）：
`python -m pytest evals/public_issues/test_flask_2751_minimal.py -q`

冻结状态仍为 pending，直到获取固定 SHA、核对许可证并完成真实上游 base/fix 测试。

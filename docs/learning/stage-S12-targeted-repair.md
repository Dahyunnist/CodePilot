# S12：定点缺陷的快速修复路径

## 改动

系统提示为用户已给出单个文件、符号和目标行为的任务设定初始读取上限：首次补丁前最多 4 次只读工具调用，优先检查目标实现、相关测试和直接调用点。测试失败后，允许按新证据继续定位。多文件或根因未知任务仍按需探索。

这是模型提示策略，当前没有在 Agent 运行时强制计数；单次遵循结果不代表每次都会遵守。若此预算需要成为生产硬约束，后续需实现可配置、按任务类型适用的运行时调用预算。

## Click 8.3.1 上游案例结果

DeepSeek V4 Flash + Docker，修复 [Click issue #3145](https://github.com/pallets/click/issues/3145)：

- 完整状态：`success`，12 步，77,864 Tokens；输入 75,005，缓存输入 51,968，输出 2,859。
- 估算费用 `$0.010654`；Agent 23.2 秒，全流程 29.7 秒。
- 首次定位阶段 4 次 `read_file`、3 次 `search_code`，之后应用 3 个精确补丁。
- Agent 配置测试、独立可见测试和隐藏测试均通过。可见套件 38 passed，隐藏套件 3 passed。
- 补丁 SHA-256：`23b40ed5847ac6a02fde8a05002b63f8e84ad5948057a6ef5804242bdb5d9550`。

逐轮轨迹、补丁、Token、费用和测试输出见 `reports/public-click3145-s12-read-budget/`；奖励评分见 `reports/trajectory-score-s12/`。

## 验证

- Click 基线可见回归：2 项失败，36 项原有测试通过。
- 修复后 Agent 测试和独立可见测试：各 38 passed；隐藏测试：3 passed。
- NN 完整测试：`D:\Anaconda3\envs\NN\python.exe -m pytest -q --basetemp .tmp/pytest-s12-full`，**100 passed**。

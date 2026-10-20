# S8 阶段记录：分层仓库上下文与检索

## 目标

让 Agent 面对多包 Python 项目时按需理解目录约定和代码关系，并把检索证据绑定到内容版本；控制索引规模、秘密外传和测试验收边界。

## 工作流

1. 启动任务时只把根目录 `AGENTS.md` 注入用户任务上下文；内容限 12,000 字符，文件大于 48 KB 不读。内容先脱敏，再附 SHA-256 来源。根规则和工具输出都被标记为不可信项目数据。
2. 模型可用 `read_project_instructions(path)` 加载目标目录的继承规则。工具从仓库根到目标目录逐级读取 `AGENTS.md`；路径经过符号链接解析和根目录限制。每份规则附文件哈希，合并最多 24,000 字符。
3. `project_map`、`search_symbols` 和 `find_references` 建立并查询 Python AST 索引，输出模块/定义/调用位置和来源文件 SHA-256。索引只读仓库内 Python 源，忽略 `.git`、`.tmp`、虚拟环境、构建目录、dotenv 和私钥；限制 2,000 文件、单文件 1 MB、总量 50 MB。
4. 索引内容版本由排序后的路径及文件内容 SHA-256 聚合。每次调用先计算当前内容摘要；若内容变化，缓存索引作废并重建。文件相同则复用当前 `ToolContext` 缓存。反射、动态导入、别名传播和运行时分派不是静态 AST 可完整推导的关系。
5. `search_code` 行结果带文件 SHA-256；`read_file` 返回仓库相对路径和文件 SHA-256。模型可以回到相同内容验证引用，补丁改变内容后哈希变化。
6. `suggest_tests` 读取当前未提交 Python 差异，通过测试文件名、导入和调用点提出候选。该建议是启发式，不是覆盖率或依赖证明。
7. `run_selected_tests(paths)` 只允许仓库内 pytest 文件或 `tests` 目录，适合短反馈。它会清除 Agent 的最终测试验收状态；模型随后必须运行任务配置的完整 `run_tests` 才能报告成功。定向与全量测试共用 `max_test_attempts`。

## 数据边界与失败路径

- 仓库代码、`AGENTS.md`、pytest 输出、MCP 输出都可能包含提示注入；系统提示把它们标为不可信。真正的权限仍来自固定工具集、路径规则、pytest 限制、Docker 隔离与审批写回。
- 常见 API key、访问令牌、密码、Bearer token、私钥块会在工具结果和项目约定进入模型前脱敏。文件名规则继续拒绝 `.env.*`、`.key`、`.pem`。
- 根外路径、越界符号链接和秘密路径返回工具错误。项目约定超过上限时跳过该文件或按字符截断。Python 语法错误文件计入索引解析失败数，不会被当作有效模块。
- 项目超过索引上限时停止继续纳入，项目图必须以实际索引文件数判断覆盖范围。测试选择没有静态匹配时退回仓库现有测试文件；仍必须运行完整配置套件。
- 候选测试失败不会自动判任务失败；Agent 可以继续诊断。没有完整测试通过就不能用 targeted run 的结果宣称任务通过。

## 关键实现与测试

- `codepilot/repository_index.py`：项目约定继承、AST 索引、缓存摘要、模块图、符号/调用检索和候选测试。
- `codepilot/tools/builtins.py`：工具参数 schema、路径校验与定向 pytest 执行。
- `codepilot/agent.py`：定向测试不满足最终验收；定向与完整测试尝试共享预算。
- `codepilot/tools/repo.py`、`codepilot/security.py`：来源文件哈希、敏感路径和文本脱敏。
- `codepilot/mcp_client.py`：MCP 模式保留本地 AST/指导/定向测试工具，文件读取/搜索/完整测试继续按 MCP allowlist 路由。
- `tests/test_repository_index.py`：目录规则继承、内容版本失效、符号/调用检索、测试建议和定向测试安全边界。
- `tests/test_agent.py`：定向测试后直接结束会失败；后续完整套件通过才可成功。
- `tests/test_mcp.py`：MCP 混合注册表能发现本地项目上下文工具。

## 验证结果

- NN 完整回归：`D:\Anaconda3\envs\NN\python.exe -m pytest -q`，**95 passed**。
- DeepSeek V4 Flash + Docker 实跑 `multi-bug-invoice`：**success，独立可见和隐藏测试均通过**；9 步，58,246 Tokens（输入 52,443，缓存输入 46,720，输出 5,803），估算费用 **$0.008961**，Agent 31.2 秒，全流程 34.1 秒。Agent 实际使用 `read_project_instructions`、`project_map`、`suggest_tests`、`run_selected_tests`，随后运行完整 `run_tests`。工具调用轨迹在 `reports/live-model-20261020-s8/`。
- 本任务用量高于 S3 相同案例的成功记录；新工具 schema 与更细的上下文可能增加输入。单个 run 不能证明平均成本，需要在 S9 固定仓库任务集上重复统计。

## 10 分钟动手实验

1. 在临时仓库添加根目录 `AGENTS.md` 与 `billing/AGENTS.md`，用 `read_project_instructions` 读取 `billing/pricing.py`，检查继承顺序和 SHA-256。
2. 用 `project_map` 看包分布，用 `search_symbols` 找 `create_invoice`，用 `find_references` 找调用方。
3. 记录项目图内容版本；改函数名或实现后再次运行，确认索引摘要变化、旧符号消失。
4. 改一个模块文件，运行 `suggest_tests`，再用 `run_selected_tests` 跑候选；尝试直接给 Agent 最终回答，确认必须继续跑完整套件。
5. 在源码或 AGENTS 中写入测试用 API key 字符串，读取该文件，确认返回 `[REDACTED]`，而非原值。

## 面试追问

**为什么索引版本用内容哈希而非 mtime？** 工具、编辑器或 Git 操作可能保留或回拨时间戳。内容哈希能发现相同大小、相同 mtime 下的真实内容变化。

**为什么 AST 调用关系不是完整调用图？** Python 支持反射、猴子补丁、动态导入和变量别名。静态结果是定位线索，必须读取源码和运行测试确认。

**为什么候选测试通过仍需完整测试？** 静态导入关系可能漏掉间接依赖、插件发现、配置路径和跨服务契约。候选测试缩短反馈时间，全套测试负责最终验收。

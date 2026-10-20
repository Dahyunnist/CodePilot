# Step 0
1. 为什么需要`.env.example`: 告诉协作者项目需要哪些配置，在开发时作为模板直接复制到`.env`后填写真实值；同时真正的`.env`被git忽略，可以保护API key
2. 指令学习：
   - 启动虚拟环境：
    ```
    conda activate NN
    cd codepilot-lite
    ```
    - 运行test：
    ```
    cd .\evals\cases\parse-config\repo
    python -m pytest tests -q
    ```
    - 保存运行结果：
    ```
    python -m pytest tests -q --color=no 2>&1 | Tee-Object -FilePath ..\baseline-output.txt
    Get-Content ..\baseline-output.txt 
    ```
## 任务描述和约束条件
1. Step0 验收条件：
   - .venv可用，能够运行python和pytest
   - .env.example, .gitignore, pyproject.toml已创建
   - 演示样例包含Bug代码和pytest测试
   - 测试结果稳定为1 failed, 2 passed
   - 失败项为test_empty_input_returns_empty_config
   - 测试输出保存到baseline-output.txt
   - .env和.venv不被git追踪
   - 尚未接入模型
2. 首个Agent修复任务：parse_config在空输入时错误地抛出异常，修复该问题，使空输入返回{}，并保持其他测试通过。不要修改测试
3. 修复任务验收条件：
   - parse_config("") == {}
   - 正常配置仍能正常解析
   - 非法配置行仍抛出带行号的ValueError
   - pytest结果从1 failed, 2 passed变为3 passed
   - 不允许删除，跳过或修改测试
   - git diff不包含无关修改
# Step 1
1. python环境变更：改为依赖本机已有conda环境NN

# Step 6：隔离工作区与执行安全

1. 输入与输出：输入源 Git 仓库和 `run_id`，输出固定提交的干净 clone；测试输入 pytest 参数，输出标准化 `ToolResult`。
2. 调用链：CLI 创建 workspace，Agent 只把 workspace 交给工具；`run_tests` 再进入 Docker。
3. 主要失败：源仓库追踪密钥文件；Docker 不可用或测试超时。
4. 复现测试：提交 `.env` 后准备 workspace；运行休眠测试并设置短 timeout。
5. 方案原因：本地 clone 比直接修改源仓库安全，比完整 VM 简单；Docker 提供进程、网络和资源边界，但不是完整安全沙箱。

# Step 7：预算与审批

1. 输入与输出：输入步数、测试次数、时间和 Token 上限；输出明确终止状态和失败类别。
2. 调用链：Agent 在模型请求和工具执行前检查预算；宿主机测试先进入审批接口。
3. 主要失败：模型重复调用测试；未经批准执行宿主机代码。
4. 复现测试：连续生成相同 `run_tests`；不给 ApprovalProvider。
5. 方案原因：显式计数器容易审计。暂不增加复杂退避器，因为工具错误会作为 observation 返回模型。

# Step 8：Trace 与报告

1. 输入与输出：输入运行和工具事件，输出一行一个 JSON 对象的 JSONL，以及 Markdown 总结。
2. 调用链：Agent 在模型轮次、工具前后和结束时写事件；CLI 写最终报告。
3. 主要失败：日志泄露补丁或密钥；日志缺少失败步骤。
4. 复现测试：在 patch 参数放入假密钥并搜索 trace；制造工具失败后检查 `error_type`。
5. 方案原因：JSONL 可流式追加和逐行分析；只记录参数键、路径和长度，避免保存源码内容。

# Step 9：固定评测

1. 输入与输出：输入 5 个固定 case，输出 CSV、Markdown、Trace 和隐藏测试结果。
2. 调用链：runner 创建固定初始提交，Agent 修复，隐藏测试在 Agent 结束后单独挂载。
3. 主要失败：fixture 初始测试意外通过；可见测试通过但隐藏测试失败。
4. 复现测试：直接运行每个初始 repo；故意写一个只满足可见样例的补丁。
5. 方案原因：scripted-oracle 先验证评测基础设施。它不能代表真实模型能力，真实 LLM 结果必须另行运行和记录。

# Step 10：稳定化

1. 输入与输出：输入完整仓库，输出通过的测试、可复现 README、评测证据和 `v0.1` tag。
2. 调用链：开发测试、Docker 评测、差异检查、提交、tag。
3. 主要失败：文档命令依赖本机绝对路径；生成结果与实现不一致。
4. 复现测试：搜索盘符路径和密钥模式；从 README 顺序执行构建、测试和评测命令。
5. 方案原因：v0.1 固定一个可回退的 Day 2 基线，后续 LangGraph 迁移不影响显式 Loop 版本。

# Step 17：公开仓库问题评测

1. 先固定上游 issue、源码归档 SHA-256、可见/隐藏测试和容器镜像，再调用真实模型。
2. 冻结任务与基线：[S17 案例冻结记录](learning/stage-S17-public-issues-frozen.md)；结果与失败分析：[S17 真实模型报告](learning/stage-S17-public-issues-results.md)。
3. 本轮 3 项任务都因 25k Token 上限及测试/收尾预算保留而在编辑前停止；0/3 accepted。轨迹说明预算保护生效，但此结果不能证明修复能力。
4. SWE-agent/OpenHands 的公开基准使用 issue 任务和可复现评测管线；本项目尚未使用官方 SWE-Bench harness，也没有同条件对照或足够样本。

# Step 18：CLI 参数与功能缺口

1. 新增 Click #3084、#3121 和 Flask #4777 三项公开案例；任务、源码摘要和验收先行冻结。
2. Docker 基线三项均失败；上游金标准的可见、隐藏验收三项全通过。
3. Flask 旧测试集有 3 项受当前容器依赖影响，冻结命令只选目标 CLI 测试和相关回归测试。
4. 真实模型三项均在补丁前被测试/收尾预算护栏停止；0/3 accepted。60k Token 上限仍不足以支撑完整上下文轮次。
5. [S18 冻结记录](learning/stage-S18-public-issues-frozen.md)和[真实模型结果](learning/stage-S18-public-issues-results.md)记录来源、哈希、容器、成本和失败轨迹。

# Step 19：跨进程异常序列化

1. 新增 Requests #6628 真实案例：异常 pickle 失败会令 `ProcessPoolExecutor` 崩溃。
2. 基线复现失败；上游补丁通过 pickle 可见测试和进程池隐藏测试。
3. 为 Requests 建立独立固定依赖 Docker 镜像，避免借用不含 Requests 依赖的通用镜像。
4. 60k Token 在 S18 仍不足；本阶段冻结为单项 100k Token、16 步，先校准预算再扩充样本。
5. [S19 案例冻结记录](learning/stage-S19-requests-process-pool-frozen.md)和[真实模型结果](learning/stage-S19-requests-process-pool-results.md)记录问题、镜像、成功补丁和验收证据。

# Step 20：公开仓库跨模块行为问题

1. 新增 Flask #4834 嵌套 Blueprint 子域继承、urllib3 #3653 `HTTPHeaderDict` bytes 键两项案例，来自两个真实仓库。
2. Docker 基线两项失败；独立上游金标准的可见、隐藏测试全部通过。
3. 首轮真实模型均因 10 步上限未修改代码、未运行测试，0/2 accepted；20 步最终诊断因模型请求长时间无响应而中断，没有验收结果。
4. 失败轨迹发现缓存命中不重发旧证据；`_fit_context` 也会在不可压缩消息超限时无限循环。提交 `0f03185`、`24644ce` 分别修复，并关闭 SDK 隐式重试。
5. urllib3 修复后单项重跑仍因 Token 预算保护停止；新增连续两轮只读提醒、四轮熔断后，请求补充用户方向。最新单项仍为 0/1，未编辑、未测试；全套测试 122 项通过。
6. 结果、成本（含峰时费率估算）、耗时与失败轨迹：[S20 评测报告](learning/stage-S20-public-issues-results.md)；案例来源与复现：[S20 冻结记录](learning/stage-S20-public-issues-frozen.md)。

# Step 21：真实模型完成公开缺陷修复

1. 将 urllib3 #3653 任务缩窄到 bytes 键读取、删除、成员判断与 `getlist`，指明源码方法和基准测试；10k 字符上下文、45k Token 总预算。
2. DeepSeek V4 Flash 真实模型完成补丁；Agent 定向测试、独立可见/隐藏测试通过，1/1 accepted。隔离评测工作区提交 `12a4ae6 修复 HTTPHeaderDict bytes 键访问`；峰价估算 `$0.005174`，低于 `$0.03` 上限。
3. urllib3 全量回归：1,840 passed、329 skipped、4 xfailed、2 failed。一个 TLS 警告失败已在未修改基线复现；一个并发敏感失败在基线和补丁版单独重跑均通过。
4. CodePilot 自身全回归：122 passed。补丁、逐次成本、预算根因、测试环境限制和失败轨迹：[S21 真实修复报告](learning/stage-S21-public-urllib3-repair.md)。

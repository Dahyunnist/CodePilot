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

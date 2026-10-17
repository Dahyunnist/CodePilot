# Step 0
1. 为什么需要`.env.example`: 告诉协作者项目需要哪些配置，在开发时作为模板直接复制到`.env`后填写真实值；同时真正的`.env`被git忽略，可以保护API key
2. 指令学习：
   - 启动虚拟环境：
    ```
    cd E:\job\codepilot-lite
    .\.venv\Scripts\Activate.ps1
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
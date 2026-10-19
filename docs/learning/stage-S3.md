# S3：加固执行边界

## 1. 问题与前后变化

S3 检查路径、密钥、Docker 失败、超时和临时工作区。找到两处真实缺口：Windows 文件系统路径可用大小写变体绕过 `.env` / `.git` 名称检查；Docker 超时后清理容器若自身超时，会抛错并覆盖原始测试超时。现在路径检查也检查解析后的真实路径并忽略大小写；工作区 run ID 限制为安全目录名，clone 失败会移除本次创建的半成品；Docker 清理失败不再覆盖原超时。模型历史压缩也会缩短旧工具调用参数，防止大型补丁参数绕过上下文字符预算。

## 2. 数据流与涉及文件

`resolve_repo_path` 先拒绝绝对路径、遍历和敏感项，再解析真实路径，核对是否仍在仓库根内，并对真实路径的 `.git`、`.env` 和密钥后缀做检查。`WorkspaceManager.prepare` 检查 run ID 和跟踪密钥文件；clone 后验证干净状态，准备失败时清理半成品。`run_tests` 把 Docker 缺失、守护进程拒绝、容器超时归为执行错误或超时。`ModelClient` 在抛出模型错误前遮蔽密钥。Agent 保留 host 测试审批门槛。

## 3. 设计取舍

只清理 `WorkspaceManager` 本轮明确创建的目标目录；正常运行后的工作区仍保留，供报告和人工复核使用。容器清理失败不能改变原始超时结果。拒绝解析后落在仓库外的符号链接和 junction；Windows 符号链接权限不足时测试改用 junction。Docker 与主机内核仍是隔离信任边界。

## 4. 两条失败路径与错误传播

尝试通过 `.ENV`、`.GIT/config` 或越界符号链接读取文件时，仓库工具返回路径策略错误，内容不进入模型。Docker daemon 不可用时返回 `error_type=execution`；容器超时后即使 `docker rm` 也超时，结果仍为 `error_type=timeout`。工作区 ID 含 `../` 时准备前拒绝；Git clone 失败时删除半成品并保留原错误。模型异常里的 DeepSeek 格式 `sk-...` 字符串被遮蔽。

## 5. 测试结果与证据

NN 环境 `D:\Anaconda3\envs\NN\python.exe -m pytest -q`：55 项通过。覆盖大小写敏感路径、符号链接/junction 越界、Docker 不可用、容器清理再次超时、API key 遮蔽、run ID 路径遍历及 clone 半成品清理。未执行额外 Docker 集成评测；当前执行器无法连接 Docker named pipe，错误已由单测覆盖。

## 6. 10–20 分钟小实验

在 NN 环境运行 `python -m pytest -q tests/test_repository_tools.py tests/test_workspace.py tests/test_execute.py tests/test_model.py`。随后在一个临时 Git 仓库创建目录 junction 指向仓库外，再用 CodePilot 读其文件；预期工具返回路径策略错误。测试完成后移除临时 junction 和仓库。

## 7. 面试问题与回答

**问：为什么检查解析后的路径？** 原始字符串可能经由 `..`、大小写别名或链接指向不同位置；授权边界应基于文件系统解析结果。

**问：为何 Docker 清理失败不应覆盖超时？** 调用方需要得到测试进程的主结果；容器清理属于补救动作，失败不能改变已发生的超时类型。

**问：半成品工作区为何清理、成功工作区为何保留？** 失败 clone 不是可复核产物，留下会污染磁盘；成功工作区支持检查 patch 和诊断，因此目前由操作者按需清理。

## 8. 未完成边界

成功运行的工作区目前不自动删除；本机宿主测试依赖操作者审批和仓库可信度。Docker bind mount 对容器内测试仍可写，且 Docker Desktop、宿主内核及 Git 元数据解析仍在信任边界内。未加入 seccomp、恶意软件扫描、VM 隔离或多租户防护。

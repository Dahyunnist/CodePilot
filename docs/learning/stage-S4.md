# S4：只读测试工作区

## 1. 本阶段目标

S3 已限制容器自身的文件系统，但绑定到 `/workspace` 的 Git 工作区仍可写。测试代码因此能改动 Agent 生成的补丁、Git 元数据或其他仓库文件，影响验证结果。本阶段让 Docker 测试容器只读访问工作区。

## 2. 实现

`codepilot/tools/execute.py` 将工作区 bind mount 标为 `readonly`。容器中的 pytest 缓存插件关闭，`tmp_path` 等临时文件统一写入 `/tmp/pytest-tmp`；该目录位于既有的 64 MB `/tmp` tmpfs。

Docker 根文件系统继续只读。隐藏测试挂载此前已只读，保持不变。主机执行模式不变。

## 3. 验收

- Docker 命令把 `/workspace` 挂载为只读。
- pytest 临时目录使用容器 `/tmp`，不会尝试写入仓库。
- Docker 命令仍包含无网络、非 root、资源上限与只读隐藏测试挂载。
- NN 环境全量测试通过。

## 4. 验证限制

当前执行环境无法访问 Docker Desktop 命名管道，故不能在此处运行真实 Docker 容器验证 bind mount 行为。命令构造和只读参数由单元测试验证。需要在有 Docker 权限的终端运行：

```powershell
python -m evals.runner --docker-image codepilot-runner:0.1
```

只读工作区会拒绝主动向仓库写文件的测试；这类测试应使用 pytest 的 `tmp_path`。Docker 隔离仍依赖 Docker Desktop 与宿主内核，不等于 VM 沙箱。

# CP-2 后续审计（2026-11-13）

## 状态

- `django__django-10924`：污染，永久排除本轮评测。此前本地产生过候选补丁和测试文件，也运行过对应基线/修复测试。它们不构成有效基准证据；不得提交、复用或宣称成功。
- `django__django-11133`：排除。此前读取过该题 gold patch 正文。
- `mwaskom__seaborn-3010`：唯一继续核验的候选，仍为 `candidate_metadata_only`。本地已知 CP-2 缓存目录的文件名扫描没有发现该题补丁或工作区；扫描范围有限，不能证明整台机器不存在其他副本。
- 本轮没有运行模型，也没有运行候选代码、可见测试或隐藏测试。没有模型成功率、成本或耗时结果。

## 来源核验

- 仓库：`mwaskom/seaborn`
- 冻结基线：`0f5a013e2cf43562deec3b879458e59a73853813`
- 许可证元数据：`BSD-3-Clause`；尚未取得冻结基线上的 LICENSE 文件证据。
- 官方问题：[seaborn #2992](https://github.com/mwaskom/seaborn/issues/2992)。问题报告显示 `so.PolyFit()` 遇到缺失数据会触发 `LinAlgError: SVD did not converge in Linear Least Squares`。
- 关联 PR：[seaborn #3010](https://github.com/mwaskom/seaborn/pull/3010)。PR 标题为 “Fix: Make PolyFit stat robust to missing data”，目标基线短 SHA 与冻结基线一致。
- 官方 SWE-bench 镜像：`swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3010:latest`。
- Docker Desktop 服务端可响应。镜像首次检查时不存在；随后拉取未完成并已停止。没有容器运行证据、镜像 ID、基线测试结果或许可证文件哈希。

## 继续步骤

在 Docker Desktop 可用的主机终端执行：

```powershell
docker pull swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3010:latest
docker image inspect swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3010:latest --format '{{.Id}}'
```

之后先在无网络容器内核对 `/testbed` 的 Git 基线和该基线 LICENSE，再独立编写可见回归测试。先确认基线失败，再确认本地修复通过。只有用户提供或授权使用官方隐藏测试时，才在隔离容器中执行隐藏验收。禁止读取或打印 gold patch 正文。

所有运行命令、镜像 ID、基线/修复测试结果、文件哈希和限制必须记录后，才能把候选从 `candidate_metadata_only` 升级。未完成这些步骤前，不得报告候选成功或真实模型表现。

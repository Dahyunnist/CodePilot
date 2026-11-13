# CP-2 后续审计（2026-11-13）

## 状态

- `django__django-10924`：污染，永久排除本轮评测。此前本地产生过候选补丁和测试文件，也运行过对应基线/修复测试。它们不构成有效基准证据；不得提交、复用或宣称成功。
- `django__django-11133`：排除。此前读取过该题 gold patch 正文。
- `mwaskom__seaborn-3010`：唯一继续核验的候选，仍为 `candidate_metadata_only`。本地已知 CP-2 缓存目录的文件名扫描没有发现该题补丁或工作区；扫描范围有限，不能证明整台机器不存在其他副本。
- 本轮没有运行模型、隐藏测试或候选补丁。可见故障复现未能启动；没有模型成功率、成本或耗时结果。

## 来源核验

- 仓库：`mwaskom/seaborn`
- 冻结基线：`0f5a013e2cf43562deec3b879458e59a73853813`
- 许可证元数据：`BSD-3-Clause`；尚未取得冻结基线上的 LICENSE 文件证据。
- 官方问题：[seaborn #2992](https://github.com/mwaskom/seaborn/issues/2992)。问题报告显示 `so.PolyFit()` 遇到缺失数据会触发 `LinAlgError: SVD did not converge in Linear Least Squares`。
- 关联 PR：[seaborn #3010](https://github.com/mwaskom/seaborn/pull/3010)。PR 标题为 “Fix: Make PolyFit stat robust to missing data”，目标基线短 SHA 与冻结基线一致。
- 官方 SWE-bench 镜像：`swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3010:latest`。
- 用户提供的镜像 ID：`sha256:22fef36e8b9655fb1642d976de669e3f2426df0186a09d6d788fc6215cfa1bc0`；平台 `linux/amd64`，工作目录 `/testbed/`。
- 隔离容器用 `--network none --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --memory 6g --cpus 2` 启动；未挂载宿主目录。
- 镜像内 `/opt/miniconda3/envs/testbed/bin/python` 可导入 NumPy 1.25.2、Pandas 2.0.0、Matplotlib 3.7.2、SciPy 1.11.2、Seaborn 0.12.1.dev0。
- 容器源码 HEAD 为 `191ec3379337aea8e27e61f8fd3dd11411a8654f`，与冻结基线 `0f5a013e2cf43562deec3b879458e59a73853813` 不同。原始输出：`BASE_SHA=191ec3379337aea8e27e61f8fd3dd11411a8654f`、`BASE_SHA_MISMATCH`。
- SHA 校验失败后立即停止；未读取 LICENSE、未运行 issue 复现或测试。此前用系统 `python` 的尝试曾因缺少 NumPy 退出；随后只读发现并检查了镜像预装的 `testbed` 环境。
- 当前镜像不匹配冻结源码基线，不能作为有效实验。没有足够证据提出 Seaborn 源码补丁。

## 继续步骤

下一步需要与冻结 base SHA 完全一致的干净源码环境。确认 SHA 和该基线 LICENSE 后，再运行 issue 可见复现；只有复现基线故障，才讨论独立源码修复。禁止读取或打印 gold patch 正文；本轮不运行隐藏测试。

所有运行命令、镜像 ID、基线/修复测试结果、文件哈希和限制必须记录后，才能把候选从 `candidate_metadata_only` 升级。未完成这些步骤前，不得报告候选成功或真实模型表现。

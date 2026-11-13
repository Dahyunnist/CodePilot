# CP-2 后续审计（2026-11-13）

## 状态

- `django__django-10924`：污染，永久排除本轮评测。此前本地产生过候选补丁和测试文件，也运行过对应基线/修复测试。它们不构成有效基准证据；不得提交、复用或宣称成功。
- `django__django-11133`：排除。此前读取过该题 gold patch 正文。
- `mwaskom__seaborn-3010`：唯一继续核验的候选，仍为 `candidate_metadata_only`。本地已知 CP-2 缓存目录的文件名扫描没有发现该题补丁或工作区；扫描范围有限，不能证明整台机器不存在其他副本。
- 冻结基线上的许可证与公开 issue 复现现已核验；未运行模型、pytest、隐藏测试或候选补丁。没有模型成功率、成本或耗时结果。

## 来源核验

- 仓库：`mwaskom/seaborn`
- 冻结基线：`0f5a013e2cf43562deec3b879458e59a73853813`
- 许可证元数据：`BSD-3-Clause`；冻结基线文件为 `LICENSE.md`，SHA-256：`0874bfc01308833385b2f5ca62205525739f6a57b8688afea1b078d0f845d6d4`。
- 官方问题：[seaborn #2992](https://github.com/mwaskom/seaborn/issues/2992)。问题报告显示 `so.PolyFit()` 遇到缺失数据会触发 `LinAlgError: SVD did not converge in Linear Least Squares`。
- 关联 PR：[seaborn #3010](https://github.com/mwaskom/seaborn/pull/3010)。PR 标题为 “Fix: Make PolyFit stat robust to missing data”，目标基线短 SHA 与冻结基线一致。
- 官方 SWE-bench 镜像：`swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3010:latest`。
- 用户提供的镜像 ID：`sha256:22fef36e8b9655fb1642d976de669e3f2426df0186a09d6d788fc6215cfa1bc0`；平台 `linux/amd64`，工作目录 `/testbed/`。
- 初始镜像 HEAD 是 `191ec3379337aea8e27e61f8fd3dd11411a8654f`。镜像仓库已有冻结提交对象 `0f5a013e2cf43562deec3b879458e59a73853813`；GitHub PR 的 Codecov 元数据也把 `0f5a013` 标为 base。随后在一次性容器写层 detached checkout 精确 base；容器禁网、限资源、未挂宿主目录，退出后销毁。
- 精确 base 的 `/opt/miniconda3/envs/testbed/bin/python` 可导入 NumPy 1.25.2、Pandas 2.0.0、Matplotlib 3.7.2、SciPy 1.11.2、Seaborn 0.12.1.dev0。
- 公开 issue 复现表达式：`so.Plot([1, 2, 3, None, 4], [1, 2, 3, 4, 5]).add(so.Line(), so.PolyFit()).plot()`。原始结果：`LinAlgError: SVD did not converge in Linear Least Squares`，符合 issue 预期；另有 NumPy/BLAS 的 `DLASCL` 警告。未运行 pytest 或隐藏测试。
- LICENSE 哈希与 issue 复现均已取得，但完整 SWE-bench visible/hidden 命令、金标准修复 commit 的完整 SHA 和验收尚未补齐；候选仍保持 `candidate_metadata_only`。

## 继续步骤

下一步候选修复方向：拟合前按 x/y 成对过滤缺失值，保持坐标对齐；再补可见回归测试覆盖 x 缺失、y 缺失和全缺失输入。该方向仅由 issue 行为推导，尚未改代码或验证；不得读取 gold patch。之后补齐独立可见验收命令，再讨论隐藏验收。未完成前不得升级候选状态或报告修复成功。

所有运行命令、镜像 ID、基线/修复测试结果、文件哈希和限制必须记录后，才能把候选从 `candidate_metadata_only` 升级。未完成这些步骤前，不得报告候选成功或真实模型表现。

# CP-2 后续审计（2026-11-13）

## 状态

- `django__django-10924`：污染，永久排除本轮评测。此前本地产生过候选补丁和测试文件，也运行过对应基线/修复测试。它们不构成有效基准证据；不得提交、复用或宣称成功。
- `django__django-11133`：排除。此前读取过该题 gold patch 正文。
- `mwaskom__seaborn-3010`：唯一继续核验的候选，仍为 `candidate_metadata_only`。本地已知 CP-2 缓存目录的文件名扫描没有发现该题补丁或工作区；扫描范围有限，不能证明整台机器不存在其他副本。
- 冻结基线上的许可证与公开 issue 复现已核验；本轮完成独立补丁和可见测试。未运行模型或隐藏测试，没有模型成功率、成本或耗时结果。

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
- 公开 issue 复现表达式：`so.Plot([1, 2, 3, None, 4], [1, 2, 3, 4, 5]).add(so.Line(), so.PolyFit()).plot()`。未修复基线触发 `LinAlgError: SVD did not converge in Linear Least Squares`，符合 issue 预期；另有 NumPy/BLAS 的 `DLASCL` 警告。
- 基线文件在一次性禁网容器中 checkout。补丁只读挂载；源码改动只存在于临时容器写层，容器退出后销毁。

## 独立修复实验

- 补丁文件：[candidate.patch](../../evals/public_cases/cp2/reproductions/seaborn_3010/candidate.patch)
- 补丁 SHA-256：`0ea4fdc52c1eb6d8278de6843f3d79751b681518c46fb2fb74bb74e52915ee73`
- 独立改动：在 `PolyFit._fit_predict` 中对 `x`、`y` 两列成对 `dropna()`，再拟合，避免错位或 NaN 进入 `numpy.polyfit`。
- 新增可见回归覆盖：x 缺失、y 缺失、x/y 缺失行不同、全部缺失，以及 issue 输入的统计阶段。
- 命令：`python -m pytest -v -p no:cacheprovider tests/_stats/test_polyfit_missing_data.py tests/_stats/test_regression.py`
- 结果：`7 passed in 0.90s`。新增 5 项通过；冻结基线原有 `TestPolyFit::test_no_grouper` 和 `TestPolyFit::test_one_grouper` 通过。官方隐藏测试补丁未应用，未运行。
- issue 输入通过 Plot 统计阶段。为隔离后续渲染，回归测试临时 stub `Plotter._plot_layer`；完整绘图调用在统计通过后触发环境错误 `OptionError: No such keys(s): 'mode.use_inf_as_null'`。这是 Seaborn 0.12.1.dev0 与镜像 Pandas 2.0.0 的兼容问题，不能据此宣称完整绘图通过。
- 首轮自写用例有一项期望网格错误，测试指出该断言问题；修正样例后最终 7 项全通过。源码补丁未因此改变。
- 本次没有查看或套用 PR diff、gold patch，也没有提交 Seaborn 上游仓库。
- 候选仍为 `candidate_metadata_only`：缺少官方完整 fix commit SHA、正式 visible/hidden 命令及隐藏验收。不能报告 SWE-bench 完整修复成功或模型表现。

## 继续步骤

下一步先处理绘图环境的 Pandas 兼容问题，或将验收限定为 Stat 输出并明确范围；再确认可见完整回归命令。隐藏测试继续隔离，不读取 gold patch。

所有运行命令、镜像 ID、基线/修复测试结果、文件哈希和限制必须记录后，才能把候选从 `candidate_metadata_only` 升级。未完成这些步骤前，不得报告候选成功或真实模型表现。

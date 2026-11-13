# CP-2 后续审计（2026-11-13）

## 状态

- `django__django-10924`：污染，永久排除本轮评测。此前本地产生过候选补丁和测试文件，也运行过对应基线/修复测试。它们不构成有效基准证据；不得提交、复用或宣称成功。
- `django__django-11133`：排除。此前读取过该题 gold patch 正文。
- `mwaskom__seaborn-3010`、`pytest-dev__pytest-5495`、`django__django-11099`：本地已知 CP-2 缓存目录未发现对应题目补丁/工作区；扫描范围有限，不能证明整台机器不存在其他副本。三题均未运行模型或官方隐藏测试。
- 三题已在冻结基线上完成 issue 复现、许可证哈希和独立可见修复实验；仍为 `candidate_metadata_only`，未构成完整 SWE-bench 验收。没有模型成功率、成本或耗时结果。

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
- 补丁 SHA-256：`41df778ae5f5633ccf3343e83e328af55796995220be31f9e5b40a8dadda0bd9`
- 独立改动：在 `PolyFit._fit_predict` 中对 `x`、`y` 两列成对 `dropna()`，再拟合，避免错位或 NaN 进入 `numpy.polyfit`。
- 新增可见回归覆盖：x 缺失、y 缺失、x/y 缺失行不同、全部缺失，以及 issue 输入的统计阶段。
- 命令：`python -m pytest -v -p no:cacheprovider tests/_stats/test_polyfit_missing_data.py tests/_stats/test_regression.py`
- 结果：`7 passed in 0.87s`。新增 5 项通过；冻结基线原有 `TestPolyFit::test_no_grouper` 和 `TestPolyFit::test_one_grouper` 通过。官方隐藏测试补丁未应用，未运行。
- issue 输入通过 Plot 统计阶段。为隔离后续渲染，回归测试临时 stub `Plotter._plot_layer`；完整绘图调用在统计通过后触发环境错误 `OptionError: No such keys(s): 'mode.use_inf_as_null'`。这是 Seaborn 0.12.1.dev0 与镜像 Pandas 2.0.0 的兼容问题，不能据此宣称完整绘图通过。
- 首轮自写用例有一项期望网格错误，测试指出该断言问题；修正样例后最终 7 项全通过。源码补丁未因此改变。
- 本次没有查看或套用 PR diff、gold patch，也没有提交 Seaborn 上游仓库。
- 候选仍为 `candidate_metadata_only`：缺少官方完整 fix commit SHA、正式 visible/hidden 命令及隐藏验收。不能报告 SWE-bench 完整修复成功或模型表现。

## 继续步骤

下一步先处理绘图环境的 Pandas 兼容问题，或将验收限定为 Stat 输出并明确范围；再确认可见完整回归命令。隐藏测试继续隔离，不读取 gold patch。

所有运行命令、镜像 ID、基线/修复测试结果、文件哈希和限制必须记录后，才能把候选从 `candidate_metadata_only` 升级。未完成这些步骤前，不得报告候选成功或真实模型表现。

## 第二候选：pytest #5495

- 候选：`pytest-dev__pytest-5495`，仓库 `pytest-dev/pytest`，本地已知 CP-2 缓存未见该题工作区或补丁。
- 官方问题：[pytest #5260](https://github.com/pytest-dev/pytest/issues/5260)；[关联 PR #5495](https://github.com/pytest-dev/pytest/pull/5495)。问题复现为 `assert b"" == b"42"`，旧输出把 byte 值显示为 ASCII 整数 `52`。PR 页面 Codecov base 前缀 `1aefb24` 与清单完整 SHA 前缀一致。
- 冻结 base：`1aefb24b37c30fba8fd79a744829ca16e252f340`。官方镜像 `swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-5495:latest`，镜像 ID `sha256:86b356cf05ac9a623ba8943849e25ce2d0bcebc506753b1361595e5ad488a9b3`。容器 `linux/amd64`，工作目录 `/testbed`。
- base 时点许可：清单声明 MIT；根目录 `LICENSE` 的 SHA-256 为 `4be38574daf05665b6194e4fd84c5ef6ce7c3a2810308a5222d5cdffc2d04d18`。
- 使用 `/opt/miniconda3/envs/testbed/bin/python`，pytest `4.6.1.dev144+g1aefb24b3.d20260815`。容器禁网、限资源、无宿主目录挂载；补丁只读挂载，checkout 和应用改动只在销毁即清理的容器层。
- 未修复 base 运行 `pytest -vv -p no:cacheprovider /tmp/test_byte_strings_issue.py`，临时测试内容为 issue 原例。结果 `1 failed`，输出 `Right contains 2 more items, first extra item: 52`，与 issue 一致。

### 独立修复与可见验证

- 补丁：[candidate.patch](../../evals/public_cases/cp2/reproductions/pytest_5495/candidate.patch)，SHA-256：`255f432389ea57193a713b937f30c0184f732ed99436ed30479ee186919fdc08`。
- 根因：`istext()` 只把 `str` 视为文本，bytes 落入序列比较，被逐字节显示成整数。独立最小修复让 `istext()` 接受 `str` 与 `bytes`；现有 `_diff_text()` 已实现 bytes 的可读差异。
- 新测试：`testing/test_bytes_comparison_issue.py::test_bytes_equality_uses_readable_byte_diff`。
- 邻近非隐藏测试命令：`python -m pytest -v -p no:cacheprovider testing/test_bytes_comparison_issue.py testing/test_assertrewrite.py`。`testing/test_assertion.py`（清单中的隐藏测试文件）未读、未运行。
- 补丁版结果：`59 passed, 4 failed, 2 error`。未修补 base 对 `testing/test_assertrewrite.py` 的对照为 `58 passed, 4 failed, 2 error`；失败/错误项完全相同。现有失败来自该镜像当前环境/平台兼容问题，不是补丁新增。新增回归通过。
- issue 临时测试补丁后仍按预期以断言失败结束，但输出改为 `- '`、`+ '42`；不再出现整数 `52`。新回归测试验证该格式。
- 未查看或套用 PR diff、gold/hidden patch；没有模型调用。候选仍是 `candidate_metadata_only`，隐藏验收未做，不能称完整基准通过。

CP-2 当前已有三个独立候选实验，达到至少三个案例；若按 3–5 个案例目标，仍可再补一至两题。继续保持污染的 `django_10924` 目录不动、不提交。

## 第三候选：Django #11099

- 候选：`django__django-11099`，仓库 `django/django`。本地已知 CP-2 缓存目录未发现该 task ID 的工作区或补丁；扫描仅覆盖已知 CP-2 缓存目录。
- 官方问题：[Django ticket #30257](https://code.djangoproject.com/ticket/30257)；[关联 PR #11099](https://github.com/django/django/pull/11099)。问题说明 `UsernameValidator` 的 `$` 可在字符串末尾换行前匹配，令带 `\n` 用户名通过。
- 冻结 base：`d26b2424437dabeeca94d7900b37d2df4410da0c`。Docker 镜像 `swebench/sweb.eval.x86_64.django_1776_django-11099:latest`，ID `sha256:cca302934edd881cc4f1e4647a389a25cdaa3c02bfa33667a4204934a09c4fb1`；镜像仓库含该 Git 对象，detached checkout 后 SHA 精确匹配，工作树干净。
- base 许可元数据：BSD-3-Clause；根目录 `LICENSE` SHA-256：`b846415d1b514e9c1dff14a22deb906d794bc546ca6129f950a18cd091e2a669`。
- 环境：镜像自带 `/opt/miniconda3/envs/testbed/bin/python`，Python 3.6，Django `3.0.dev20190322115239`。镜像没有 pytest；未安装依赖，使用 Python 自带 `unittest`。
- 未修复基线直接调用 `ASCIIUsernameValidator` 与 `UnicodeUsernameValidator`，两者都接受 `"username\\n"`。这是 ticket 的可见现象；未读取隐藏测试 `tests/auth_tests/test_validators.py`。

### 独立修复与可见验证

- 补丁：[candidate.patch](../../evals/public_cases/cp2/reproductions/django_11099/candidate.patch)，SHA-256：`092258892bea38f7959d72b7bda1e4cb48b56a0a275a77d0581389566c8d450c`。
- 独立修复：两个 username validator 的 regex 结束锚点从 `$` 改为 `\Z`；保留 `^`，因为问题只涉及末尾换行。
- 新增测试：`tests/auth_tests/test_username_trailing_newline.py::UsernameValidatorTrailingNewlineTests.test_ascii_validator_rejects_trailing_newline` 与 `...test_unicode_validator_rejects_trailing_newline`。
- 命令：`python -m unittest test_username_trailing_newline -v`，工作目录 `tests/auth_tests`，`PYTHONPATH=/testbed`。结果：`Ran 2 tests ... OK`。
- 未读或套用 PR diff/gold/hidden patch；未调用模型。候选仍为 `candidate_metadata_only`；没有跑官方隐藏验收或完整 Django 测试集。

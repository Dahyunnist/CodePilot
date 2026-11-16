# CP-2：pytest 5103 与 xarray 3364 公开样例

本阶段加入两个不同仓库和故障类别的纵向切片。仅使用 Docker 镜像精确基线归档、GitHub PR 公共测试文件和公共 PR 源码差异。没有读取、复制或运行 hidden test、`test_patch` 或 gold patch；公开修复只用于独立临时副本。

## pytest：断言失败诊断

- 仓库 / 许可证：`pytest-dev/pytest`，MIT；基线 `LICENSE` SHA-256：`4be38574daf05665b6194e4fd84c5ef6ce7c3a2810308a5222d5cdffc2d04d18`。
- PR：<https://github.com/pytest-dev/pytest/pull/5103>；问题：<https://github.com/pytest-dev/pytest/issues/5062>。
- PR head：`22d91a3c3a248761506a38fdf26c859b341e82be`。
- 基线提交 / tree：`10ca84ffc56c2dd2d9dc4bd71b7b898e083500cd` / `f71d163f3bec6192303f6781459aaa329d5a9da8`。
- 本地镜像：`swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-5103:latest`；digest：`sha256:1648c614485c81d9e08bcf9ec8014fb38cd2f20fad6bea782552d923a35ce714`。
- 基线归档 SHA-256：`9d159dd0e3e323b30657b38d727c7f0a56d64b147e166c3bd8205637a182ee98`；清单覆盖 418 个基线文件，清单 SHA-256：`89c1a72fd03830705aaa83fe2701ed4bba9835e09bebfe97fcf56ee377e96a05`。
- 公开测试：`testing/test_assertrewrite.py`；SHA-256：`31c32710503e03e8a0b945be273c43f0b151e5caa21b2f5c403ca14b9bb6a24f`。
- 公开修复文件：`src/_pytest/assertion/rewrite.py`；只把 PR 的改动应用到临时副本。修复副本 SHA-256：`6360c3c8f25d2a76279c0c532fe45b23997a1fc8a76d60f35b292b8e86657c96`。
- 运行镜像另外生成的 `src/_pytest/_version.py`，SHA-256：`e9f276f3036f19ddf29332a5a3d33a10f6d326fa7f5af046dfc419fb3769f915`。它不属于基线归档，单独列入 `generated_files` 并核对哈希；项目现有物化器也会恢复该生成版本元数据。

`test_unroll_expression` 在基线失败：报告只有 `assert False = all(<generator ...>)`，没有指出失败表达式。应用公开 PR 修复后，同一测试通过，断言诊断包含 `0 == 1`。案例运行命令只选择这个直接公开回归。

额外运行 PR 新增的 `testdir.runpytest` 用例时，两个子进程仍输出泛化的 `AssertionError`，没有出现预期诊断；覆盖到容器内 pytest 源文件的临时挂载没有在这些子进程中生效。本案例不把这两项算作已验证，也不扩大运行器改动。

## xarray：concat 缺失变量

- 仓库 / 许可证：`pydata/xarray`，Apache-2.0；基线 `LICENSE` SHA-256：`73ba74dfaa520b49a401b5d21459a8523a146f3b7518a833eea5efa85130bf68`。
- PR：<https://github.com/pydata/xarray/pull/3364>；问题：<https://github.com/pydata/xarray/issues/508>。
- PR head：`a6ba031238c0631d708ac30881d92540ca799047`。
- 基线提交 / tree：`863e49066ca4d61c9adfe62aca3bf21b90e1af8c` / `39ca20ba2fab753b757741686104dad9ff73ac7b`。
- 本地镜像：`swebench/sweb.eval.x86_64.pydata_1776_xarray-3364:latest`；digest：`sha256:8591047f512d8d26b4d0e121d2d04eb6b95fa6ad41e13d92fe64f5ef66244c27`。
- 基线归档 SHA-256：`b9f476a07cd04f1ef413d6074db1f1134e328140f9312a456f6c9c7a05ec974d`；清单覆盖 234 个文件，清单 SHA-256：`dface19dbbc32d4fcbfae9192c94f8f4244808ec2c8314d7a56e40dd7ab69e7a`。
- 公开测试：`xarray/tests/test_concat.py`；SHA-256：`5a08f516cd30928411e68d8261e7a27245502d84d2d90eeae3b9651542ffca05`。
- 公开修复文件：`xarray/core/concat.py`；只把 PR 的改动应用到独立临时源文件。修复副本 SHA-256：`01830462c2ddd3819ec021401e1e652f5f1f40d389db1111ce343458510b029d`。

公开测试在基线因 `variables {'z'} are present in some datasets but not others` 失败。公开 PR 修复副本运行同一测试通过：`1 passed, 35 deselected`。

## 边界与复核

两个案例的 Docker 镜像父提交、tree 和许可证哈希均与冻结清单匹配。基线归档由镜像内 `git archive HEAD^` 生成，只含已核验父提交；pytest 另外单列镜像 setup 生成的版本元数据，并校验其哈希。每个案例随后只覆盖 PR head 中对应的公开测试文件。复用 `evals/cp2_benchmark.py::_case_materialization_blockers` 后，两例均无路径、清单、文件哈希或 oracle 字段阻断。

完整仓库 `repo/` 依项目忽略规则留在本机，不进入提交。提交包含案例元数据、公开测试、逐文件哈希清单和本说明。新 checkout 需从记录的公开基线重新取源并校验清单后运行。本阶段无模型请求、无 API 成本。

本阶段证明的是可见测试在基线与公开修复副本间的差异，以及案例材料校验；没有运行 Agent 或模型。完整 `WorkspaceManager` clone 仍受此前记录的 Git for Windows `NtCreateDirectoryObject ... 0xC0000022` 宿主限制。

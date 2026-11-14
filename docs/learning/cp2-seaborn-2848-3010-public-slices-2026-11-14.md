# CP-2 seaborn 第三批公开样例（2026-11-14）

本批加入两个 seaborn 公开回归样例。仅使用 PR 公开测试、公开源码和冻结 Docker 基线；没有读取隐藏测试、`test_patch` 或 gold patch，没有调用模型。

## `mwaskom__seaborn-2848`

- 基线：commit `94621cef29f80282436d73e8d2c0aa76dab81273`，tree `2df89059488d28b92ff85365266ae8f2032e4328`。
- 上游：[PR 2848](https://github.com/mwaskom/seaborn/pull/2848)，head `487dae9b7817894eddf59a155124c7e53267d1a9`。
- 冻结镜像：`swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-2848:latest`，digest `sha256:d719470351e66623e532a4f23cdedfe8fb737147fe108e4b5829aa273528389d`。
- 许可证：`LICENSE`，BSD-3-Clause，SHA-256 `0874bfc01308833385b2f5ca62205525739f6a57b8688afea1b078d0f845d6d4`。
- 基线归档 SHA-256 `c5dd9be0e160589707f4b7b026c211c8299f75582807ba7396f016cecebe52b4`，260 个文件。
- 可见测试：`tests/test_relational.py`，SHA-256 `76dbfd47cba045bc87f0ed428b85cda106d63f2dd16000dbfdff1ceef4f013a1`。
- 公开缺陷：`HueMapping._lookup_single` 对 `hue_order` 排除的类别仍尝试调用空 `norm`。冻结描述曾写 pairplot；但公开 PR 测试实际调用 `scatterplot`。本样例严格按公开测试范围描述，不声称覆盖 pairplot。
- Docker 基线：1 项失败，复现公开测试 `test_hue_order` 的 `TypeError`。
- 修复后验证：未完成。Docker 权限审查连接中断，后续修复验证未执行。

## `mwaskom__seaborn-3010`

- 基线：commit `0f5a013e2cf43562deec3b879458e59a73853813`，tree `902c8d72200c6f62b6c62f8bc71039cb6148841d`。
- 上游：[PR 3010](https://github.com/mwaskom/seaborn/pull/3010)，head `f191292f5554eb7908a07b849094c1d78adcf8bb`。
- 冻结镜像：`swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3010:latest`，digest `sha256:22fef36e8b9655fb1642d976de669e3f2426df0186a09d6d788fc6215cfa1bc0`。
- 许可证路径差异：冻结信息写 `LICENSE`，精确基线实际文件为 `LICENSE.md`；该文件声明 BSD-3-Clause，SHA-256 `0874bfc01308833385b2f5ca62205525739f6a57b8688afea1b078d0f845d6d4`。
- 基线归档 SHA-256 `58e3374b966a99d1fc0d2705f9b30bbdd63c631fa6f4efe71a4254acc01f339c`，286 个文件。
- 可见测试：`tests/_stats/test_regression.py`，SHA-256 `c68053590168ce35c79d499e2b33e0e7ca3aff7319b0feb09770065c9bb66ad9`。
- 公开缺陷：`PolyFit` 将含 x/y 缺失值的行交给 `numpy.polyfit`，导致线性代数错误；公开修复先按 x/y 丢弃缺失行。
- Docker 基线：1 项失败，复现公开测试 `test_missing_data` 的 `LinAlgError`。
- 修复后验证：未完成。Docker 权限审查连接中断，后续修复验证未执行。

## 闸门与限制

两个 case 的 `_case_materialization_blockers` 均返回空列表；本地 NN 环境定向运行 `tests/test_cp2_benchmark.py tests/test_execute.py` 得到 **44 passed**。这证明清单和 runner 单测通过，不替代 Docker 修复后回归验证。未统计模型费用；模型未调用。两个完整仓库仅保留在被忽略的本地 `repo/` 目录，不纳入提交。

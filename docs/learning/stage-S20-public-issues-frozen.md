# S20：Flask 与 urllib3 公开问题评测冻结

## 案例

本阶段新增两个不同仓库的公开缺陷。案例与校验测试在模型评测前冻结；每项只进行一次真实模型评测。

| 案例 | 任务 | 来源 | 基线 | 上游金标准 |
|---|---|---|---|---|
| Flask #4834 | 嵌套 Blueprint 继承父级子域；子级自带子域时按子.父组合 | [issue #4834](https://github.com/pallets/flask/issues/4834)、[PR #4935](https://github.com/pallets/flask/pull/4935) | 可见测试 1 项失败；关联套件 57 项通过 | 可见 58 项、隐藏 1 项通过 |
| urllib3 #3653 | `HTTPHeaderDict` 支持 bytes 键读取、删除、成员判断和 `getlist` | [PR #3653](https://github.com/urllib3/urllib3/pull/3653) | 可见测试 1 项失败，`__getitem__` 对 bytes 键抛 `KeyError` | 可见 1 项、隐藏 2 项通过 |

## 来源与复现

固定来源为 Flask 2.2.2 与 urllib3 2.5.0 PyPI 源码归档，SHA-256 分别为：

- Flask：`642c450d19c4ad482f96729bd2a8f6d32554aa1e231f4f6b4e7e5264b16cca2b`
- urllib3：`3fc47733c7e419d4bc3f6b3dc2b4f890bb743906a30d56ba4a5bfa4bbff92760`

准备冻结副本：

```powershell
python -m evals.public_cases.prepare_s20_cases `
  --archives .tmp/public-bench-sources `
  --output .tmp/public-s20-frozen
```

运行：

```powershell
python -m evals.live_runner `
  --cases .tmp/public-s20-frozen `
  --case-ids flask-4834 urllib3-3653 `
  --execution docker `
  --docker-image codepilot-public-runner:20261020 `
  --max-total-tokens 100000 `
  --max-steps 10 `
  --max-elapsed 360 `
  --context-budget-chars 8000 `
  --output-root reports/public-s20-actual-20261020 `
  --work-root .tmp/public-s20-work-20261020
```

冻结版本的基线测试均失败。金标准副本分别使用 Flask PR #4935 的子域继承逻辑，以及 urllib3 PR #3653 对 bytes 键做 Latin-1 解码；金标准仅用于隔离验收，不在模型可见仓库中。Docker 镜像内禁网运行。逐案报告位于被 Git 忽略的 `reports/public-s20-actual-20261020/`。

## 比较边界

这两个任务覆盖 Web 路由注册与 HTTP 头映射两类行为。Flask 案例需同时兼容继承和显式嵌套子域；urllib3 案例覆盖同一映射 API 的四种访问路径。公开 PR 有训练数据污染可能，不能据此估算生产成功率。

对开源方案的初步调研显示，OpenHands 与 SWE-agent 都用真实仓库 issue、隔离执行环境和测试结果作为修复闭环；OpenHands 的基准仓库也支持 SWE-bench Verified 等仓库级评测。本项目目前已有类似的隔离基线、Agent 工具反馈、隐藏验收流程，但样本仍小，且 S17/S18 六项首次评测全失败。来源：[OpenHands SWE-bench 基准](https://github.com/OpenHands/benchmarks/blob/main/benchmarks/swebench/README.md)、[OpenHands Benchmarks](https://github.com/OpenHands/benchmarks)。

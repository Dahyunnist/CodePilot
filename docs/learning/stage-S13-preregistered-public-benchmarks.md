# S13：预注册公开仓库修复基准

## 目标

在冻结案例、测试、容器依赖和 Agent 代码后，测量 CodePilot 对两个公开 Python 项目缺陷的首次修复能力与一次重复运行差异。实验开始后不改提示词、案例、可见测试、隐藏测试或预算；任何更改都只能进入新的基准版本。

## 冻结案例

| 案例 | 上游问题 | 上游修复 | 固定源码 | 类型 | 可见/隐藏验收 |
|---|---|---|---|---|---|
| `flask-4834` | [Flask #4834](https://github.com/pallets/flask/issues/4834) | [Flask #4935](https://github.com/pallets/flask/pull/4935) | Flask 2.2.2 sdist，SHA-256 `642c450d19c4ad482f96729bd2a8f6d32554aa1e231f4f6b4e7e5264b16cca2b` | 多层 Blueprint 子域继承、路由回归 | 公开 reproducer + 上游 `test_blueprints.py`；隐藏三层嵌套子域组合 |
| `urllib3-3710` | [urllib3 #3710](https://github.com/urllib3/urllib3/issues/3710) | [urllib3 #3711](https://github.com/urllib3/urllib3/pull/3711) | urllib3 2.5.0 sdist，SHA-256 `3fc47733c7e419d4bc3f6b3dc2b4f890bb743906a30d56ba4a5bfa4bbff92760` | 大响应部分读取性能、内存复制 | 峰值分配上限与完整读取正确性；隐藏多尺寸分块及独立内存上限 |

PyPI sdist 不包含可验证的 Git commit/tree。这里以项目官方仓库链接、精确 release、完整源包 SHA-256 固定输入；不把包版本冒充 Git commit。Flask sdist 中 `tests/test_apps/.env` 是与目标无关的本机配置夹具；准备器按清单排除，并将排除路径写入每条结果。源码准备器先验 SHA，再安全解包。

## 数据边界

- 两案例均作冻结 holdout；不参与提示词或策略调优。
- `click-3145` 是此前多轮提示词调优案例，只可作校准参考，不计入本次首次通过率。
- S9 的三个案例是合成多文件/多缺陷/性能任务，单独报告，不与公开仓库 holdout 合并。
- 每个 holdout 案例运行两次同配置任务。第 1 次计首次结果，第 2 次只观察重复差异；重复次数不足以支持统计显著性结论。
- 两个不同仓库、两个 issue 仅是小样本，不代表通用大型仓库能力。

## 执行冻结

- Docker 基础镜像固定 Python 3.11 slim digest；`docker/public-runner.Dockerfile` 锁定 pytest 及 Flask 运行/测试依赖版本。
- Docker 容器断网、只读根文件系统、非 root 用户、512 MiB 内存和 1 CPU。
- 每次 Agent 调用有独立源码副本；基线可见测试必须失败。Agent 自测、独立可见测试和只读挂载隐藏测试全部通过才算接受。
- API 模型、模型名、服务地址、温度默认值、Token/耗时预算及当前代码提交写入每轮结果。密钥不记录。
- 轨迹统计模型输入/缓存/输出 Token、费用估算、耗时、步数、工具调用、读文件次数与字符数、代码搜索次数、测试调用次数。
- 任一失败或超预算均保留原始 trace、测试日志和 JSON 结果；不根据 holdout 结果修改后重跑。

## 复现

在项目根目录 PowerShell 中运行：

```powershell
docker build -f docker/public-runner.Dockerfile -t codepilot-public-runner:20261020 .
docker run --rm --network bridge -v "${PWD}\.tmp\public-bench-sources:/out" python:3.11-slim python -m pip download --no-deps --no-binary=:all: Flask==2.2.2 urllib3==2.5.0 --dest /out
python -m evals.public_cases.prepare_s13_cases --archives .tmp/public-bench-sources --output .tmp/public-bench-prepared/cases
python -m evals.live_runner --cases .tmp/public-bench-prepared/cases --case-ids flask-4834 urllib3-3710 --execution docker --docker-image codepilot-public-runner:20261020 --max-total-tokens 18000 --max-steps 10 --max-elapsed 180 --output-root reports/public-s13-attempt-1
```

第二次执行改输出目录为 `reports/public-s13-attempt-2`，其他参数与源码提交保持不变。必须先保存第 1 轮结果，再执行第 2 轮。

## 敏感报告审计

对历史文本报告扫描了常见 API key、Bearer token、私钥头及 Windows 用户路径。未发现密钥样式匹配；34 份未跟踪运行摘要含本机用户路径。旧报告和 SQLite 原件均保留，不提交、不删除。需要共享时，先备份并只生成脱敏副本；SQLite 先确认 schema、导出并扫描后再分享。

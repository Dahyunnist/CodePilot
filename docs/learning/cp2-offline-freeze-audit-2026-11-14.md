# CP-2 冻结清单离线审计与可见测试预检（2026-11-14）

## 结论

15 题冻结清单的**内部元数据哈希自洽**，但目前不能进入真实基准：工作区没有物化的 `cases/`；15 题 visible test 都只有规格文本，未写成测试、未在 base 上验证；本会话 Docker CLI 不能连接 Linux Engine；另有运行时镜像 digest 缺失、冻结时记录的部分代码工件哈希已与当前代码漂移，以及费用预留高于当前可用账本。

未调用模型、未运行容器、未检查隐藏测试，也未读取或修改未跟踪的 `evals/public_cases/cp2/reproductions/django_10924/`。

## 清单交叉核对

离线复算结果：15 个入选 task ID 均能在 20 题 `frozen-selection.json` 和候选元数据中对应；repo、base commit、题面 SHA-256、gold patch SHA-256 与选择清单一致。15/15 task record hash、汇总 task hash、gold hash、题面 hash、visible-test-spec hash均匹配。15 个可见测试规格 SHA 是**规格文字的哈希**，不能当作测试文件哈希。

| 仓库 | 题数 | 清单许可证 | base commit | image config digest | 当前可见测试状态 |
| --- | ---: | --- | --- | --- | --- |
| `django/django` | 4 | BSD-3-Clause | 4/4 有记录 | 4/4 有冻结值 | 4 题均只有规格 |
| `pytest-dev/pytest` | 4 | MIT | 4/4 有记录 | 4/4 有冻结值 | 4 题均只有规格 |
| `pydata/xarray` | 4 | Apache-2.0 | 4/4 有记录 | 3/4 有冻结值 | 4 题均只有规格 |
| `mwaskom/seaborn` | 2 | BSD-3-Clause | 2/2 有记录 | 2/2 有冻结值 | 2 题均只有规格 |
| `scikit-learn/scikit-learn` | 1 | BSD-3-Clause | 1/1 有记录 | 1/1 有冻结值 | 1 题只有规格 |

许可文件名与其 SHA-256 记录在 manifest 中；14 题标为 `verified_at_exact_base`，xarray-4493 因缺 image 标为 `pending_missing_image`。本次没有本地上游仓库 checkout 或 Docker daemon，故不能重新读取对应 base commit 的许可证文件来独立验证这些记录。15 个 base commit SHA 已冻结，但 manifest 没有逐题 Git tree SHA；本地也没有可读取的上游 Git 对象。

15 个入选题均有公开 PR 链接，且与候选清单中的 `source_pr_url` 一致；`auditable-candidates-v1.json` 的 20/20 项 `issue_url` 都为空，不能把 PR 链接说成已核实的 issue 链接。15 个入选题的候选元数据有 gold patch SHA 和 test patch SHA；本地没有对应 patch 原文可供重新计算，gold 内容按策略不进入 agent workspace。benchmark manifest 本身没有 test patch SHA 字段或真实测试文件 SHA；它保存的是规格文本 SHA。

## 冻结工件漂移

manifest 的 source selection SHA、model SHA、runtime descriptor SHA 都可复算。代码工件中 `evals/live_runner.py` 哈希匹配；以下冻结工件哈希与当前 HEAD 不同：

| 工件 | 冻结 SHA-256 | 当前 SHA-256 |
| --- | --- | --- |
| `codepilot/` Python tree | `e08f5c4ea406bb0456deb2bec6e10a7750a8eb544bac18faa6b76bb80687a336` | `df9b72e6189b8945a4d2fda0cd716cc9d70864ab8fd13c2cec316c642416dda9` |
| `evals/compare_live_runs.py` | `3dd4f8d74a1bcbc857d93c4bd58cf06b5432c7a0cc43813b04916fe901723a79` | `25282bc83c2c6a8d5945e0bdf86912c1eb69c2acf2186cd59d88577fc6f2654f` |
| `evals/cp2_benchmark.py` | `c23622daddd1dd99a82b3367506c57b366f2b7622e073874a40866e4f395738a` | `cb984ce3ee192d74671105324926b7af52bc7f83c435226e9c232f757f27870c` |

冻结 manifest 不应就地改写。后续若重新开展 benchmark，需生成新的冻结版本，并重新记录 agent、scorer、driver、测试、镜像身份与配对配置哈希。

## 可见测试物化尝试

检查 `evals/public_cases/cp2/` 后，没有 `cases/` 目录或 15 个 base 仓库 checkout；只有规格文本和少数历史 reproduction patch 文件。不能从规格摘要安全地伪造“公开测试”，也不能在缺少上游代码时验证 base 失败、修复后通过。因此没有创建替代测试或把任何一题标记为已物化。

`docker version` 显示客户端 29.1.3，但连接 `npipe:////./pipe/dockerDesktopLinuxEngine` 失败；对 xarray 镜像的只读 inspect 同样失败。当前 Docker 镜像可用性不能从此会话确认。

用临时零余额账本和不存在的临时 cases 路径调用 `evals.cp2_benchmark plan`，按预期 fail-closed，报告：预算未与供应商对账、15 题双配置最坏费用预留 `$1.731456` 高于 `$0`，15 题没有 materialized case / baseline，且 xarray-4493 缺 image digest。项目授权 cap 是 `$0.50`；因此即便之后物化完测试，也须先调整为实际可满足的预算方案并完成账单对账，才能申请运行真实模型。

在 Docker Desktop 已启动且可访问的 PowerShell 中，对缺失镜像执行：

```powershell
docker pull swebench/sweb.eval.x86_64.pydata_1776_xarray-4493:latest
docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}} {{json .RepoDigests}}' swebench/sweb.eval.x86_64.pydata_1776_xarray-4493:latest
```

请回传完整 inspect 输出。manifest 的 `docker_image_config_digest` 应填写 `.Id` 给出的 `sha256:<64 位十六进制>`，并核实平台为 `linux/amd64`；RepoDigest 是另一个身份值，不能误填到 config digest 字段。缺少该值期间继续 fail-closed，不批量拉取其余镜像。

## 验收

本轮运行：

```powershell
python -m pytest tests/test_cp2_benchmark.py tests/test_benchmark_manifest_integrity.py -q --basetemp=.tmp\pytest-cp2-audit
```

结果 **7 passed**。`evals.cp2_benchmark plan` 的阻断输出确认没有启动评测或模型调用。未运行真实模型、Docker 容器或公开测试。

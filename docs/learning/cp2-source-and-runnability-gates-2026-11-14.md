# CP-2 来源与可运行性闸门（2026-11-14）

## 一手来源核验

SWE-bench [官方数据说明](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/datasets.md)列出 `issue_url`、`pr_url`、`base_commit`、`patch` 和 `test_patch` 为不同字段。因此 PR 链接和 issue 链接不能互相冒充；本仓库原冻结选择中的 issue URL 为空。对 15 个选中任务逐一查看了对应的官方仓库 PR 页面，并把 PR 页面明确提到的 issue/ticket 关系记入 `source-provenance-v1.json`。这个 sidecar 不改写旧冻结 manifest，也不填充猜测的 issue URL。

| task | 官方 PR 中的 issue/ticket 关系 |
| --- | --- |
| `django__django-10924` | 修复 [Django ticket 29529](https://code.djangoproject.com/ticket/29529)；[PR 10924](https://github.com/django/django/pull/10924) |
| `django__django-11001` | 修复 [Django ticket 29692](https://code.djangoproject.com/ticket/29692)；[PR 11001](https://github.com/django/django/pull/11001) |
| `django__django-11099` | 修复 [Django ticket 30257](https://code.djangoproject.com/ticket/30257)；[PR 11099](https://github.com/django/django/pull/11099) |
| `django__django-11133` | 修复 [Django ticket 30294](https://code.djangoproject.com/ticket/30294)；[PR 11133](https://github.com/django/django/pull/11133) |
| `pytest-dev__pytest-5103` | 关闭 [pytest issue 5062](https://github.com/pytest-dev/pytest/issues/5062)；[PR 5103](https://github.com/pytest-dev/pytest/pull/5103) |
| `pytest-dev__pytest-5221` | 修复 [pytest issue 5220](https://github.com/pytest-dev/pytest/issues/5220)；[PR 5221](https://github.com/pytest-dev/pytest/pull/5221) |
| `pytest-dev__pytest-5413` | 修复 [pytest issue 5412](https://github.com/pytest-dev/pytest/issues/5412)；[PR 5413](https://github.com/pytest-dev/pytest/pull/5413) |
| `pytest-dev__pytest-5495` | 修复 [pytest issue 5260](https://github.com/pytest-dev/pytest/issues/5260)，替代 [issue 5267](https://github.com/pytest-dev/pytest/issues/5267)；[PR 5495](https://github.com/pytest-dev/pytest/pull/5495) |
| `pydata__xarray-3364` | 关闭 [xarray issue 508](https://github.com/pydata/xarray/issues/508)；[PR 3364](https://github.com/pydata/xarray/pull/3364) |
| `pydata__xarray-4094` | 关闭 [xarray issue 4049](https://github.com/pydata/xarray/issues/4049)；[PR 4094](https://github.com/pydata/xarray/pull/4094) |
| `pydata__xarray-4248` | PR 写明“possibly closes” [xarray issue 2773](https://github.com/pydata/xarray/issues/2773)，故标为可能关联；[PR 4248](https://github.com/pydata/xarray/pull/4248) |
| `pydata__xarray-4493` | 关闭 [xarray issues 4483](https://github.com/pydata/xarray/issues/4483) 和 [4529](https://github.com/pydata/xarray/issues/4529)；[PR 4493](https://github.com/pydata/xarray/pull/4493) |
| `mwaskom__seaborn-2848` | PR 文本修复 [seaborn issue 2419](https://github.com/mwaskom/seaborn/issues/2419)，提交记录也提到 issue 2590；[PR 2848](https://github.com/mwaskom/seaborn/pull/2848) |
| `mwaskom__seaborn-3010` | 修复 [seaborn issue 2992](https://github.com/mwaskom/seaborn/issues/2992)；[PR 3010](https://github.com/mwaskom/seaborn/pull/3010) |
| `scikit-learn__scikit-learn-10508` | 修复 [scikit-learn issue 10458](https://github.com/scikit-learn/scikit-learn/issues/10458)；[PR 10508](https://github.com/scikit-learn/scikit-learn/pull/10508) |

以上 PR 页面均显示已合并。官方数据文档说明 issue URL 与 PR URL 分列；因此 sidecar 关系来自各 PR 页面，而不声称它们已与原始数据集 issue_url 字段逐项字节核验。PR 页面是本次关系证据的一手来源。

## commit、许可、镜像与测试哈希边界

- 15/15 base commit 均为完整 40 位 SHA，并与本地冻结选择、候选元数据一致。这是本地交叉核对；本轮未能从每个上游 repo 的 commit 页面独立校验 Git 对象/tree SHA。冻结清单没有逐题 tree SHA，不能补写推测值。
- 五个项目的仓库主页/许可证页面当前分别声明 BSD-3-Clause、MIT、Apache-2.0、BSD-3-Clause、BSD-3-Clause。可查 [Django LICENSE](https://github.com/django/django/blob/main/LICENSE)、[pytest LICENSE](https://github.com/pytest-dev/pytest/blob/main/LICENSE)、[xarray LICENSE](https://github.com/pydata/xarray/blob/main/LICENSE)、[seaborn 仓库许可证标识](https://github.com/mwaskom/seaborn) 和 [scikit-learn COPYING](https://github.com/scikit-learn/scikit-learn/blob/main/COPYING)。这些 `main` 页面不证明历史 base commit 上 license 文件字节相同。
- manifest 有 14 个 image config digest，xarray-4493 为 null；本轮按要求未运行 Docker。缺 digest 的 task schema 校验失败。
- 15 个 `visible_test_spec_sha256` 都匹配规格文字本身；它不是测试脚本哈希。候选元数据有 test patch SHA，但没有实际 visible test 文件。`visible_test_status` 仍是 `spec_frozen_test_not_materialized_or_run`，15 题没有 baseline 证据。
- 旧冻结 `artifacts` 的 4 个哈希中，`live_runner.py` 匹配当前源代码，`codepilot/`、`compare_live_runs.py`、`cp2_benchmark.py` 三个不匹配；旧文件也没有新加的 provenance sidecar 与两个 schema 哈希。新 freeze 会同时固定这 7 项，旧 manifest 因漂移/缺项不能复用；生成新 freeze 后也仍会被未物化测试与 xarray 镜像缺项阻断。
- seaborn 当前官方仓库主页将许可证文件列为 `LICENSE.md`；旧 manifest 记录 `LICENSE`，而历史 base 的文件名/内容本轮无法从一手页面确认。此项不以当前 main 猜测历史值，必须在后续 exact-base 仓库或其固定镜像中核实。运行闸门还要求许可证路径、SHA 和 `verified_at_exact_base` 证据完整。

## Schema 与 validator

新增 `runnable-task.schema.json`、`source-provenance.schema.json` 和 15 题来源关系 sidecar。`evals.cp2_benchmark.plan()` 在原有预算、visible baseline、case 目录检查前，新增以下 fail-closed 条件：

1. 每题必须有匹配仓库的 HTTPS GitHub PR 来源、已合并状态和至少一个带关系类型的一手 issue/ticket 引用；缺失或 PR 不一致则阻断。
2. 必须有许可证标识、base 路径、64 位许可证文件 SHA 和 `verified_at_exact_base`；任一缺失即阻断。
3. 必须有 40 位 base commit、image 中已核验标志、镜像 tag 和格式正确的 `sha256:<64位>` config digest。
4. 必须有规格文本哈希、已物化测试文件哈希，以及 `ready_and_baseline_verified` 状态。
5. 必须校验 task 记录汇总、gold 哈希汇总、selection 哈希、runtime hash、model hash 和当前 agent/scorer/runner/driver 工件哈希。

新增回归覆盖缺 source PR/issue、缺许可证证据、缺 image digest、缺 visible test hash、来源 sidecar 缺失、issue 关系缺失和 scorer/driver hash 漂移。它们只检查安全闸门，不运行 Docker 或 benchmark。

## 验证范围

```powershell
python -m pytest tests/test_cp2_benchmark.py tests/test_benchmark_manifest_integrity.py -q --basetemp=.tmp\pytest-cp2-gates
```

结果 **17 passed**。对当前冻结 manifest 单独调用只读 runnable-contract validator，得到 **57 个阻断项**：15 题均缺物化测试文件 hash 和已核验 baseline；xarray-4493 另缺 base-image 核验、许可证文件路径/hash 和 image digest；旧冻结有三项代码哈希漂移，并缺 provenance 与两个 schema 的三项哈希。该检查未运行评测。

本轮未运行 Docker、benchmark、API 或模型。旧 manifest 及 selection 未改写；`django_10924/` 未跟踪目录未读取、修改或纳入提交。

# CP-2 三题上游元数据审计（2026-11-13）

本轮只看官方 GitHub PR 页面和本地冻结 manifest 元数据；没有下载或运行仓库代码，没有打开 PR diff、gold patch 或 hidden-test patch。PR 页面能核对修复主题、关联 issue 和合并状态；不能单独证明某题可复现。

| 候选 | 官方 PR / 关联 issue | PR 页面可核验内容 | 冻结 manifest 元数据 | 未满足的可复现门槛 |
|---|---|---|---|---|
| `django__django-10924` | [PR #10924](https://github.com/django/django/pull/10924) / [Django ticket #29529](https://code.djangoproject.com/ticket/29529) | 标题为允许 `FilePathField` 使用 callable path；已合并至 `django:master`，2019-05-02。 | base `bceadd2788dc2dad53eba0caae172bd8522fd483`；hidden path `tests/model_fields/test_filepathfield.py`；test patch SHA `418a17eede0c413fb5424bc202f1d1cd43d51ee67941370580e21b87be0550ce`。 | 未核实完整 fix SHA、base revision 的 LICENSE 文件、visible test command；hidden path/hash 只来自 manifest，未读取测试内容。 |
| `pytest-dev__pytest-5103` | [PR #5103](https://github.com/pytest-dev/pytest/pull/5103) / [Issue #5062](https://github.com/pytest-dev/pytest/issues/5062) | 标题为 unroll calls to `any`；已合并至 `pytest-dev:features`，2019-05-27。合并到 features 分支不能单独证明当前目标基线仍保留该行为。 | base `10ca84ffc56c2dd2d9dc4bd71b7b898e083500cd`；hidden path `testing/test_assertrewrite.py`；test patch SHA `89740f6cb7127fc954eb9fa2a84e7b6df26e77f18b76bf96b50db5bfb0ba5c86`。 | 未核实完整 fix SHA、base revision 的 LICENSE 文件、visible test command；也未核实后续行为是否被回滚。 |
| `pydata__xarray-3364` | [PR #3364](https://github.com/pydata/xarray/pull/3364) / [Issue #508](https://github.com/pydata/xarray/issues/508) | 标题为 concat 对待合并变量缺失更宽容；已合并至 `pydata:master`，2019-10-14。PR 描述称新增测试，并称 `black . && mypy . && flake8` 通过；这些不是该冻结题的可复现命令证据。 | base `863e49066ca4d61c9adfe62aca3bf21b90e1af8c`；hidden path 与 test patch SHA 仍以冻结 manifest 为准，本轮不读取 patch。 | 未核实完整 fix SHA、base revision 的 LICENSE 文件、该题 visible test command；hidden path/hash 未从上游测试文件交叉验证。 |

冻结 manifest 中 3 个 base SHA、许可证标识、hidden path 和 test patch SHA 已被本地 validator 与 selection 交叉核对。base revision 的许可证 URL 访问返回 GitHub cache miss，故许可证**仅有 manifest 声明**，不视为时点文件核验。PR 页面列出 commit 数量和 merged 状态，但本轮没有取得三个完整 40 位 fix SHA；不以短 SHA 或 gold patch SHA 冒充 fix SHA。

## 结论

3 个候选仍全部是 `candidate_metadata_only`。上游 PR/issue 关联已找到；完整 fix SHA、base 时点 LICENSE 证据和题目级 visible test command 缺失。因此不能称为可复现候选，也不能据此声称运行通过。pytest 题另有目标分支为 `features` 的边界，需核对其后续历史后再选作固定基准。

Validator 现在只接受 `candidate_reproducible` 状态同时具备 issue URL、40 位 fix SHA 及对应官方 commit URL、指向同仓库同 base 的 LICENSE URL、非空 visible/hidden test command，以及与冻结 manifest 一致的 hidden-test 文件和 patch SHA。测试用合成完整记录检查正向路径，并逐字段删除和篡改 base 地址检查 fail-closed。此正向测试只验证校验器，不代表以上三题已经具备这些证据。

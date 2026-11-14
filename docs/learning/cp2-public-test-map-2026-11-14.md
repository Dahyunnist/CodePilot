# CP-2 公开回归测试入口映射（2026-11-14）

通过 GitHub API 核对了 15 个已合并 PR 的元数据与 changed-file 列表。以下只是公开测试入口映射；还没有把测试复制进独立 case，也没有执行 baseline。

| task | PR | 公开测试文件 |
| --- | --- | --- |
| `django__django-10924` | [#10924](https://github.com/django/django/pull/10924) | `tests/model_fields/test_filepathfield.py` |
| `django__django-11001` | [#11001](https://github.com/django/django/pull/11001) | `tests/expressions/tests.py` |
| `django__django-11099` | [#11099](https://github.com/django/django/pull/11099) | `tests/auth_tests/test_validators.py` |
| `django__django-11133` | [#11133](https://github.com/django/django/pull/11133) | `tests/httpwrappers/tests.py` |
| `pytest-dev__pytest-5103` | [#5103](https://github.com/pytest-dev/pytest/pull/5103) | `testing/test_assertrewrite.py` |
| `pytest-dev__pytest-5221` | [#5221](https://github.com/pytest-dev/pytest/pull/5221) | `testing/python/fixtures.py` |
| `pytest-dev__pytest-5413` | [#5413](https://github.com/pytest-dev/pytest/pull/5413) | `testing/code/test_excinfo.py` |
| `pytest-dev__pytest-5495` | [#5495](https://github.com/pytest-dev/pytest/pull/5495) | `testing/test_assertion.py` |
| `pydata__xarray-3364` | [#3364](https://github.com/pydata/xarray/pull/3364) | `xarray/tests/test_combine.py` |
| `pydata__xarray-4094` | [#4094](https://github.com/pydata/xarray/pull/4094) | `xarray/tests/test_dataset.py` |
| `pydata__xarray-4248` | [#4248](https://github.com/pydata/xarray/pull/4248) | `xarray/tests/test_formatting.py` |
| `pydata__xarray-4493` | [#4493](https://github.com/pydata/xarray/pull/4493) | `xarray/tests/test_dask.py`, `xarray/tests/test_dataset.py`, `xarray/tests/test_interp.py`, `xarray/tests/test_variable.py` |
| `mwaskom__seaborn-2848` | [#2848](https://github.com/mwaskom/seaborn/pull/2848) | `tests/test_relational.py` |
| `mwaskom__seaborn-3010` | [#3010](https://github.com/mwaskom/seaborn/pull/3010) | `tests/_stats/test_regression.py` |
| `scikit-learn__scikit-learn-10508` | [#10508](https://github.com/scikit-learn/scikit-learn/pull/10508) | `sklearn/preprocessing/tests/test_label.py` |

## Materialization notes

- For 14 tasks, the public PR adds a focused regression test or changes an existing test. Use only the relevant test hunk; do not copy implementation hunks or hidden SWE-bench `test_patch` data.
- xarray-4493 public issue #4483 reports lazy Dask data becoming eager during `Dataset.update`. Its merged PR mostly adapts `DataArray` handling across several test modules. Write a small visible regression from the public issue's reproducer, then baseline it against the exact-base image.
- Keep the independently authored visible test hash separate from the frozen visible-test-spec hash. Update neither `test_patch` nor any hidden-test metadata.
- Exact-base Docker verification is corrected in [the parent audit](cp2-docker-parent-audit-2026-11-14.md). Image outputs can now support case construction; no test result exists yet.

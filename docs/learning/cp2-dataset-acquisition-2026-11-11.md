# CP-2 SWE-bench Lite 数据获取

`python -m scripts.fetch_cp2_dataset` 默认只打印计划；显式 `--fetch` 才请求固定 Hugging Face revision `b0dde1093fe417d83b7184254edf8199c1f0dff5` 的 Parquet 文件。官方 LFS SHA-256 固定为 `438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3`。数据写入 ignored `.tmp/cp2-swebench-lite-v1`。可选解析依赖由 `requirements-bench.txt` 固定。freeze 记录分离 `source_parquet_sha256` 与规范化 20 题 `subset_json_sha256`，不覆盖旧 JSON 字节 SHA。下载成功不等于任务执行成功；未运行 20 题，也未加载隐藏测试到 Agent 工作区。

测试：`python -m pytest tests/test_cp2_dataset_fetch.py -q`，2 passed。dry-run 已验证。许可证仍需按每个上游仓库及数据集条款逐项复核。

## 逐仓许可来源与子集排除边界

| 仓库 | 冻结题数 | 清单声明许可 | 官方许可来源 |
|---|---:|---|---|
| django/django | 4 | BSD-3-Clause | https://github.com/django/django/blob/main/LICENSE |
| pytest-dev/pytest | 4 | MIT | https://github.com/pytest-dev/pytest/blob/main/LICENSE |
| pydata/xarray | 4 | Apache-2.0 | https://github.com/pydata/xarray/blob/main/LICENSE |
| mwaskom/seaborn | 4 | BSD-3-Clause | https://github.com/mwaskom/seaborn/blob/master/LICENSE |
| scikit-learn/scikit-learn | 4 | BSD-3-Clause | https://github.com/scikit-learn/scikit-learn/blob/main/COPYING |

这些 URL 是逐仓许可证核对入口；复现时仍须在固定 base revision 核实许可证文件存在且与清单一致。若缺失或无法核验，该仓库任务全部标为 excluded，不能进入可运行子集。五仓各有 4 个候选；当前真实可运行题数仍为 0，因为原始数据未物化、镜像/依赖未逐题验证。

资产脚本 freeze 采用独占创建，已有封存拒绝覆盖；verify 要求源 Parquet SHA、规范化子集 SHA 和 20 题数全匹配。

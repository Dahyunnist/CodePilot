# CP-2 SWE-bench Lite 数据获取

`python -m scripts.fetch_cp2_dataset` 默认只打印计划；显式 `--fetch` 才请求固定 Hugging Face revision `b0dde1093fe417d83b7184254edf8199c1f0dff5` 的 Parquet 文件。官方 LFS SHA-256 固定为 `438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3`。数据写入 ignored `.tmp/cp2-swebench-lite-v1`。可选解析依赖由 `requirements-bench.txt` 固定。freeze 记录分离 `source_parquet_sha256` 与规范化 20 题 `subset_json_sha256`，不覆盖旧 JSON 字节 SHA。下载成功不等于任务执行成功；未运行 20 题，也未加载隐藏测试到 Agent 工作区。

测试：`python -m pytest tests/test_cp2_dataset_fetch.py -q`，2 passed。dry-run 已验证。许可证仍需按每个上游仓库及数据集条款逐项复核。

## 下载与冻结操作记录（2026-11-13）

仅检查项目约定缓存目录 `E:\job\codepilot-lite\.tmp\cp2-swebench-lite-v1`、`E:\job\codepilot-lite\cp2-download`、`E:\job\codepilot-lite\cp2-freeze`；均不存在，未扫描其他用户目录或全盘。官方镜像未核实，本记录不提供猜测的镜像地址。已支持 `--mirror-url`，但使用者须提供可信镜像且内容必须通过官方 SHA 校验。

固定官方 revision：`b0dde1093fe417d83b7184254edf8199c1f0dff5`。Parquet SHA-256：`438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3`。官方文件页：`https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite/blob/b0dde1093fe417d83b7184254edf8199c1f0dff5/data/test-00000-of-00001.parquet`。

尝试下载至 `E:\job\codepilot-lite\cp2-download\test-00000-of-00001.parquet` 被 Windows 网络权限拒绝：`以一种访问权限不允许的方式做了一个访问套接字的尝试。` 文件未生成。因此当前无实际文件 SHA、20 题 freeze manifest 或子集哈希；不宣称数据冻结完成。未调用模型，未运行修复实验。

在可访问 Hugging Face 的 PowerShell 执行以下步骤。哈希不匹配时停止，不运行冻结：

```powershell
$ErrorActionPreference = 'Stop'
$dir = 'E:\job\codepilot-lite\cp2-download'
New-Item -ItemType Directory -Force $dir | Out-Null
$file = Join-Path $dir 'test-00000-of-00001.parquet'
Invoke-WebRequest 'https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite/resolve/b0dde1093fe417d83b7184254edf8199c1f0dff5/data/test-00000-of-00001.parquet' -OutFile $file
$expected = '438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3'
$actual = (Get-FileHash -Algorithm SHA256 $file).Hash.ToLower()
if ($actual -ne $expected) { throw "SHA-256 mismatch: $actual" }
python -m pip install -r E:\job\codepilot-lite\requirements-bench.txt
python -m scripts.fetch_cp2_dataset --fetch --source-file $file --expected-source-sha256 $expected --output-dir E:\job\codepilot-lite\cp2-freeze --mode freeze
python -m scripts.fetch_cp2_dataset --fetch --source-file $file --expected-source-sha256 $expected --output-dir E:\job\codepilot-lite\cp2-freeze --mode verify
```

预期生成 `E:\job\codepilot-lite\cp2-freeze\freeze.json`：固定 revision、源 Parquet SHA、规范化 20 题子集 SHA、task_count=20。数据保存在独立目录，不入 Git、不放 `.tmp`。旧 `frozen-selection.json` 与 holdout 哈希不改。

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

# CP-2 SWE-bench Lite 数据获取

`python -m scripts.fetch_cp2_dataset` 默认只打印计划；显式 `--fetch` 才请求固定 Hugging Face revision `b0dde1093fe417d83b7184254edf8199c1f0dff5` 的 Parquet 文件。官方 LFS SHA-256 固定为 `438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3`。数据写入 ignored `.tmp/cp2-swebench-lite-v1`。可选解析依赖由 `requirements-bench.txt` 固定。freeze 记录分离 `source_parquet_sha256` 与规范化 20 题 `subset_json_sha256`，不覆盖旧 JSON 字节 SHA。下载成功不等于任务执行成功；未运行 20 题，也未加载隐藏测试到 Agent 工作区。

测试：`python -m pytest tests/test_cp2_dataset_fetch.py -q`，2 passed。dry-run 已验证。许可证仍需按每个上游仓库及数据集条款逐项复核。

## 下载与冻结操作记录（2026-11-13）

仅检查项目约定缓存目录 `E:\job\codepilot-lite\.tmp\cp2-swebench-lite-v1`、`E:\job\codepilot-lite\cp2-download`、`E:\job\codepilot-lite\cp2-freeze`；均不存在，未扫描其他用户目录或全盘。官方镜像未核实，本记录不提供猜测的镜像地址。已支持 `--mirror-url`，但使用者须提供可信镜像且内容必须通过官方 SHA 校验。

固定官方 revision：`b0dde1093fe417d83b7184254edf8199c1f0dff5`。Parquet SHA-256：`438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3`。官方文件页：`https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite/blob/b0dde1093fe417d83b7184254edf8199c1f0dff5/data/test-00000-of-00001.parquet`。

早期尝试下载至 `E:\job\codepilot-lite\cp2-download\test-00000-of-00001.parquet` 被 Windows 网络权限拒绝。此记录是当时状态；2026-11-13 后续已在用户宿主下载并核验，见下方最新记录。

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

早期命令示例中的输出位置已被安全收紧：当前冻结器只允许写入仓库 ignored `.tmp/`，旧 `frozen-selection.json` 与 holdout 哈希不改。

## 逐仓许可来源与子集排除边界

| 仓库 | 冻结题数 | 清单声明许可 | 官方许可来源 |
|---|---:|---|---|
| django/django | 4 | BSD-3-Clause | https://github.com/django/django/blob/main/LICENSE |
| pytest-dev/pytest | 4 | MIT | https://github.com/pytest-dev/pytest/blob/main/LICENSE |
| pydata/xarray | 4 | Apache-2.0 | https://github.com/pydata/xarray/blob/main/LICENSE |
| mwaskom/seaborn | 4 | BSD-3-Clause | https://github.com/mwaskom/seaborn/blob/master/LICENSE |
| scikit-learn/scikit-learn | 4 | BSD-3-Clause | https://github.com/scikit-learn/scikit-learn/blob/main/COPYING |

这些 URL 是逐仓许可证核对入口。当前冻结流程用固定 repo→license allowlist 与两份清单交叉核验；它没有检出每个 base revision 并复核许可证文件，故不代表逐 commit 许可证审计完成。

资产脚本 freeze 采用独占创建，已有封存拒绝覆盖；verify 要求源 Parquet SHA、规范化子集 SHA 和 20 个唯一任务全匹配。

## 真实本地数据冻结（2026-11-13）

用户宿主已将官方 Parquet 放入 `E:\job\codepilot-lite\.tmp\release-safe\.tmp\cp2-swebench-lite-v1\test.parquet`。源 SHA-256 为 `438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3`，与固定 revision 的预期值一致。Anaconda Python 环境中的 `pyarrow 21.0.0` 读出 300 行；冻结器选出 20 个唯一 task ID。

冻结前逐题核验 selection、候选清单与 Parquet：仓库、base commit、问题文本 SHA、gold patch SHA、hidden test patch SHA、许可证 allowlist。重复 ID、缺失字段、空 patch、哈希差异和不受支持的许可都会在写入前失败。冻结文件只含问题文本及任务 ID、仓库、base commit、时间和版本，不含 gold patch、hidden test patch、eval script 或镜像配置。

执行：`D:\Anaconda3\python.exe scripts\fetch_cp2_dataset.py --fetch --source-file .tmp\cp2-swebench-lite-v1\test.parquet --expected-source-sha256 438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3 --mode freeze`。结果：20 题，subset SHA-256 `8fb7c6b9a93a3eaef1d0c55839e8d5420ad222447cac7b247735faf23927941d`。随后 `--mode verify` 通过；`git check-ignore` 确认 freeze.json 位于 ignored `.tmp/`。

该结果只证明数据身份与冻结封装。尚未检出 20 个仓库、运行可见/隐藏测试或模型评测；不得称为 20 道可运行修复题。旧选择/holdout 的历史哈希未改。模型调用、费用和成功率均未产生。

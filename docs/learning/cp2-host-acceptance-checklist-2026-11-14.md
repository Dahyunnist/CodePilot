# CP-2 宿主验收清单（2026-11-14）

本清单供 Windows 宿主后续执行。当前轮没有调用 Docker、下载仓库、运行测试、发送模型请求或运行评测。只有所有本清单输入都留下可复核证据后，CP-2 才能解除相应预检阻断。

## 1. 固定输入

仓库为 `E:\job\codepilot-lite` 的发布安全分支 `publish/safe-source-20261024`。本地 Python 使用 NN 环境，命令行示例用：

```powershell
$Python = 'D:\Anaconda3\envs\NN\python.exe'
```

十五个任务的 Docker image tag、当前冻结摘要和待核对 base commit 如下。14 个摘要是冻结文件里的现有值，必须由宿主 `docker image inspect` 重读确认；xarray-4493 是有意留空，不能用 seaborn 或其它 xarray 镜像代替。

| task | image tag | 当前冻结 config digest | base commit |
| --- | --- | --- | --- |
| `django__django-10924` | `swebench/sweb.eval.x86_64.django_1776_django-10924:latest` | `sha256:d41b289ea27a92ef6346702388e5ea0b8c8f48c41d83466a72c2dffb934007a1` | `bceadd2788dc2dad53eba0caae172bd8522fd483` |
| `django__django-11001` | `swebench/sweb.eval.x86_64.django_1776_django-11001:latest` | `sha256:68c61032db48a5eef2175532d3555e20acdd426aa5b426ba3acfe34a0ddd83b7` | `ef082ebb84f00e38af4e8880d04e8365c2766d34` |
| `django__django-11099` | `swebench/sweb.eval.x86_64.django_1776_django-11099:latest` | `sha256:cca302934edd881cc4f1e4647a389a25cdaa3c02bfa33667a4204934a09c4fb1` | `d26b2424437dabeeca94d7900b37d2df4410da0c` |
| `django__django-11133` | `swebench/sweb.eval.x86_64.django_1776_django-11133:latest` | `sha256:914093363dbe12def92c5d36e9bdc5270cce5ed0aa6f3daad8bc4ef0389c29bf` | `879cc3da6249e920b8d54518a0ae06de835d7373` |
| `pytest-dev__pytest-5103` | `swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-5103:latest` | `sha256:1648c614485c81d9e08bcf9ec8014fb38cd2f20fad6bea782552d923a35ce714` | `10ca84ffc56c2dd2d9dc4bd71b7b898e083500cd` |
| `pytest-dev__pytest-5221` | `swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-5221:latest` | `sha256:547472f1933751a67623599dae697188232c9712a46ab66fb69330f88b911e5a` | `4a2fdce62b73944030cff9b3e52862868ca9584d` |
| `pytest-dev__pytest-5413` | `swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-5413:latest` | `sha256:75700210c9eb925d1abde2cb95b7dfffc2c409376ae434854375bacaa193864f` | `450d2646233c670654744d3d24330b69895bb9d2` |
| `pytest-dev__pytest-5495` | `swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-5495:latest` | `sha256:86b356cf05ac9a623ba8943849e25ce2d0bcebc506753b1361595e5ad488a9b3` | `1aefb24b37c30fba8fd79a744829ca16e252f340` |
| `pydata__xarray-3364` | `swebench/sweb.eval.x86_64.pydata_1776_xarray-3364:latest` | `sha256:8591047f512d8d26b4d0e121d2d04eb6b95fa6ad41e13d92fe64f5ef66244c27` | `863e49066ca4d61c9adfe62aca3bf21b90e1af8c` |
| `pydata__xarray-4094` | `swebench/sweb.eval.x86_64.pydata_1776_xarray-4094:latest` | `sha256:6bcd1fe581af0796691ac3527b940d43e5e1bfd6539adeecebb12f3e4b25dc2c` | `a64cf2d5476e7bbda099b34c40b7be1880dbd39a` |
| `pydata__xarray-4248` | `swebench/sweb.eval.x86_64.pydata_1776_xarray-4248:latest` | `sha256:d16aca15c86b2ef8a698600711bfde3559f794154a0edd4ac4213edf6b6fdf73` | `98dc1f4ea18738492e074e9e51ddfed5cd30ab94` |
| `pydata__xarray-4493` | `swebench/sweb.eval.x86_64.pydata_1776_xarray-4493:latest` | **缺失，须宿主实际检查后记录** | `a5f53e203c52a7605d5db799864046471115d04f` |
| `mwaskom__seaborn-2848` | `swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-2848:latest` | `sha256:d719470351e66623e532a4f23cdedfe8fb737147fe108e4b5829aa273528389d` | `94621cef29f80282436d73e8d2c0aa76dab81273` |
| `mwaskom__seaborn-3010` | `swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3010:latest` | `sha256:22fef36e8b9655fb1642d976de669e3f2426df0186a09d6d788fc6215cfa1bc0` | `0f5a013e2cf43562deec3b879458e59a73853813` |
| `scikit-learn__scikit-learn-10508` | `swebench/sweb.eval.x86_64.scikit-learn_1776_scikit-learn-10508:latest` | `sha256:4c25a7511f252ed93ce8555f6bb84ffb8d56baa46151e3df5b4338cb2f228677` | `c753b77ac49e72ebc0fe5e3c2369fe628f975017` |

## 2. 镜像摘要与 exact-base 检查

先确认 Docker Server 可用：

```powershell
docker version
```

预期 Client、Server 两段都成功；只有 Client 版本或 Server 连接错误都不算通过。逐项读取本机实际镜像 config digest，并与上表现有值比对：

```powershell
$m = Get-Content 'evals/public_cases/cp2/benchmark-v1.json' -Raw | ConvertFrom-Json
foreach ($t in $m.tasks) {
    $actual = docker image inspect --format '{{.Id}}' $t.docker_image_ref 2>$null
    if ($LASTEXITCODE -ne 0) {
        "MISSING $($t.task_id) $($t.docker_image_ref)"
        continue
    }
    "IMAGE $($t.task_id) actual=$actual frozen=$($t.docker_image_config_digest)"
}
```

通过条件：15/15 tag 均可 inspect；14 个已有摘要逐字节相等；xarray-4493 返回真实的 `sha256:<64位小写十六进制>`，再把这条宿主输出作为新证据记录。摘要不匹配时停止，不把 tag 当前指向的内容悄悄覆盖成冻结值。

对每个匹配镜像，以镜像 ID 而非可变 `latest` tag 检查 `/testbed` 中的实际 Git HEAD：

```powershell
$imageId = 'sha256:<上一步实测的config digest>'
docker run --rm --network none --entrypoint bash $imageId -lc 'git -C /testbed rev-parse HEAD'
```

预期只输出上表对应的 40 位 `base commit`。路径不存在、Git 不可用或 SHA 不同，都记为未验证并停止该题。

许可证也必须从该精确 base 的根目录读取；不要用当前 `main` 分支文件名推断历史文件名：

```powershell
docker run --rm --network none --entrypoint bash $imageId -lc 'cd /testbed && git ls-tree --name-only HEAD | grep -E "^(LICENSE(\.md)?|COPYING)$"'
docker run --rm --network none --entrypoint bash $imageId -lc 'cd /testbed && sha256sum LICENSE'
```

第二条的文件名必须替换为第一条在该镜像、该 base 中实际列出的许可文件。预期证据需记录 `task_id`、实测镜像 config digest、`git rev-parse HEAD`、经文件内容核对的 SPDX 标识、精确许可路径、许可文件 SHA-256，以及保存这些原始输出的证据文件路径和该证据文件 SHA-256。旧 `benchmark-v1.json` 里已有的许可路径/摘要只能作为待比对值，不能代替这次原始输出；若不一致，先查清原因再更新。

## 3. 测试入口和可见测试

官方 SWE-bench 数据结构把 `issue_url`、`pr_url`、`base_commit`、`patch`、`test_patch` 分开记录；`test_patch` 属于 benchmark oracle 材料，不能把它复制成 CP-2 的公开可见测试。[官方数据说明](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/datasets.md)

已从一手 PR 的 Files 页面直接确认的公开回归测试入口包括：Django 10924/11001/11099/11133，pytest 5103/5221，xarray 4094，seaborn 2848/3010，scikit-learn 10508。示例：[Django 10924 测试文件](https://github.com/django/django/pull/10924/files)、[pytest 5103 测试文件](https://github.com/pytest-dev/pytest/pull/5103/files)、[xarray 4094 测试文件](https://github.com/pydata/xarray/pull/4094/files)、[seaborn 3010 测试文件](https://github.com/mwaskom/seaborn/pull/3010/files)、[scikit-learn 10508 测试文件](https://github.com/scikit-learn/scikit-learn/pull/10508/files)。pytest 5413/5495、xarray 3364/4248/4493 的 PR 文件页在本轮公开页面读取中未能载入 changed-file 列表；现有 `hidden_test_files` 路径是候选数据集的 oracle 文件清单，不能冒充已确认的公开 visible test。

目前仓库中 `evals/public_cases/cp2/cases/` 不存在。CP-2 的 `visible_test_spec_sha256` 只校验一句规格文字；它不证明可执行测试存在。现有 `prepare_swebench_lite.py` 从原数据读取 `test_patch` 并把隐藏补丁写进案例目录，CP-2 的 `plan()` 会拒绝这种带隐藏测试元数据的案例，所以它不能直接作为 CP-2 可见测试物化命令。另一个 runner 事实是：`live_runner.py` 执行 `case.json.test_command`，只把 `visible_tests/` 的目录哈希写入运行记录，没有把 `visible_tests/` 文件放进运行副本；因此单独创建该目录也不会执行其中的测试。

宿主验收前必须先有专用的 CP-2 visible-only case 构建结果：15 个 `case.json`、精确 base 的 `repo/`、独立编写并审核的公开测试、实际 `test_command`、测试目录 SHA-256，以及每题 base 上预期失败、修复后通过的 baseline 记录。不得把 `test_patch` 内容或隐藏测试文件带入该目录。当前没有可给出的“测试通过”预期输出；成功条件是 15 个 case 的 hash 和 baseline 证据都被 validator 接受。

独立可见测试文件 SHA-256 的计算应与 `live_runner._directory_sha256()` 一致：按相对 POSIX 路径排序；对每个文件追加路径 UTF-8 字节、一个 `NUL` 字节、再追加该文件内容的 SHA-256 原始 32 字节。目录必须至少含一个普通文件；空目录的哈希不能当作通过。

## 4. 本机代码与无模型回归

先运行本机纯 Python 回归，不会请求模型或调用 Docker：

```powershell
& $Python -m pytest tests/test_cp2_benchmark.py tests/test_benchmark_manifest_integrity.py -q --basetemp=.tmp\pytest-cp2-host-gates
```

预期 `19 passed`（以当前分支测试集为准）。需要查看只读预检时，先提供真实且已审计的账本后再运行：

```powershell
& $Python -m evals.cp2_benchmark plan --manifest evals/public_cases/cp2/benchmark-v1.json --ledger evals/public_cases/cp2/budget-ledger-v1.json --cases evals/public_cases/cp2/cases
```

当前仓库没有 `budget-ledger-v1.json` 和 `cases/`，所以这条命令暂时不能通过。即使宿主把上面的镜像和许可证核验完成，只要测试物化、baseline、工件摘要、预算对账任一仍缺，plan 也必须返回非零并列出阻断项；这才是正确的 fail-closed 结果。不要运行 `run`，直到 `plan` 无 blocker 且另行批准模型预算。

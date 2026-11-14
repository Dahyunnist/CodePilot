# CP-2 seaborn-2848 宿主 Docker 验证记录（2026-11-14）

## 结果与来源

- 镜像：`swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-2848:latest`
- 镜像 ID：`sha256:d719470351e66623e532a4f23cdedfe8fb737147fe108e4b5829aa273528389d`。
- 容器工作目录：`/testbed`。镜像 HEAD 是 `a110ef5b2bca99904daf60a6e10e7e5bda8d98d6`；父提交（公开基线）是 `94621cef29f80282436d73e8d2c0aa76dab81273`，与 case 的 `source_commit` 一致。
- visible test：`tests/test_relational.py`；Windows checkout 字节 SHA-256 `541484E556DD195F73EF0D916820999FDCACDF28F591251656A6BED70715FD76`。case 元数据记录规范化 LF 文件 SHA-256 `76dbfd47cba045bc87f0ed428b85cda106d63f2dd16000dbfdff1ceef4f013a1`。
- 从镜像父提交抽出的唯一基线源码文件 `seaborn/_oldcore.py` SHA-256 `93336117B3C11561F63C7DE7235F9EA79D680C7582489ABFFC779012DD09BEE8`。
- 修复副本 SHA-256 `E3E5F6BDAB89113585ED890C68D4FD4900DB448484DCC86B9402786953ADE28C`。唯一变更是在 `HueMapping._lookup_single` 检查 `self.norm is None` 并返回透明色 `(0, 0, 0, 0)`。
- 基线结果：`test_hue_order` **1 failed, 72 deselected**，类别 `c` 触发颜色映射 `TypeError`；pytest 退出码 **1**。
- 修复结果：`test_hue_order` **1 passed, 72 deselected**；pytest 退出码 **0**。两次均有 12 条现存 Matplotlib `register_cmap` 弃用警告。
- NN 离线回归：`tests/test_cp2_benchmark.py tests/test_execute.py` 排除一个依赖未提供 `.tmp/cp2-single-preflight` 数据的用例后，**43 passed, 1 deselected**。
- 测试只读挂载公开 visible test 和一个目标源码文件，容器使用 `--network none`。没有导出完整仓库，没有读取或运行隐藏测试，没有调用模型。

## PowerShell 复现命令

在 `E:\job\codepilot-safe-validation` 工作树根目录执行。命令只从镜像父提交导出一个公开源码文件：

```powershell
$root = 'E:\job\codepilot-safe-validation'
$case = Join-Path $root 'evals\public_cases\cp2\cases\mwaskom__seaborn-2848'
$out = Join-Path $root 'verification-artifacts\seaborn-2848'
$image = 'swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-2848:latest'
$python = '/opt/miniconda3/envs/testbed/bin/python'
New-Item -ItemType Directory -Force -Path $out | Out-Null

docker run --rm --network none --volume "${out}:/out" $image sh -lc 'git -C /testbed show HEAD^:seaborn/_oldcore.py > /out/oldcore-baseline.py'
Get-FileHash (Join-Path $out 'oldcore-baseline.py') -Algorithm SHA256
```

运行基线；预期失败，退出码 1：

```powershell
$baseline = Join-Path $out 'oldcore-baseline.py'
$visible = Join-Path $case 'visible_tests\tests\test_relational.py'
docker run --rm --network none --volume "${baseline}:/testbed/seaborn/_oldcore.py:ro" --volume "${visible}:/testbed/tests/test_relational.py:ro" --workdir /testbed $image $python -m pytest tests/test_relational.py -p no:cacheprovider -k test_hue_order -q
$rc = $LASTEXITCODE; Write-Output "pytest_exit=$rc"; exit $rc
```

生成并运行修复副本；预期通过，退出码 0：

```powershell
$source = Get-Content (Join-Path $out 'oldcore-baseline.py') -Raw
$before = "        except KeyError:`n            # Use the colormap to interpolate between existing datapoints"
$after = "        except KeyError:`n            if self.norm is None:`n                return (0, 0, 0, 0)`n            # Use the colormap to interpolate between existing datapoints"
if (-not $source.Contains($before)) { throw '2848 base source context mismatch' }
$fixed = Join-Path $out 'oldcore-fixed.py'
[System.IO.File]::WriteAllText($fixed, $source.Replace($before, $after), [System.Text.UTF8Encoding]::new($false))
Get-FileHash $fixed -Algorithm SHA256

docker run --rm --network none --volume "${fixed}:/testbed/seaborn/_oldcore.py:ro" --volume "${visible}:/testbed/tests/test_relational.py:ro" --workdir /testbed $image $python -m pytest tests/test_relational.py -p no:cacheprovider -k test_hue_order -q
$rc = $LASTEXITCODE; Write-Output "pytest_exit=$rc"; exit $rc
```

## 样本限制

此测试实际覆盖 `scatterplot`。冻结任务描述写了 pairplot，但公开 PR 测试不测试 pairplot；不能把结果外推到 pairplot。本次验证只证明此公开回归测试通过，不代表 seaborn 完整测试套件通过，也不代表真实模型修复成功。

# CP-2 seaborn-3010 宿主 Docker 验证记录（2026-11-14）

## 结果

- 镜像：`swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3010:latest`
- 镜像 ID：`sha256:22fef36e8b9655fb1642d976de669e3f2426df0186a09d6d788fc6215cfa1bc0`。
- 容器工作目录：`/testbed`。镜像 HEAD 是 `191ec3379337aea8e27e61f8fd3dd11411a8654f`；其父提交，即公开基线，是 `0f5a013e2cf43562deec3b879458e59a73853813`，与 case 的 `source_commit` 一致。
- visible test：`tests/_stats/test_regression.py`；当前 Windows checkout 字节 SHA-256 `B70030ED70CC95C39BD8FAA02D16491A0ED4F4AA28306B2945C8771D4934A2BE`。case 元数据记录规范化 LF 文件 SHA-256 `c68053590168ce35c79d499e2b33e0e7ca3aff7319b0feb09770065c9bb66ad9`。
- 从镜像父提交抽出的单一基线源码文件 `seaborn/_stats/regression.py` SHA-256 `B6AF5792468FA0CBFD739D68437D53289377A964F7BB3C4F74FEDEABDECE555E`。
- 修复副本 SHA-256 `93B087FB9B7EFB08E155D9D65F04ACCF9B76F72D3D86C2BD89471A656D30C3C4`。唯一变更是在 PolyFit 拟合前用 `data.dropna(subset=["x", "y"])` 过滤缺失值。
- 基线结果：`test_missing_data` **1 failed, 2 deselected**，错误为 `numpy.linalg.LinAlgError: SVD did not converge in Linear Least Squares`；pytest 退出码 **1**。
- 修复结果：`test_missing_data` **1 passed, 2 deselected**；pytest 退出码 **0**。
- 本地 NN 定向回归：`tests/test_cp2_benchmark.py tests/test_execute.py` 排除一个需要仓库内 `.tmp/cp2-single-preflight` 数据的用例后，**43 passed, 1 deselected**。未排除时该用例因该工作树不含所需文件而报 `FileNotFoundError`；没有该路径，也没有读到或创建其中数据。
- 只挂载一个公开测试文件和一个目标源码文件；挂载均只读。容器使用 `--network none`。没有读取或运行隐藏测试，没有调用模型。

## PowerShell 复现命令

在安全分支工作树根目录 `E:\job\codepilot-safe-validation` 执行。以下步骤只从镜像导出公开基线的一个源码文件，并把修复写入系统临时目录。

```powershell
$root = 'E:\job\codepilot-safe-validation'
$case = Join-Path $root 'evals\public_cases\cp2\cases\mwaskom__seaborn-3010'
$out = Join-Path $root 'verification-artifacts\seaborn-3010'
$image = 'swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3010:latest'
$python = '/opt/miniconda3/envs/testbed/bin/python'
New-Item -ItemType Directory -Force -Path $out | Out-Null

# 精确从镜像父提交导出公开基线文件；不导出隐藏测试或完整仓库。
docker run --rm --network none --volume "${out}:/out" $image sh -lc 'git -C /testbed show HEAD^:seaborn/_stats/regression.py > /out/regression-baseline.py'
Get-FileHash (Join-Path $out 'regression-baseline.py') -Algorithm SHA256
```

运行基线。该命令最后返回 pytest 的真实退出码 1，这是预期失败：

```powershell
$baseline = Join-Path $out 'regression-baseline.py'
$visible = Join-Path $case 'visible_tests\tests\_stats\test_regression.py'
docker run --rm --network none --volume "${baseline}:/testbed/seaborn/_stats/regression.py:ro" --volume "${visible}:/testbed/tests/_stats/test_regression.py:ro" --workdir /testbed $image $python -m pytest tests/_stats/test_regression.py -p no:cacheprovider -k test_missing_data -q
$rc = $LASTEXITCODE; Write-Output "pytest_exit=$rc"; exit $rc
```

生成并运行修复副本。精确源代码上下文不匹配时停止：

```powershell
$source = Get-Content (Join-Path $out 'regression-baseline.py') -Raw
$before = 'return groupby.apply(data, self._fit_predict)'
$after = 'return groupby.apply(data.dropna(subset=["x", "y"]), self._fit_predict)'
if (-not $source.Contains($before)) { throw '3010 base source context mismatch' }
$fixed = Join-Path $out 'regression-fixed.py'
[System.IO.File]::WriteAllText($fixed, $source.Replace($before, $after), [System.Text.UTF8Encoding]::new($false))
Get-FileHash $fixed -Algorithm SHA256

docker run --rm --network none --volume "${fixed}:/testbed/seaborn/_stats/regression.py:ro" --volume "${visible}:/testbed/tests/_stats/test_regression.py:ro" --workdir /testbed $image $python -m pytest tests/_stats/test_regression.py -p no:cacheprovider -k test_missing_data -q
$rc = $LASTEXITCODE; Write-Output "pytest_exit=$rc"; exit $rc
```

## 限制

此记录只验证 seaborn-3010。seaborn-2848 本轮没有 Docker 基线或修复结果。验证工作树不带 `cp2-single-preflight` 临时数据，依赖它的一个旧用例无法在此复核。没有模型调用，因此没有模型成本或模型耗时。

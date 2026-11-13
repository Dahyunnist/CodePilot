# CP-2 Django 可见测试预检命令（2026-11-13）

本地单题输入已核对：`one-task.json` SHA-256 `d12214881ed1ef50aaf2153d2b329b24285ae1f68dca46c64d22b7dedaff00fb`；`prepared/django__django-11133/case.json` SHA-256 `a84d45bc56d1d49adc32b0048b920c0c7c4aad3ed43b8d994bb339617c746f51`。公开命令为 `python -m pytest tests/httpwrappers/tests.py -q`。此处没有启动 Docker。

在项目根目录普通 PowerShell 执行以下命令。它只把 repo 子目录复制到 `.tmp` 隔离 workspace；容器无网络、根文件系统只读、丢弃 capabilities，只读挂载 workspace，不挂载 case 私有目录或 Docker socket。输出重定向到 `.tmp` 日志，不包含隐藏 patch/test 内容。

```powershell
$ErrorActionPreference = 'Stop'
$case = (Resolve-Path '.tmp/cp2-single-preflight/prepared/django__django-11133').Path
$workspace = Join-Path (Resolve-Path '.tmp').Path 'cp2-django-11133-visible-workspace'
$log = Join-Path (Resolve-Path '.tmp').Path 'cp2-django-11133-visible.log'
if (Test-Path $workspace) { throw "Refusing to overwrite $workspace" }
New-Item -ItemType Directory -Path $workspace | Out-Null
Copy-Item -Path (Join-Path $case 'repo\*') -Destination $workspace -Recurse
$image = 'swebench/sweb.eval.x86_64.django_1776_django-11133:latest'
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 512m --cpus 1 --tmpfs /tmp:rw,noexec,nosuid,size=64m --mount "type=bind,source=$workspace,target=/workspace,readonly" --workdir /workspace $image /opt/miniconda3/envs/testbed/bin/python -m pytest tests/httpwrappers/tests.py -q *> $log
if ($LASTEXITCODE -ne 0) { throw "Visible preflight failed; inspect redacted summary in $log" }
Get-Content $log | Select-Object -Last 8
```

期望可见测试全部通过并显示 pytest 汇总。该命令不应用 hidden patch、不调用模型，也不代表隐藏测试或 Agent 修复通过。仓库当前仅提交命令构造安全测试；真实 Docker 预检须用户本机运行后回传状态和摘要。

# S19：Requests 多进程异常序列化评测冻结

**状态：一个全新真实缺陷已冻结；准备与基线/金标准验证完成后，方可调用模型。每项只运行一次。**

## 任务

Requests #6628 报告 `JSONDecodeError` 经 pickle 反序列化失败，使 `ProcessPoolExecutor` 进程池损坏；上游合并修复为 PR #6629。任务使用 Requests 2.31.0 sdist，SHA-256：`942c5a758f98d790eaed1a29cb6eefc7ffb0d1cf7af05c3d2791656dbd6ad1e1`。

来源：[issue #6628](https://github.com/psf/requests/issues/6628)、[修复 PR #6629](https://github.com/psf/requests/pull/6629)。

## 验收设计

- 可见测试直接 pickle round-trip `requests.exceptions.JSONDecodeError`，检查类型、repr、错误消息、文档和位置。
- 隐藏测试在 `ProcessPoolExecutor` 中抛出该异常，检查主进程收到原异常且进程池还能继续执行任务。
- Docker 镜像断网、非 root、只读根文件系统；依赖版本固定在 `docker/public-requests-runner.Dockerfile`。
- 独立金标准使用 Requests 的上游修复：在 `JSONDecodeError` 中调用 `CompatJSONDecodeError.__reduce__(self)`。
- 未修复基线在 pickle round-trip 断言失败；金标准可见测试和隐藏进程池测试均通过。

## 运行配置

准备案例：

```powershell
python -m evals.public_cases.prepare_s19_cases `
  --archives .tmp/public-bench-sources `
  --output .tmp/public-s19-frozen
```

构建镜像：

```powershell
docker build -f docker/public-requests-runner.Dockerfile `
  -t codepilot-requests-runner:s19-20261020 .
```

冻结 Docker 镜像 ID：`sha256:212c1ac230b762dc874f413e345364f3cf9cd42f2923be1b20bf6fdf94106e0c`。

单项使用 100k Token、16 步上限；60k 上限在 S18 的三项任务中仍不足以保留最终测试和收尾调用。真实模型运行前再核对 `$4` 总账，任务只调用一次。

## 解释边界

一项公开 issue 只作为预算校准样本；它不能表示大型仓库或通用修复能力。公开 issue 和 PR 可能已被模型见过。S19 结果必须单独记录，不与金标准测试通过混为 Agent 成功。

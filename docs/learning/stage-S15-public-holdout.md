# S15：Requests 多进程异常传输 holdout

## 公开任务

Requests 上游 issue [#6628](https://github.com/psf/requests/issues/6628) 报告 `JSONDecodeError` 无法经 pickle 恢复，进而让 `ProcessPoolExecutor` 崩溃。上游修复在 [PR #6629](https://github.com/psf/requests/pull/6629)。案例使用问题发生时的 Requests 2.31.0 官方 PyPI sdist；源码包 SHA-256 固定在案例元数据。

可见测试覆盖异常的 pickle 往返和 JSON 字段；隐藏测试覆盖跨进程异常传输，以及进程池收到异常后继续执行任务。

## 冻结规则

- 本阶段测试、说明、源码归档校验和 Docker 环境在首次模型调用前提交。
- holdout 首次运行后，不改任务说明、测试断言或金标准。
- Docker 使用 Python 3.11、Requests 运行依赖固定版本、断网、只读、非 root 和资源限制；镜像从 `docker/public-runner-s15.Dockerfile` 构建。
- 评测工作副本由 `evals.public_cases.prepare_s15_cases` 从已校验 sdist 生成。

## 验收

必须同时满足 Agent 自测、独立可见测试和隐藏多进程测试通过。报告记录模型、预算、usage Token、估算费用、耗时、工具调用、补丁散列和完整失败轨迹。

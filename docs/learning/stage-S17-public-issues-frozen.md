# S17：三项公开问题评测冻结

**状态：任务、基线和验证测试已冻结；尚未调用真实模型。**

本阶段新增三个来自上游 issue 的独立任务。第一次真实模型调用必须发生在本文件和全部案例文件提交之后。每个任务仅运行一次；失败结果不重跑、不覆盖。

## 冻结任务

| 案例 | 上游问题与修复 | 缺陷类型 | 固定源码 |
|---|---|---|---|
| `flask-4831` | [Flask #4831](https://github.com/pallets/flask/issues/4831)，[修复 PR #4840](https://github.com/pallets/flask/pull/4840) | `.svg` 模板自动转义与安全边界 | Flask 2.2.2，SHA-256 `642c450d19c4ad482f96729bd2a8f6d32554aa1e231f4f6b4e7e5264b16cca2b` |
| `urllib3-3649` | [urllib3 #3649](https://github.com/urllib3/urllib3/issues/3649)，[修复 PR #3655](https://github.com/urllib3/urllib3/pull/3655) | PoolManager 整数重试参数导致重定向失效 | urllib3 2.5.0，SHA-256 `3fc47733c7e419d4bc3f6b3dc2b4f890bb743906a30d56ba4a5bfa4bbff92760` |
| `urllib3-3700` | [urllib3 #3700](https://github.com/urllib3/urllib3/issues/3700)，[修复 PR #3705](https://github.com/urllib3/urllib3/pull/3705) | `SSLKEYLOGFILE` 中环境变量路径未展开 | urllib3 2.5.0，同上 |

Flask 的 issue 与 urllib3 的变更也能在各自的[官方变更记录](https://github.com/pallets/flask/blob/main/CHANGES.rst)和[官方变更记录](https://github.com/urllib3/urllib3/blob/main/CHANGES.rst)核对。Flask 与 urllib3 的任务分别使用独立源码副本；两个 urllib3 任务修改不同模块，测试彼此无依赖。

## 测试设计和污染控制

- 每项任务有独立可见测试和独立隐藏测试。可见测试随源码进入 Agent 工作副本；隐藏测试留在案例目录外，只在补丁产出后挂载到验证容器。
- 所有评测从只读冻结基线复制工作副本。独立验收重新从冻结基线复制，再叠加 Agent 对生产源码的改动；测试目录、pytest 配置、`conftest.py` 和 `sitecustomize.py` 不从 Agent 副本回写。
- urllib3 #3649 使用本地回环 HTTP 服务验证重定向，不访问公网。#3700 用临时目录和环境变量验证路径展开。Flask 用临时 SVG 模板验证转义结果。
- 源码准备器校验 PyPI sdist SHA-256，拒绝覆盖已有输出，并调用已有安全解包器拒绝路径穿越、链接和设备文件。
- 从归档排除 Flask 的 `tests/test_apps/.env` 和 urllib3 的私钥/证书测试文件。模型 API key 只由主机侧配置读取，不进入测试容器。
- Agent 无法读取隐藏测试目录。验证容器断网、非 root、只读根文件系统、删除全部 Linux capabilities，并限制进程数、内存和 CPU。

## 基线和金标准验证

基线均使用与正式 live runner 相同的固定镜像 `codepilot-public-runner:20261020`，镜像 ID：
`sha256:308e3d3864738b8287b7387bf060681a67748ab7666847ace900c58d10d55100`。
Docker Engine 为 Linux/amd64 29.1.3。

| 案例 | 未修复基线 | 独立已知修复副本：可见 | 独立已知修复副本：隐藏 |
|---|---|---:|---:|
| `flask-4831` | 目标断言失败；其他 Flask 模板测试通过 | 通过 | 通过 |
| `urllib3-3649` | `PoolManager(retries=3)` 遇重定向抛 `MaxRetryError` | 通过 | 通过 |
| `urllib3-3700` | 未展开的 `$CODEPILOT_TLS_LOG_DIR` 导致 `FileNotFoundError` | 通过 | 通过 |

金标准代码只用于 `.tmp/public-s17-gold/` 下的独立副本，不在 Agent 可见仓库中，也不会提交。三个任务的可见与隐藏测试均由金标准修复副本通过。测试没有依赖上游服务或网络。

## 可复现方式

准备器需要以下 PyPI 源码包，并会再次核对 SHA-256：

- Flask 2.2.2：[源码归档](https://files.pythonhosted.org/packages/69/b6/53cfa30eed5aa7343daff36622843688ba8c6fe9829bb2b92e193ab1163f/Flask-2.2.2.tar.gz)
- urllib3 2.5.0：[源码归档](https://files.pythonhosted.org/packages/15/22/9ee70a2574a4f4599c47dd506532914ce044817c7752a79b6a51286319bc/urllib3-2.5.0.tar.gz)

```powershell
python -m evals.public_cases.prepare_s17_cases `
  --archives <源码归档目录> `
  --output <新的空目录>

python -m evals.live_runner `
  --cases <准备后的目录> `
  --case-ids flask-4831 urllib3-3649 urllib3-3700 `
  --execution docker `
  --docker-image codepilot-public-runner:20261020 `
  --max-total-tokens 25000 `
  --max-steps 8
```

Docker 镜像由仓库内固定基础镜像摘要和锁定依赖的 `docker/public-runner.Dockerfile` 构建。已有镜像标签不得代替上表不可变镜像 ID。评测时宿主机须提供 Docker Desktop 和模型 API 配置；测试容器不需要网络或 API 密钥。

## 解释边界

这是三项公开 issue 的小样本诊断，不等同于 SWE-bench，也不足以声称 CodePilot 与 SWE-agent 或 OpenHands 达到同等能力。来源、任务数、运行镜像和独立测试会固定，报告失败、用量、估算成本和耗时；模型可能已在训练数据中见过公开修复，无法消除这种污染风险。

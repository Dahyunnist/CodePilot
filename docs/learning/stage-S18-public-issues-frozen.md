# S18：公开问题评测冻结

**状态：任务、源码校验和测试已冻结；此提交之后才可调用真实模型。** 每项任务运行一次；任务失败后不重复调用。

## 任务

| 案例 | 上游问题与修复来源 | 类型 | 固定源码 |
|---|---|---|---|
| `click-3084` | [Click #3084](https://github.com/pallets/click/issues/3084)，[PR #3152](https://github.com/pallets/click/pull/3152) | 带默认值的可选 flag 参数解析 | Click 8.3.1，SHA-256 `f3999c7e787a93e159eb78a97db7a768a441509795a23f3a060bde24362ff38d` |
| `click-3121` | [Click #3121](https://github.com/pallets/click/issues/3121)，[PR #3225](https://github.com/pallets/click/pull/3225) | flag 默认值错误实例化类 | 同上 |
| `flask-4777` | [Flask #4777](https://github.com/pallets/flask/issues/4777)，[Flask 2.2.3 变更记录](https://github.com/pallets/flask/blob/2.2.3/CHANGES.rst) | `flask run --debug` 功能缺口 | Flask 2.2.2 sdist，SHA-256 `642c450d19c4ad482f96729bd2a8f6d32554aa1e231f4f6b4e7e5264b16cca2b` |

Click 案例来自同一源码归档，但任务和工作副本隔离，分别覆盖参数值解析与默认值解析。Flask 变更记录确认 2.2.3 加入 `flask run --debug`；上游 issue 页面未关联 PR，因此不虚构 PR 编号。

## 验收与隔离

- 每项有可见测试和案例目录外隐藏测试；模型只看到可见测试。
- 基线需在固定 Docker 镜像中失败；独立金标准副本需通过可见和隐藏测试。
- Docker 容器断网、非 root、只读根文件系统。模型密钥只留在主机环境。
- 源码包 SHA-256 在准备前校验。归档解包使用现有安全解包器。
- S17 用 25k Token 预算在保护测试和最终答复时过早停止。S18 每项冻结上限 60k Token、12 步、300 秒；成本账本须在调用前重新核对，累计支出上限为用户设定的 $4。

## 准备

```powershell
python -m evals.public_cases.prepare_s18_cases `
  --click-archive .tmp/real-click-download/click-8.3.1-stage9.zip `
  --flask-archives .tmp/public-bench-sources `
  --output .tmp/public-s18-frozen
```

准备后，分别用 `evals.live_runner --cases .tmp/public-s18-frozen --case-ids click-3084 click-3121 flask-4777 --execution docker` 评测。Docker 镜像固定为 `codepilot-public-runner:20261020`，镜像 ID 为 `sha256:308e3d3864738b8287b7387bf060681a67748ab7666847ace900c58d10d55100`。

## 解释边界

三项公开问题只是小样本诊断，不等同 SWE-bench，也不能用于声称与 SWE-agent 或 OpenHands 能力相当。公开问题和修复可能已进入模型训练数据。Click 两项共用仓库版本，结果需按单项报告。

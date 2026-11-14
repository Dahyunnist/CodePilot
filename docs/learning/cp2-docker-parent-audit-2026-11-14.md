# CP-2 Docker 父提交审计与勘误（2026-11-14）

## 更正

上一份预检只比较 `/testbed` 的 `HEAD`，据此误判 15 个镜像都不是冻结 base。SWE-bench 镜像会创建一个作者为 `SWE-bench` 的合成提交；应检查该提交的第一个父提交。

重新核验后，15/15 镜像的 `HEAD^` 都与任务冻结的 `base_commit` 完全一致。`HEAD^` 到合成 `HEAD` 的差异只改变文件执行位（`100644` 到 `100755`）；每个文件的 Git blob ID 相同，没有内容差异。之前记录的 LICENSE 内容摘要也吻合；seaborn-3010 的实际文件名为 `LICENSE.md`，xarray-4493 为 `LICENSE`。

因此，镜像精确 base 检查通过；不需要用户再运行 Docker 或下载缺失镜像。原始镜像摘要和逐题容器输出见[首次宿主检查证据](cp2-docker-host-inspection-2026-11-14.json)，合成提交父 SHA、Git 树与文件模式摘要见[父提交审计证据](cp2-docker-parent-audit-2026-11-14.json)，SHA-256：`4373816d84a0fca118c6b035a938fce8b5ad0c96736c653830de902ef3033f58`。

## 逐题核验

| task | 冻结 base = HEAD^ | blob 内容相同的模式变更文件数 |
| --- | --- | ---: |
| `django__django-10924` | 是 | 6062 |
| `django__django-11001` | 是 | 6063 |
| `django__django-11099` | 是 | 6061 |
| `django__django-11133` | 是 | 6056 |
| `pytest-dev__pytest-5103` | 是 | 417 |
| `pytest-dev__pytest-5221` | 是 | 432 |
| `pytest-dev__pytest-5413` | 是 | 424 |
| `pytest-dev__pytest-5495` | 是 | 444 |
| `pydata__xarray-3364` | 是 | 231 |
| `pydata__xarray-4094` | 是 | 254 |
| `pydata__xarray-4248` | 是 | 256 |
| `pydata__xarray-4493` | 是 | 261 |
| `mwaskom__seaborn-2848` | 是 | 257 |
| `mwaskom__seaborn-3010` | 是 | 284 |
| `scikit-learn__scikit-learn-10508` | 是 | 1082 |

## 剩余 CP-2 阻断

- `benchmark-v1.json` 仍冻结旧版工件哈希；不要原地改写。应基于本证据生成新版本，并补齐 xarray-4493 镜像摘要、seaborn-3010 精确许可证路径和逐题 provenance。
- 15 题公开可见测试尚未物化，也没有 base 失败/修复后通过的 baseline。
- 预算账本和供应商消费对账尚缺；真实模型运行仍被预算闸门禁止。
- `evals/public_cases/cp2/reproductions/django_10924/` 继续保持未读取、未修改、未纳入提交。

当前没有需要用户执行的 Docker 命令。后续要启动真实模型评测时，最小用户输入是 DeepSeek 可导出的消费明细或账单，用于核对项目预算账本；其余可见测试准备可继续由本机完成。

# CP-2：Django 10924 公开样例切片

## 范围与来源

- 仓库：`django/django`
- 基线提交：`bceadd2788dc2dad53eba0caae172bd8522fd483`
- 基线 tree：`7efb2d995f2a78b9b6a596303807d300a64febbf`
- 公开 PR：<https://github.com/django/django/pull/10924>
- 问题：<https://code.djangoproject.com/ticket/29529>
- PR head：`ef082ebb84f00e38af4e8880d04e8365c2766d34`
- Docker 镜像：`swebench/sweb.eval.x86_64.django_1776_django-10924:latest`
- 镜像 digest：`sha256:d41b289ea27a92ef6346702388e5ea0b8c8f48c41d83466a72c2dffb934007a1`
- 公开回归测试：`tests/model_fields/test_filepathfield.py`，来自 PR 文件列表。
- 源文件清单：6073 个基线文件；清单 SHA-256 为 `2a143204199aa7df7f8abab538e6342621bacee67ff0f7f5016e8e9389e29ce6`。
- 可见测试 SHA-256：`805a530e676cf0ba4177153eb82b4635e7132a7a82af57d4e0245ef44dd03724`。
- 原始 source archive SHA-256：`8d2b311b516a9af774ce6109bd37631f146a1725aa17c8c8813b06d19aa28fb8`。

样例只包含精确基线、公开 PR 测试和公开元数据。没有读取、复制或使用 SWE-bench hidden test patch、gold patch 或隐藏测试。公开 PR 的实现差异只用于独立验证，没有放进 Agent 工作区。

完整 `repo/` 为本地生成的 36 MB 源码目录，按现有 `.gitignore` 策略不提交。新 checkout 需从标注的公开基线重新取源，并用提交号、tree SHA 和源文件清单校验后才能运行；本次未添加自动下载器。

## 可见测试验证

在 Django Docker 镜像内，用基线源码和公开 PR 测试运行：

```text
python tests/runtests.py model_fields.test_filepathfield
```

基线按预期失败：`test_callable_path` 报 `TypeError`，`scandir` 收到函数而不是路径。随后在独立临时副本中，仅应用公开 PR 对 `django/db/models/fields/__init__.py` 的实现改动，同一命令运行 2 项测试并通过。修复内容没有写入案例仓库。

Docker 命令使用镜像内解释器 `/opt/miniconda3/envs/testbed/bin/python`。为了让 Django 根目录可导入，Docker 执行器现在会在检测到 `django/__init__.py` 时设置 `PYTHONPATH=/workspace`；对应回归测试覆盖该分支。

## 数据隔离门禁

`evals/cp2_benchmark.py` 在计划阶段核对案例元数据、公开源文件清单哈希、基线 commit/tree、完整文件路径集合及每个基线文件哈希，也核对可见测试副本与其 SHA-256。它拒绝 patch/gold/hidden 字段、额外文件、符号链接、路径穿越和基线文件漂移。

`tests/test_cp2_benchmark.py` 用合成样例覆盖干净材料、额外 `gold.patch` 哨兵、源码漂移和 oracle 元数据。`tests/test_workspace.py` 新增 `SENTINEL ONLY` 哨兵回归，目标是验证 WorkspaceManager 不带入未跟踪的 `gold.patch` 或 `hidden_tests`；本机 Git clone 在断言前失败，故该项尚未验证。

对真实 6074 个文件的基线，`_prepare_base` 成功生成 Git 基线，清单包含 6074 个已跟踪路径（6073 个公开基线文件和 1 个公开测试）。但真实大仓库的 `WorkspaceManager.prepare` 未能完成：Git for Windows 的 `sh.exe` 返回 `NtCreateDirectoryObject ... 0xC0000022`。因此本次没有声称真实大仓库的 Agent workspace clone 已验证；隔离保证由精确基线清单校验与合成 workspace 回归共同覆盖。

## 本地验证

```text
python -m pytest tests/test_cp2_benchmark.py tests/test_execute.py tests/test_workspace.py -q
```

CP-2 与执行器定向测试：42 项通过。完整定向组：45 项通过、3 项因宿主拦截 Git for Windows `sh.exe` 而失败；失败点都在 `WorkspaceManager.prepare()` 启动 clone 时，错误为 `NtCreateDirectoryObject ... 0xC0000022`。新加的未跟踪 oracle 哨兵测试也在 clone 启动处受阻，未能在此宿主验证其断言。

Docker 基线失败/公开修复通过证据来自本切片前序运行；本次没有重跑 Docker，也没有发起模型请求。案例 `repo/` 按项目现有策略留在本机并被 `.gitignore` 排除；提交包括来源清单、案例元数据、公开测试和隔离门禁，不包含 36 MB 的 Django 源码副本。

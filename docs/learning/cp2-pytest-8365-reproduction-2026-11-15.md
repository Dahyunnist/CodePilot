# CP-2 pytest #8317 公开案例复现（2026-11-15）

## 结论

新增一个独立公开开发案例 `pytest-dev__pytest-8365`。固定镜像中，精确 base 对 PR 公开回归测试 **1 failed**；应用官方 PR 后同一测试 **1 passed**。该案例来自 [pytest issue #8317](https://github.com/pytest-dev/pytest/issues/8317) 与修复它的 [pytest PR #8365](https://github.com/pytest-dev/pytest/pull/8365)。

这是已公开的开发案例，不是 blind holdout。没有运行 CodePilot Agent、模型或 hidden tests。既有冻结 manifest `benchmark-v1.json` 保持不变；案例单独列入 `supplemental-public-cases-v1.json`。

## 冻结来源与环境

| 字段 | 核验值 |
|---|---|
| 仓库许可 | MIT；base `LICENSE` SHA-256 `7898b9b164d4f93fd9a562fd0f592935518b48c4745303964110eb7f7fe64faf` |
| issue / PR | pytest #8317 / PR #8365 |
| PR base | `4964b468c83c06971eb743fbc57cc404f760c573` |
| PR head | `26d3d7743a860c0898c035961536fe36d9ff12e7` |
| 官方 merge/fix commit | `b7f2d7ca61d6169495e5780fffc252daaacd6583` |
| 镜像 | `swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-8365@sha256:ad963610bf29e6d0df24f5eab20df20ada6db050f21434f2dd329075286c4044` |
| 镜像 Git 状态 | `HEAD=a2ae9f63ad2d1d5e87b84ec52e07c38d5a210d5c`，其父提交与 PR base 完全一致 |
| 可见测试 | `testing/test_tmpdir.py::test_tmp_path_factory_handles_invalid_dir_characters` |
| base / fix 测试文件 SHA-256 | `824a8b3310d5904a7aa36d570e7080eee590c7953acf7569b5ebae655cbe5bad` / `1696de6151b0dee0f88db6d9e2df2d91f81f71fa0296505b3e1faef2eac0c3de` |
| 原始官方 PR patch SHA-256 | `275dcb5855d867cb603841b31a47a425d232601b35e55650adefb16e7ac595ec` |

镜像基于 `linux/amd64`。Issue 描述的原始环境是 Windows SSH/域账号用户名。PR 的可见测试把 `getpass.getuser()` 替换成含斜杠的 `os/<:*?;>agnostic`，在 Linux 上触发相同的目录创建 `OSError` 回退路径。这里证明公开测试的 base→fix 行为，不声称复现 Windows 主机环境。

## 复现结果

在容器里 checkout 精确 base `4964b468c83c06971eb743fbc57cc404f760c573`，应用官方 PR 测试，再从 base 恢复 `src/_pytest/tmpdir.py` 作为失败端。结果：**1 failed, 33 deselected**，失败为 `FileNotFoundError` 创建 `/tmp/pytest-of-os/<:*?;>agnostic`，退出码 **1**。

随后从相同 base 应用原始官方 patch。运行同一个可见测试，结果：**1 passed, 33 deselected**，退出码 **0**。两次均固定镜像 digest、`--network none`，容器使用 `--rm` 销毁；没有宿主仓库挂载。

原始官方 patch 可从 PR patch URL 重新下载。SHA-256 必须与 case manifest 中的 `official_patch_sha256` 一致。当前工作副本的下载位于 `evals/public_cases/cp2/reproductions/pytest_8365/official-pr-8365.patch`；该原始 patch 文件保持未跟踪，不进入本次提交。

复现命令：

```powershell
$patch = 'E:/job/codepilot-safe-validation/evals/public_cases/cp2/reproductions/pytest_8365/official-pr-8365.patch'
docker run --rm --network none --tmpfs /tmp:rw,nosuid,nodev,size=1g --mount "type=bind,source=$patch,target=/input/official.patch,readonly" --entrypoint /bin/bash sha256:ad963610bf29e6d0df24f5eab20df20ada6db050f21434f2dd329075286c4044 -lc 'set -e; cd /testbed; git checkout --detach 4964b468c83c06971eb743fbc57cc404f760c573; git am /input/official.patch; git checkout 4964b468c83c06971eb743fbc57cc404f760c573 -- src/_pytest/tmpdir.py; /opt/miniconda3/envs/testbed/bin/python -m pytest testing/test_tmpdir.py -p no:cacheprovider -k test_tmp_path_factory_handles_invalid_dir_characters -q'
```

此命令产生预期 base 失败。再在容器中执行 `git checkout HEAD -- src/_pytest/tmpdir.py`，并重复 pytest 命令，得到官方修复通过。结构化结果和原始 patch 分别保存在 `evals/public_cases/cp2/reproductions/pytest_8365/reproduction.json` 与 `official-pr-8365.patch`。

首次试跑曾显示 base 通过。复核发现该次 `git restore` 从已应用 PR 的 HEAD 恢复了源文件，实际仍是修复代码。该结果已明确作废；第二次从冻结 base SHA 恢复源文件后，得到上述失败/通过配对。

## 验证边界

只跑 PR 提供的单个公开回归测试。没有运行 Agent、真实模型、hidden tests 或完整 pytest 套件。此公开开发题不代表 CodePilot 成功率，也不能作为盲测成绩。

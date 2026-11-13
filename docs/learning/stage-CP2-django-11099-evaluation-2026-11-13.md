# CP-2 Django #11099 单题评估记录（2026-11-13）

## 任务与冻结环境

- 公开任务：`django__django-11099`，Django ticket #30257，修复用户名末尾换行被 validator 接受的问题。
- 冻结 base：`d26b2424437dabeeca94d7900b37d2df4410da0c`；声明许可证 BSD-3-Clause。
- Docker 镜像：`swebench/sweb.eval.x86_64.django_1776_django-11099:latest`，ID `sha256:cca302934edd881cc4f1e4647a389a25cdaa3c02bfa33667a4204934a09c4fb1`。
- base 根目录 `LICENSE` SHA-256：`b846415d1b514e9c1dff14a22deb906d794bc546ca6129f950a18cd091e2a669`。
- 镜像 Python：`/opt/miniconda3/envs/testbed/bin/python`，Python 3.6；Django `3.0.dev20190322115239`。镜像无 pytest；未安装依赖，未联网。

## 基线与候选修复

- 基线在冻结 base 上复现：`ASCIIUsernameValidator` 和 `UnicodeUsernameValidator` 均接受 `"username\n"`。
- 独立候选补丁：[candidate.patch](../../evals/public_cases/cp2/reproductions/django_11099/candidate.patch)，SHA-256：`092258892bea38f7959d72b7bda1e4cb48b56a0a275a77d0581389566c8d450c`。
- 修复把两个正则的 `$` 结束锚点改为 `\Z`，避免 `$` 在末尾换行前匹配。
- 可见回归测试：`tests/auth_tests/test_username_trailing_newline.py`，分别验证 ASCII 与 Unicode validator 拒绝末尾换行。

## 验证结果

- 在独立 Docker 容器内，对候选补丁运行：`/opt/miniconda3/envs/testbed/bin/python -m unittest test_username_trailing_newline -v`。
- 结果：2 项测试通过，`Ran 2 tests ... OK`。
- 本轮 CodePilot 回归另见 CP-2/CP-3 提交及终端结果；此记录只覆盖该 Django 任务的可见测试。

## 边界

- 未读取或运行官方隐藏测试、gold patch 或 PR diff；没有真实模型调用，也没有 SWE-bench 分数。
- 这是一个独立候选与可见回归测试结果，不代表官方任务通过或生产级修复能力。
- pytest 不在冻结镜像中；未安装依赖，也未运行完整 Django 测试集。

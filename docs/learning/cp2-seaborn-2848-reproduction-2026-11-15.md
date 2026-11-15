# CP-2 seaborn-2848 离线复现（2026-11-15）

## 哈希绑定与输入核验

| 项目 | 实测 | frozen case 对照 |
|---|---|---|
| case | `mwaskom__seaborn-2848`，`hue_order` 仅列部分类别时隐藏其余点/图例 | 与 [上游 PR #2848](https://github.com/mwaskom/seaborn/pull/2848) 的题意一致 |
| 镜像 | `swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-2848:latest`，`sha256:d719470351e66623e532a4f23cdedfe8fb737147fe108e4b5829aa273528389d` | image ID 和 RepoDigest 均匹配 |
| base | 镜像 `HEAD=a110ef5b2bca99904daf60a6e10e7e5bda8d98d6`；`HEAD^=94621cef29f80282436d73e8d2c0aa76dab81273` | `HEAD^` 与 case 的 `source_commit` 完全一致 |
| 许可证 | `BSD-3-Clause`，`LICENSE` SHA-256 `0874bfc01308833385b2f5ca62205525739f6a57b8688afea1b078d0f845d6d4` | 与 source sidecar 一致 |
| source sidecar 绑定 | sidecar 原始文件 SHA-256 `977c0d56fb6a707423628fcb1f5a0ba6af04149b32380f34750b8e9c18723e17` | 与 `case.source_file_manifest_sha256` 相同；sidecar 的 archive SHA 和 source commit 也与 case 相同 |
| visible test 绑定 | base 文件 SHA `786d33306a6b7fe340b27679855e89ae7f27a3a34f86e93bff6cc902305812fb`；官方 PR 测试-only patch 后 SHA `76dbfd47cba045bc87f0ed428b85cda106d63f2dd16000dbfdff1ceef4f013a1` | 后者与 `case.visible_test_sha256` 完全相同；验证此 case 的 visible hash 指向含新增测试的完整 `tests/test_relational.py`，不是 base 文件 |

因此，目标测试哈希绑定已确认。base 镜像没有 `test_hue_order`，先只应用 PR 测试文件 hunk 后运行目标；fix 容器应用完整官方 patch 后运行同一命令。没有替换或猜测测试。

## Patch 与容器

- Patch URL：<https://github.com/mwaskom/seaborn/pull/2848.patch>
- 原始 patch SHA-256：`641f3103dd3a4b1a7f07387ec6f79d185b6c00ee029a9facfd8c5a24d9fbe6b0`
- PR commit：`487dae9b7817894eddf59a155124c7e53267d1a9`
- 两次容器运行均使用固定 image ID、`--network none`、`--rm`；patch 只读挂载。宿主源仓库没有挂载，未运行 Agent、模型或 hidden gold。
- 两个容器均已退出并由 `--rm` 删除。随后 `docker ps -a --filter ancestor=<image-id>` 无输出；临时 patch 文件已删除。

测试命令：

```bash
/opt/miniconda3/envs/testbed/bin/python -m pytest tests/test_relational.py -p no:cacheprovider -k test_hue_order -q
```

| 工作树 | pytest 结果 | pytest 退出码 |
|---|---|---:|
| 冻结 base + 仅公开测试 hunk | 1 failed，72 deselected；未映射类别触发 `KeyError: 'c'`，后续 `TypeError` | 1 |
| 官方 PR 完整 patch | 1 passed，72 deselected，12 个 Matplotlib 弃用警告 | 0 |

完整 patch 在一次性工作树用 `git apply --check` 后应用；仅容器文件系统改变，容器销毁后丢弃。

## 边界

本记录证明该题的冻结 base 在公开目标测试下失败、官方 PR patch 后通过。没有运行 CodePilot Agent、模型、hidden tests 或 benchmark 全集。`benchmark-v1.json` 未修改。

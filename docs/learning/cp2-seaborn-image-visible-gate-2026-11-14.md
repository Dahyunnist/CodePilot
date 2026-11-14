# CP-2 seaborn 镜像与 visible-only 闸门（2026-11-14）

## 镜像身份

manifest 中 `mwaskom__seaborn-3010` 固定为 `sha256:22fef36e8b9655fb1642d976de669e3f2426df0186a09d6d788fc6215cfa1bc0`，与用户提供的本机镜像 digest 完全一致。当前会话 Docker Desktop pipe 不存在，`docker image inspect` 未能连接 daemon；因此本轮只确认 manifest pin 与用户报告相符，未独立读取本机镜像 ID。

## visible-only 闸门

manifest 将该题标作开发集。runner 要求所有任务具备已核验镜像 digest、已物化且基线失败的可见测试，并拒绝含私有 oracle 路径的 case。`visible_only` 路径不读取、哈希或运行隐藏 oracle。

CP-2 15 题中，xarray-4493 的镜像 digest 仍缺；15 题可见测试均未物化/基线验证。因此整组仍须 fail closed。未批量拉取镜像，未运行模型。

## 测试证据

- `tests/test_cp2_benchmark.py`、`tests/test_benchmark_manifest_integrity.py` 与 3 个 visible-only 定向测试：**9 passed**。
- 较宽 CP-2/runner 测试组：**30 passed, 1 failed**。唯一失败在 `test_budget_stopped_patch_verifies_from_clean_copy_and_frozen_tests`，Windows 沙箱复制临时 Git object 时返回 `FileNotFoundError`。宿主之前报告 283 项全通过；当前受限环境结果不覆盖该宿主证据。

未跟踪的 `django_10924/` 未读取、修改或提交。

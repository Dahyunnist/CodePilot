# CP-2 Agent 与隐藏测试隔离验证（2026-11-13）

## 已验证路径

Agent 只接收 `case_dir/repo` 的工作副本；仓库工具 `list_files` 与 `read_file` 以该目录为根并拒绝越界路径。Runner 通过 `_prepare_independent_workspace` 将基线复制到单独的 `verification_workspace`，叠加 Agent 的生产代码改动；之后 `_apply_hidden_test_patch` 从 case 私有目录读取隐藏 patch，只应用到 verifier，再由 pytest 执行隐藏测试。

## 合成回归

`tests/test_swebench_prepare.py::test_hidden_patch_stays_outside_agent_workspace_and_runs_in_verifier` 创建临时 baseline、Agent repo 和 case 私有目录。测试断言 Agent `list_files` 不发现 patch、绝对路径 `read_file` 抛出 `PathPolicyError`、verifier 可应用 patch 并通过隐藏 pytest，且 Agent 文件内容不变。

验证命令：

```powershell
D:\Anaconda3\envs\NN\python.exe -m pytest tests/test_swebench_prepare.py::test_hidden_patch_stays_outside_agent_workspace_and_runs_in_verifier -q --basetemp=.tmp\pytest-isolation
```

结果：专项用例 `1 passed`。整份 `tests/test_swebench_prepare.py` 在本机执行 `12 passed`。准备、runner、manifest、候选集及 benchmark integrity 相关套件合计 `40 passed`。后两项需为当前临时工作树的 Git 子进程设置一次性 `safe.directory`；未改全局 Git 配置。

## Windows 权限回归

宿主禁止硬链接时，安全解包器继续失败关闭，不改成普通复制，因为复制会改变仓库符号链接的共享写入语义。正向语义测试先探测宿主能力；仅在不支持时标记 skip。另有强制 `EPERM` 的负向测试，确保解包器返回明确错误、不留下成功假象。

`_write_run_manifest` 的只读 Git 子进程显式把当前 CodePilot 仓库根作为单次 `safe.directory` 参数和工作目录；不修改全局 Git 配置。Windows 临时工作树因此能生成 manifest。

```powershell
$env:GIT_CONFIG_COUNT='1'
$env:GIT_CONFIG_KEY_0='safe.directory'
$env:GIT_CONFIG_VALUE_0='E:/job/codepilot-lite/.tmp/release-safe'
D:\Anaconda3\envs\NN\python.exe -m pytest tests/test_swebench_prepare.py::test_safe_archive_fails_closed_when_hard_links_are_unavailable tests/test_live_runner.py::test_run_manifest_pins_model_agent_and_case_hashes tests/test_swebench_prepare.py::test_hidden_patch_stays_outside_agent_workspace_and_runs_in_verifier -q --basetemp=.tmp/pytest-cp2-crossplatform
D:\Anaconda3\envs\NN\python.exe -m pytest tests/test_swebench_prepare.py tests/test_live_runner.py -q --basetemp=.tmp/pytest-cp2-related
```

结果：定向 `3 passed`；两个相关测试文件 `34 passed, 1 skipped`。硬链接语义正例在当前受限宿主标记 skip；Linux 或有权限的 Windows 会执行。仍只用合成夹具；真实 SWE-bench 任务、Docker 预检和模型评测均未运行。

本轮只验证合成夹具；没有运行真实冻结题、没有调用模型、没有声称 CP-2 基准完成。Docker 真实预检仍未运行。

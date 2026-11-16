# CP-3 Windows 本地仓库克隆与 CLI E2E（2026-11-16）

目标覆盖此前被 Codex 宿主 Git/MSYS ACL 阻断的 7 个 CLI scripted-model 端到端用例：外部仓库审批写回、缺失检查点、重启后拒绝、审批后补丁变化、脏仓库拒绝、恢复后复测、差异预览截断拒绝。

在普通 Windows PowerShell、仓库根目录运行：

```powershell
python scripts/verify_cp3_cli_e2e.py
```

脚本只用 Python `TemporaryDirectory` 创建 pytest 工作根和 JUnit 文件；离开作用域后自动清理该根目录。它不接受路径参数，不对既有仓库执行 reset、clean 或删除。用例使用 scripted model，不发真实模型请求。

输出仅含每项测试名、状态、进程退出码和有限分类。完整 pytest stdout/stderr 不显示、不写文件；失败中的宿主 ACL 文字只映射为 `host_acl_blocked`。超时和 JUnit 缺失明确报告阻断，不能记作通过。该入口本身的离线单测只验证用例清单和脱敏分类；不代替普通 PowerShell 实跑，也不把 Codex 宿主 ACL 阻断算成测试通过。

## 普通 Windows 宿主实跑

2026-11-15，用户在普通 PowerShell 使用 `python` 运行同一入口：**7/7 通过，exit code 0，`model_calls=0`**。脚本创建的临时目录已自动清理。首次使用系统 Python 3.14 因未安装 pytest 返回 `blocked_no_junit`；改用项目 NN 环境后成功。此结果来自普通宿主，不覆盖 Codex 宿主的 Git/MSYS ACL 阻断。

## 2026-11-16 父会话复验

父会话在 CodePilot 发布快照根目录运行同一入口。受限进程中 Git Bash 无法创建 MSYS named object，5 项被分类为 `host_acl_blocked`、2 项通过；这不是应用断言失败。随后在主机权限进程使用项目 NN Python 重跑：**7/7 通过，exit code 0，`model_calls=0`**，临时工作区由入口自动清理。该结果不是用户手动 PowerShell 运行记录。用户最近一次粘贴的命令显示工作目录为另一个项目目录，因此不作为 CodePilot 快照验收证据；请勿与本次主机权限复验混记。

## 2026-11-16 本地仓库克隆兼容修复

用户在短随机 `basetemp` 下直接运行 7 个 CLI E2E：**2 passed、5 failed**。失败都发生在工作副本创建阶段，CLI 返回 exit 2；Git trace 显示 `git clone --no-hardlinks <local-path> <workspace>` 启动 Git for Windows `sh.exe`，并因 `NtCreateDirectoryObject(...): 0xC0000022` 退出。问题是受限 Windows 宿主的本地 Git transport，不是路径长度。

`WorkspaceManager` 现在对已解析的本地仓库使用 `git clone --local --no-hardlinks`。`--local` 走本地复制路径；`--no-hardlinks` 保证对象文件独立复制，不建立硬链接。代码保留源与目标 HEAD 比较、目标工作树清洁检查，并在克隆后复查源 HEAD；要求源干净的写回流程还会再次核对源状态。若克隆期间源 HEAD 改变，工作区会清理并拒绝继续。

回归测试验证 clone 参数、对象文件不是硬链接、没有 `objects/info/alternates`，并模拟克隆期间源 HEAD 变化。Git 官方文档指出 `--local` 会拒绝对象目录符号链接、不同所有者仓库，并提示复制期间源仓库并发写入风险；本实现通过源状态复核处理并发变化，不会在失败时退回远程 transport。见 [Git clone 文档](https://git-scm.com/docs/git-clone.html)。

项目 NN Python 3.11.15 验证：工作区测试 **8 passed**；7 个指定 CLI E2E **7 passed**；完整套件 **373 passed**。用例只用 scripted model，真实模型调用为 **0**。Codex 受限进程仍会触发 Git/MSYS ACL 错误，即使加入 `--local`；以上通过结果来自获批的主机权限进程，不能替代用户普通 PowerShell 对最终版本的复核。

## 剩余 CP-3 门槛

- 没有真实 OpenTelemetry Collector/OTLP 导出验收。
- 没有外部模型参与的 prompt injection 测试；离线 scripted-model 用例只证明本地规则行为。
- 没有企业多仓库、monorepo、子模块或并发写回验收。
- 用户普通 PowerShell 尚未复跑本修复版本的 7 个 CLI E2E；待复核后再认定该宿主缺口关闭。
- Codex 受限进程的 Git/MSYS ACL 问题仍存在；主机权限进程通过不代表受限进程可运行。

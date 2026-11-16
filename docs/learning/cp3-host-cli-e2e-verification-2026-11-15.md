# CP-3 Windows 主机 CLI E2E 验证入口（2026-11-15）

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

## 剩余 CP-3 门槛

- 没有真实 OpenTelemetry Collector/OTLP 导出验收。
- 没有外部模型参与的 prompt injection 测试；离线 scripted-model 用例只证明本地规则行为。
- 没有企业多仓库、monorepo、子模块或并发写回验收。
- Codex 受限进程的 Git/MSYS ACL 问题仍存在；主机权限进程 7/7 不代表受限进程可运行。

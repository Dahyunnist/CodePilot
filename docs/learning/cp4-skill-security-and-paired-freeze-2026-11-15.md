# CP-4 Skill 安全审计与配对协议冻结（2026-11-15）

## Skill 审计

当前只有两个内置 Skill：`pytest-failure-triage` 与 `api-contract-check`。注册表保存两个独立冻结的数据类实例；`get_skill()` 按 ID 选择，不动态导入外部 Skill。未知 ID 和非精确整数 schema 版本会拒绝。二者各自声明输入契约、工具白名单和运行预算。

Agent 在每轮模型请求前按白名单过滤工具定义；实际执行工具时再次检查白名单。测试覆盖 API Skill 不得调用 pytest Skill 独有的 `suggest_tests`：项目 `AGENTS.md` 中的越权要求仍作为不可信上下文传入；模型即使返回被禁工具调用，也收到 policy 拒绝，后续允许的测试工具仍可执行。提示注入文本的标记只能帮助模型理解信任边界，真正的拒绝由 Agent 执行层完成。

这证明离线代码路径按预期限制工具，不证明真实模型一定遵循提示，也不证明 Skill 提高修复质量。

## 配对评测协议

冻结清单：`evals/skills/cp4-paired-protocol-2026-11-15.json`。

- 两个固定案例各自比较 `skill_id=none` 与其匹配 Skill；不跨 Skill 混配。
- 配对时固定模型/端点、Agent 源码及工作区差异、题目与仓库/测试哈希、执行镜像摘要、ContextSelector、验证模式和所有预算。
- 逐案例报告严格接受状态、独立可见/隐藏测试、失败类型、估算成本和耗时。失败样本也必须保留。
- 当前清单状态为 `frozen-not-executed`，模型调用数为 0；两题 pilot 只作描述性对照，不支持总体能力结论。
- 真实模型配对仍需单独核实供应商余额和授权；本轮未调用模型或 Docker。

`frozen_inputs_sha256` 固定 Skill、Agent、提示、比较器、runner 和案例输入的原始字节。`protocol_sha256` 对删除自身摘要字段后的 JSON 做 UTF-8、排序键、无空格 canonical 序列化并计算 SHA-256。`tests/test_cp4_skill_freeze.py` 同时校验协议摘要、全部输入摘要、配对关系和未执行状态；任何受冻结文件变化都要求显式复核并重新冻结。

协议 SHA-256：`d71d343398b7c385e32402ca1c1aa648006b6eafb40d208853f00295f3d6b066`。

## 验证边界

- NN 离线测试：Skill、提示注入、协议冻结共 **21 passed**；配对比较器定向测试 **2 passed**；消融报告含 **2 个固定案例**，`model_calls=0`。
- 本轮仅运行 NN 环境离线测试；没有真实模型请求或 Docker 执行。
- Windows junction 权限跳过和 4 个 CLI 写回 E2E 的 Git/MSYS `NtCreateDirectoryObject(...): 0xC0000022` 阻塞仍按此前记录保留；本轮不重试、不宣称集成验收完成。
- `verification-artifacts/` 是未跟踪用户目录，本轮未读取、修改或暂存。

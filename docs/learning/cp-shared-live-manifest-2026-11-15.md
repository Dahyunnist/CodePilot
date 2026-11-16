# CodePilot 真实评测共享运行清单

## 为什么补这一层

原 `run_manifest.json` 记录模型、Docker 配置和冻结案例哈希，但它在运行前写入。此时还没有请求数、响应数、费用和最终状态，异常退出也会留下看似完整的旧结构。现在保留原字段，并增加 `shared_run_manifest_v1`，运行开始时标记 `running`，统一结束或异常路径再原子更新为终态。

## 字段如何取值

- `git_sha` 记录评测代码所在提交。旧清单另存工作区是否有未提交改动及其 diff SHA-256；因此提交号不单独代表运行代码完全干净。
- `dataset_sha256` 对选中案例的元数据哈希、源码树、可见测试和适用的隐藏测试哈希做规范化后计算。不写案例原文或本机路径。
- `prompt_sha` 取实际提示模板文件哈希；案例指令由数据集哈希覆盖。
- `tool_schema_sha` 来自运行时注册给模型的工具 JSON Schema。没有到达工具注册阶段时保留 `null`。
- `runtime_digest` 仅在所有 Docker 镜像都给出不可变 SHA-256 digest 时填写。可变 tag 与主机环境一律记 `null`。
- `request_attempt_count` 统计 trace 中 `model_budget_reserved` 事件，表示 Agent 进入模型调用阶段的次数，不宣称供应商确认收单。
- `response_count` 统计成功解析并写出 `model_finished` 的响应。`failed_request_count` 统计 `model_failed`。
- `cost_usd_estimate` 只汇总本次报告中可核对的 token 用量估算。若请求失败或任一费用无法核对，金额写 `null`、确定性写 `unknown`。零请求时才写精确零。
- `scorer_sha` 哈希验收函数源码。`gold_source` 明确说明评测使用案例元数据及独立可见/隐藏测试，不暗示人工标注。

`run_id` 与共享 `trace_id` 标识一次批次；每题保留独立 `run_id`，trace span 同时关联批次 `trace_id`。异常退出由外层收尾器把已落盘的 trace 汇总为 `failed`；键盘中断记录 `cancelled`。清单不写 API Key、提示原文、补丁、测试输出或完整思维链。

## 验证

```powershell
conda activate NN
Set-Location <release worktree>
python -m pytest tests/test_live_shared_manifest.py tests/test_live_runner.py::test_run_manifest_pins_model_agent_and_case_hashes tests/test_live_runner.py::test_visible_only_manifest_does_not_read_hidden_artifacts -q
```

测试以临时案例和本地 JSONL trace 覆盖成功请求、请求失败、零请求、费用未知、共享 ID 关联、Schema 字段以及异常收尾；不访问供应商、不读取私人文件。一次 `model_budget_reserved` 是 Agent 调用尝试，不等于供应商计费记录。

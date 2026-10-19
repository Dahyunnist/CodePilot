# S2：收紧检索与上下文

## 1. 问题与前后变化

S1 的真实模型闭环已通过三项任务，但读取文件没有说明依据，重复读取会重复传回全文，对话也没有独立的字符上限。S2 让 `read_file` 要求理由、同一行段重复读取返回短提示、成功补丁后清掉该文件的读取缓存，并为模型消息增加上下文字符预算。默认上限为 30,000 字符；这是请求体大小保护，不是 tokenizer 的 token 估算。

## 2. 数据流与涉及文件

`evals.live_runner` / `codepilot.cli` 将上下文上限写入 `Task.max_context_chars`。`Agent.run` 每次请求前统计序列化后的消息字符；超限时先压缩旧工具结果，保留工具调用 ID 和协议结构；基础提示仍超限时以 `budget_exceeded` 停止。`ToolRegistry` 校验 `read_file.reason` 并去重；`TraceLogger` 记录理由，不记录文件内容。`prompts.py` 指示模型先搜索、再读相关范围。

## 3. 设计取舍

用字符数限制而非估算 token，避免引入 tokenizer 依赖。压缩旧工具观察时保留角色和 `tool_call_id`，维持 Chat Completions 的工具消息配对。重复读缓存只活在一次 Agent 运行中；修改文件后使对应路径缓存失效。理由上限 240 字符，避免把新字段变成另一个长上下文入口。

## 4. 两条失败路径与传播

模型缺少 `read_file.reason` 时由 Pydantic 校验拒绝，工具结果标记 `validation`，模型可据错误修正。读取 `../outside.py` 时由仓库路径策略拒绝，结果带 `PathPolicyError`，越界文件不会进入上下文。若旧测试失败而模型仍结束，Agent 返回 `failed`，错误为 `model finished while tests were failing`。提示本身超出字符预算时，模型调用前返回 `budget_exceeded`。

## 5. 测试结果与证据

NN 环境执行 `D:\Anaconda3\envs\NN\python.exe -m pytest -q`：49 项通过。Docker 实时评测在本执行器因 Docker named pipe `permission denied` 无法启动；改用显式授权的 host 模式运行同三例，3/3 accepted，三项 patch SHA-256 与 S1 完全相同。

| 案例 | S1 Docker tokens | S2 host tokens | Patch 相同 |
| --- | ---: | ---: | --- |
| parse-config | 11,441 | 9,916 | 是 |
| parse-port | 9,747 | 10,915 | 是 |
| timeout-config | 9,883 | 10,547 | 是 |
| 合计 | 31,071 | 31,378 | — |

这组数据不能证明 token 下降：总量增加 307（约 1%），且执行模式不同。现有证据支持修复一致、测试通过和上下文有界，不支持成本改善结论。S2 结果及轨迹在 `reports/live-model-s2/`。

## 6. 10–20 分钟小实验

在 NN 环境运行：`python -m evals.live_runner --execution host --approve-host-tests --output-root reports/live-model-s2-repeat --work-root .tmp/live-model-s2-repeat`。比较新旧 `results.csv` 的 tokens 与 patch hash；也可将 `--context-budget-chars` 暂时设为 `2000`，观察轨迹中的 `context_compacted` 或预算失败。Host 测试只用于可信评测夹具。

## 7. 面试问题与回答

**问：为什么压缩工具消息而不是直接删历史？** 保留 assistant 工具调用与对应 `tool_call_id`，否则 API 消息序列可能不合法；同时留下工具结果已压缩的明确标记。

**问：字符预算等于 token 预算吗？** 不等于。它是确定性的请求上下文护栏；token 上限仍由模型回复的 usage 计数控制。

**问：如何证明 S2 更省 token？** 当前数据没有证明。三例总 token 略增，且 S1、S2 执行模式不同；需要相同模式、多次重复和同一模型设置后再判断。

## 8. 未完成边界

去重按请求路径和行范围，不合并重叠范围，也不跨 Agent 运行。字符计数不含 JSON 编码后传输开销的精确估算，也不预测模型 tokenizer。S2 的实时评测因 Docker 权限限制使用 host 模式，不能当作 Docker 对照实验。

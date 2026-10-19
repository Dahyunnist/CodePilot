# S6：面向对象工具注册与执行

## 1. 本阶段目标

此前工具参数模型、模型 schema、名称分发和执行逻辑分散在 `registry.py`。添加工具需要分别维护多处映射，容易漏项。本阶段让每个工具类拥有自己的说明、参数模型和执行方法。

## 2. 工具调用链

1. 每个具体工具继承 `Tool`，声明 `name`、`description` 和 `arguments_model`，实现 `run()`。
2. `Tool.to_spec()` 从参数模型生成 JSON Schema。
3. `ToolRegistry` 根据默认工具类型创建实例，并按工具名建立索引；也可通过 `tool_types` 注入自定义工具。
4. Agent 调用 `read_tools()`；Registry 从实例生成模型可见的工具 schema。
5. 模型返回工具名和参数后，Registry 查找实例；工具基类统一校验参数、捕获错误并规范化结果。
6. 工具类声明 `never`、`always` 或 `host_tests` 审批策略；Registry 统一执行策略。

## 3. 添加工具

新增工具时，创建一个 `Tool` 子类并提供参数模型及 `run()`。默认工具加入 `BUILTIN_TOOL_TYPES`；外部扩展可通过 `ToolRegistry(tool_types=...)` 显式注入。无需再单独编写 schema 生成与名称到执行函数的分发表。

默认工具清单仍是显式 allowlist。没有使用自动扫描子类，因为工具导入和启用应由程序入口明确控制。

## 4. 验证

回归原有 Agent、Registry、路径策略、补丁、测试执行与 CLI 流程；另测自定义 Tool 可生成 schema、按名称执行，并对无效参数返回 validation 结果。

# S7：运行时工具注册

## 1. 参考设计

Hello-Agents 第七章 7.5.1–7.5.2 展示了 `register_tool()` 对象注册、`register_function()` 函数注册和工具发现。对象方式适合有状态或多参数工具；函数方式适合已有的简单函数。

## 2. CodePilot 的实现

`ToolRegistry.register_tool()` 接收 `Tool` 实例，验证 schema 后按名称注册。Agent 下一轮调用 `read_tools()` 时即可看到新工具；执行时也从同一个映射查找实例。

`register_function()` 将单字符串输入函数包装成内部 `Tool` 子类。模型参数固定为必填 `input` 字符串，仍由 Pydantic 校验，之后再调用原函数。

## 3. 与教程实现的取舍

- 优点：可在初始化后注册，不必修改默认内置工具清单；简单函数可快速接入。
- 保留：复杂工具继续使用类型化 Pydantic 参数模型，自动生成 API JSON Schema。避免单独维护参数描述表。
- 保留：工具通过 OpenAI 兼容 API 的原生结构化工具调用，不用把工具清单拼进 prompt，也不用从自然语言中正则提取调用。
- 安全：同名注册直接报错，不静默覆盖现有工具及其审批策略。
- 边界：`register_function()` 只支持一个非空字符串参数；多参数或有状态功能应继承 `Tool`。

# CP-1 确定性上下文机制评测

新增三条冻结 task-id fixture，统计 SHA 去重前后 token、去重数、预算预留、截断量及预留本身超限标志。脚本不运行代码任务、不调用模型，token 数是 fixture 输入值，不代表模型 tokenization 或真实修复表现。

命令：`python scripts/evaluate_cp1_context_offline.py`。测试：`python -m pytest tests/test_cp1_context_offline.py -q`，3 passed。

2026-11-13 回归：重复 SHA 证据压缩会替换旧消息为哈希指针，同时保留最新消息全文，避免裁剪丢失最新调用方/测试证据。没有发现 ContextSelector 文件索引缓存，故本轮不加无关失效逻辑。命令：`python -m pytest tests/test_context_selector_offline.py -q`。

# CP-1 重复证据配对 fixture

新增 3 个确定性任务 fixture。每题含同 SHA 证据两次与跨文件引用；baseline 和 selector 使用同一 `_context_chars` 字符计数器。定向测试验证 selector 去重后计数下降、跨文件证据保留，并计算 n=3 的中位数。该字符计数仅作机制比较，不等同模型 tokenizer，也不代表真实修复率。

验证：`python -m pytest tests/test_context_selector_offline.py -q --basetemp=.tmp\\pytest-cp1`，2 passed。无模型调用。

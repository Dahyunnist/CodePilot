# S21 评测证据

- `5e6e61292044-urllib3-3653-narrow-530cb70a.jsonl`：8k 上下文初试，4 轮只读后熔断，无补丁。
- `63d766fda543-urllib3-3653-narrow-d385ac9b.jsonl`：10k 上下文实修，9 步成功；含模型补丁和测试流程的事件记录。
- `agent-and-independent-tests.txt`：修改前定向失败，以及 Agent、独立可见和隐藏测试结果。

轨迹只含工具事件、相对仓库路径、Token 用量和耗时，不含 API 凭证或用户私有数据。

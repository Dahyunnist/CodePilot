# 项目约定

- `billing/request.py` 负责校验外部请求与规范化输入。
- `billing/pricing.py` 负责金额计算；金额运算使用 `Decimal`，不得先转成二进制浮点数。
- `billing/invoice.py` 负责把请求契约连接到定价结果。
- 对外 `discount_percent` 按 0 到 100 的百分数解释；保持发票响应字段兼容。
- 修改跨模块契约时，运行整个 `tests` 目录并检查非法边界值。

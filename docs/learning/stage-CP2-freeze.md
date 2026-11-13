# CP-2 阶段记录：公开修复题集冻结

## 本次完成

固定 SWE-bench Lite 文件 revision 与源 SHA，独立核对 20 个任务后，在 ignored `.tmp/` 建立只含模型题面的本地冻结文件。此次只完成数据身份与封存，不代表真实仓库可复现或 Agent 修复能力通过。

## 数据流

```text
固定 Hugging Face revision
  -> Parquet 源文件 SHA 校验
  -> frozen-selection + candidate 清单核对
  -> 逐题校验 ID / 仓库 / base commit / 题面与补丁哈希 / 许可证
  -> 丢弃 patch、test_patch、eval_script 等字段
  -> ignored .tmp/freeze.json 独占写入
  -> verify 源 SHA、子集 SHA、20 个唯一 ID 与字段白名单
```

Gold patch 和隐藏测试 patch 只在本地内存中计算 SHA；冻结 JSON 不保存它们。模型任务输入只可从题面字段另行构造，不能把验证材料送给 Agent。

## 关键实现与设计取舍

- `scripts/fetch_cp2_dataset.py`：固定 revision、官方源 SHA、允许的仓库许可证映射；校验清单和数据行；过滤冻结字段；独占创建与复核。
- `tests/test_cp2_dataset_fetch.py`：用 20 条合成行验证有效冻结及仓库、base commit、题面、gold、隐藏测试、许可、重复 ID、空 patch 的拒绝路径。
- 全量 Parquet 和 `freeze.json` 位于 ignored `.tmp/`。不提交数据和具体题面，避免隐藏评测材料进入仓库或模型工作区。
- 许可证 allowlist 与两份项目清单一致性检查，不等于已逐个检出固定 base commit 并审计许可证文件。

## 失败路径

1. 源 SHA 不匹配时停止；不会读取/封存另一版本数据。
2. 任务行缺失、重复、字段哈希或许可证不符时，在 `freeze_manifest` 前失败，不能生成部分冻结文件。
3. 已有 freeze 文件时独占创建失败；不可静默覆盖原冻结。
4. 冻结文件出现 patch、test patch、eval script 等字段时 verify 失败。

## 复现与结果

源文件：`E:\job\codepilot-lite\.tmp\release-safe\.tmp\cp2-swebench-lite-v1\test.parquet`

源 revision：`b0dde1093fe417d83b7184254edf8199c1f0dff5`

源 SHA-256：`438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3`

冻结题数：20；subset SHA-256：`8fb7c6b9a93a3eaef1d0c55839e8d5420ad222447cac7b247735faf23927941d`。

定向测试：`D:\Anaconda3\envs\NN\python.exe -m pytest tests/test_cp2_dataset_fetch.py -q --basetemp=.tmp/pytest-cp2-integrity`，15 passed。真实 `freeze` 与 `verify` 命令使用 `D:\Anaconda3\python.exe`，均完成；`git check-ignore` 确认冻结文件被忽略。

## 亲手实验

在临时副本中改一个测试 fixture 的 `base_commit`，运行对应 tampering 测试。预期：冻结前报错且目标目录没有 `freeze.json`。不要改本机真实 freeze、不要打印题面或补丁。

## 面试追问

**为什么要同时保存源文件 SHA 与子集 SHA？**

源 SHA 锁定上游文件的精确字节；子集 SHA 锁定本项目选择和规范化后的题目内容。两者用途不同，不能互相替代。

**为什么冻结文件排除 gold patch 和隐藏测试？**

这些是验收真值。若进入 Agent 输入或可写工作区，评测会泄漏答案。评测器应通过隔离通道应用隐藏测试，并只向 Agent 返回可见结果。

**冻结完成是否代表 benchmark 可运行？**

不是。还需固定每个仓库 base commit、验证许可证文件、准备隔离环境、确认 baseline 测试、运行 Agent 并执行独立隐藏测试。

## 尚未完成

未检出 20 个仓库；未验证 20 个 base commit 的许可证文件和环境构建；未运行可见/隐藏测试、模型评测或 paired baseline。以上不得写成已通过指标。

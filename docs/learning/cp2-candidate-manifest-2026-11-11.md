# CP-2 候选清单离线学习记录

建立候选登记和冻结门槛分离的流程。Pending 条目允许复现字段为空；Frozen 必须具备许可证、base/fix SHA、测试命令和通过记录。外部链接或父会话核验不等于本仓库完成复现。下一步在项目 NN 环境中运行定向 pytest，再逐项验证 base/fix 与 Docker harness。当前候选不纳入评分、不调用模型。

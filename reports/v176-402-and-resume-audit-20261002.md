# v176 余额中断、内容留存及恢复审计

2026-10-02，冻结bcef98cd，contract758f9159，生产进程已终止（exit1）。第8案例的Signal retrieval调用返回HTTP402 Insufficient Balance；7个完成案例均finalized、0技术排除、0技术FN，Fast/Slow指针0/0。86外部attempts中85completed/1failed，没有把支付失败转成negative研究结论或技术FN。已询问用户充值/指定其他可用模型；未重试付费、改原冻结代码、变标签或删失败。

[产物审计](v176-artifact-audit-20261002.json)：86请求canonical hash与contract绑定、85成功response hash均一致；70预测时点请求未发现current-case ground_truth/realized/outcome字段。7个canonical case checkpoint恢复通过，144完整Basic Info卡片保留，状态增量及最终state在既定identity projection后匹配，已存prediction/final_context与trajectory一致。程序剔除无足够literal/日期引用的模型陈述没有裁掉原Basic Info；首两例人工内容抽查与完整source/PIT验证保持边界。此审计不声称hash证明任意叙述语义真，也不称7个非暴涨案例的3个普通FP是代码缺陷；没有完整固定24案F1。

[实际生产恢复重放](v176-offline-resume-20261002.json)：在隔离副本使用相同冻结代码、配置、contract、角色、DualLoop和validators，模型/数据外部调用均禁用，socket connect再作禁网保险。真实入口复用2个Plan proposal、7份完整trajectory；第8案例Initialize及其局部修复复用2份付费cache，恰好停在原402同一个request_hash a55eb993...。7份checkpoint副本及ledger不变，原workspace指针/contract/ledger不改，0新增外部调用。这证明余额恢复后可以从该前沿接续，无需重跑已完成7案；它不是新增完成案例或新Slow成功。

85成功调用按provider usage合计$0.30134076；失败402的ledger保守reservation accounting为$0.00886984，没有provider usage，不声称该值是供应商实际扣费。完整Fast零技术排除、F1>=.6、Slow双轴新Mining/technical publication/后继消费及独立幅度贡献仍未验收；整体目标保持active，当前真实外部阻碍为供应商余额。

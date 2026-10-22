# 真实财务结果的消费者验收

本轮验证单个已完成测量的 F7→F8→F9 消费连接。正式阶段已完成原生执行并在预测持久化后、truth/评分/Posthoc 前停止；F7/F8 的本案窄连接得到验证，但 Predictor 原答有分类语义错误，完整单案语义验收 **0/1**，不能关闭 F9 或 MVP。所有生产模型回答来自两个 fresh、无历史上下文的独立 subagent，外部 API/资料 GET/标签读取均0。

先由独立来源审查者把旧私有 maturity oracle 的每个义务映射到实际定义，确认额外主体索引、未选 facility 和库存警告不是 presence 定义的普遍义务。旧冻结 strict **0/1** 和原件不改，也没有把该私有结果导入消费者。新消费者的[预先冻结 oracle](../runs/diagnostics/financial_context_consumer_20261023_v1/reference/consumer-oracle.json)另按 owning spec 定义，允许合法保持原状态，不规定信念变化、预测方向或引用文风；[bootstrap 补充审查](../runs/diagnostics/financial_context_consumer_20261023_v1/reference/bootstrap-binding-addendum.json)绑定完整8字段和17条 projection/lineage。

输入是已接受的 GPRE/2025-05-30 H_init、reviewed1780 来源 view、v12 精确版本目录，以及原九项财务批次中严格通过的 `liquidity_runway_months:v3`。只声明消费这一项完成结果，使用原合法 context-only 意图；不重跑旧路由、Signal apply 或初始化。原九项仍6严格通过/1literal失败/2期间政策unknown，旧路由组合0/1不改。真实 core 重建 bootstrap 与父产物全结构相同，核验两原文 operand/PIT、resolution、fingerprints 和 Registry 后才导入。

| 本案连接 | 实际证据与结论 |
|---|---|
| F7 | Reflect 首答原生接受，保留五个 exact needs；context 不认领回答，need_dispositions.items 为空。添加两条实际证据引用，保留未来资金/稀释未知。 |
| F8 | 实际最终 context 保留5.374720662778656 months、公式、Q1期间、cash 98,610,000 USD / operating CF -55,041,000 USD、精确v3与证据。stop_reason=finalized，同时明确 trigger=max_signal_rounds；终止不表示问题已答。 |
| F9 结构与边界 | 另一独立作者首答原生接受；实际匿名 wire 与 sink 连接、预测保存早于truth。未读取标签，无概率/方向答案 oracle，不报告预测效果。 |
| F9 语义 | 原答说“positive categorical state denotes a positive months measurement”。实际 v3 的 positive 是 runway≤6个月，negative≥12个月，不能按数值正号解释。保留原答和失败。 |

实际请求已有 numeric_sign/categorical_state 独立字段和区分指令，却没有该版本阈值条件。模型仍把二者混同；缺少映射不豁免它违反既有区分义务。此前离线测试只证明字段和提示存在，不能证明 fresh 解释正确。后续修复针对一般分类含义的生产与传递，未知时保持不推断；不用新词面提示、换预测方向或追加同案调用掩盖错误。详见[分类语义诊断](../runs/diagnostics/financial_context_consumer_20261023_v1/classification-semantics-diagnosis.md)及[独立终审](../runs/diagnostics/financial_context_consumer_20261023_v1/independent-final-review.json)。

预算保持256,000 case / 131,072 request / 5 LLM calls。旧 H_init 61,888 + 路由49,144 = 111,032继续计入；终止 Reflect 预算81,578、实际逻辑预留57,862，Predictor预算87,106、预留66,957，合计 **235,851 / 4 calls**，其中物理新增2原答、0纠错、0新Signal计算。逻辑预留不是host模型实耗，host tokens/费用未知。正式冻结1,856来源与106代码绑定，输入预演在request-ready、cache/receive/inbox前止，0交接。

四项临时控制覆盖完整core到sink、bootstrap错配、literal错配、网络/终态拒绝，另64项关联测试通过。独立[cache-only重建](../runs/diagnostics/financial_context_consumer_20261023_v1/cache-reconstruction.json)在临时副本核对25文件字节同、复用2原receipts、0新交接；不重入完成阶段，不证明OS中断或业务恢复。首重建验证器因macOS /var与/private/var别名在native前失败，原日志/旧验证器保留；修复路径规范化后完成，不是产品或模型重试。

本轮未启动完整后继，也未修改已发布版本、评分、研究定义或完成指针。下一目标是精确分类条件的消费者保真与新鲜变体验收；来源完整性、整体F4–F9、Slow Mining/准入/后继使用、完整恢复和MVP仍未关闭。

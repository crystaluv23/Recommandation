# LLM Signal 有界资料阅读方案（待用户决策）

本文件是具体实施提案，尚未改变生效 spec、代码、预算、Registry 或完成阶段。
目标仍是原 Fast/Slow 工程 MVP；没有缩小 F5 的“遗漏可见且可继续读取”标准。

## 为什么单改排序不足

[固定候选诊断](../runs/diagnostics/bounded_llm_source_selection_20261021_v1/driver/summary.json)
证明 whole-word/distinct/cap3 排序能救回本案 Q1，两条完整事实进入32k投影；
但固定11文档反例仍将真正最新测量依据排到第11。独立
[比较、币种、冲突反例](../runs/diagnostics/bounded_llm_source_selection_20261021_v1/independent/interface-review.json)
也显示：即使原 source/period 合同满足，较旧必要依据仍可能被新但无关的同词文档挤掉。
因此不把这个词汇策略作为语义保真修复，不继续调权重到通过。

[现行架构](../spec/architecture.md) 已规定 catalog→fetch→provenance 三层披露，
但 LLM Signal 目前只有已选资料的投影和同源窗口纠错。Reflect 的读取通道并未接到这里。
Executor 在调用 runner 前就用原10份资料算 fingerprint，并在返回后只用原资料验证证据。
所以仅给模型增加目录，会产生无法引用的新资料和不完整的恢复/跳过判断。

## 建议采用的具体行为

1. 仅让明确支持该接口的生产 `StructuredLLMSignalRunner` 使用按需阅读；
   确定性函数继续现有 callable-owned 选文。旧冻结运行、已发布版本和未知自定义 runner
   保持各自原合同。历史 numeric-LLM v1 不迁回现行数值政策；现行 v12 数值路径独立验收。
2. Executor 从既有 resolver 的公司/PIT/来源/lookback/去重结果冻结完整合格目录，
   每页最多20张卡，显示总数、遗漏和可寻址引用。引用绑定完整来源版本，不是文件路径。
   小输入完整可见时仍走现有单次直达路径；发生选文或正文遗漏时先给目录，再读资料。
3. 新阅读模式按单个 Signal 会话隔离，每会话最多 **2 次读取交换**，目录翻页与正文读取共用该额度；
   每次正文请求最多5份，累计正文来源最多10份，累计模型可见来源正文最多32,000字符。
   原文超预算时保留完整事实/句子、raw offsets、遗漏和后续可读引用；不得把摘要当全文。
   现有数据披露函数及 typed 财务 reader 可复用，不能把原始 provider response 伪装成历史原件。
4. 读取阶段之后返回现有按 `signal_ref` 分组的结果，最多再用现有一次语义纠错。
   最坏是每个 Signal 会话 **3 次初始/阅读/最终请求加1次纠错，共4次角色请求**；不增加其他 selector 或
   distillation 模型角色。每次仍遵守实际剩余 token 预算和已配置单请求上限；预算不足准确结束。
   所有生产 LLM 请求继续用 fresh 独立 subagent、exact inbox/outbox，外部 LLM API 为0。
   原完整小输入仍可按既有规则双 Signal 共享一次调用；需要按需读的两个 Signal 分开冻结会话，
   各自保持原每 Signal 最多10份来源的能力，最坏合计8次请求，并受整个 case 剩余预算约束。
5. 原 `SignalResult` schema 不变。runtime 用实际读取的原件构造最终 resolution、
   证据资格与 document fingerprint；资料未读不得伪记为已读。另保存本次目录签名和阅读轨迹。
   早期 no-op 必须同时证明目录签名与已读原件依赖未变；旧记录缺签名时不能借旧10份 fingerprint
   跳过新通道。未选候选发生变化也必须重新评估选读，不能沿用旧缓存结论。
6. 每次请求、动作、工具结果和接受/拒绝均进入原生 journal/cache 与预算；恢复只消费已完成
   的精确请求。最终结果开始接受后不再开放新读权限，纠错只处理原已读资料；有效 sibling 不重答。
   非法引用、错公司/时间/hash、重复读取、越预算等保持技术失败或准确不足，不制造测量结论。

## 实施与验收顺序

用户确认后，先更新 owning specs，再按 eligible-session → executor消费/依赖 → runner阅读 →
持久化/恢复 的顺序实现。先通过固定反例与真实来源的 input-only 检查，再冻结一次有界 fresh
subagent 正控；不得重入此前完成的 source、F7、S5 或旧 v182 阶段。

必过样本包括：已知最新资料在旧10份外；旧但必要比较期；不同币种及同期间冲突；新无关正文；
长文及分页/预算耗尽；错公司/PIT/hash；未知 runner 兼容；读取变化导致 fingerprint/no-op 变化；
中断后恢复不重复请求；已接受 sibling 保真。实际请求、原答、纠错、落盘和消费者输入都须检查。
词汇改善、hash 和测试成功本身不关闭 F5；最终仍须证明真实语义与下游消费。

## 为什么需要一次设计决策

[AGENTS.md](../AGENTS.md) 要求对“研究定义、canonical schema、评分、PIT、准入政策、
接口的实质取舍”准备具体方案并取得所需决策。这里虽然保留 `SignalResult`，仍改变了 LLM
资料读取接口、原10份静态输入的消费方式，以及最坏请求数（原最多2次，提议最多4次）。
因此先确认这组接口与资源边界，再实施。它不是外部 API 许可申请，也不恢复任何旧实验。

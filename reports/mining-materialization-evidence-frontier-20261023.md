# Mining 能力材料与 S4→S5 原始证据交接

2026-10-23。本轮依据工程 MVP S3–S8 正控要求，先审查批准的 local Discovery
材料、现有定义和真实实现入口；没有派发新生产作者、改写旧预算终态或启动完整后继。
上一轮预算连接修复是实质进展；本轮发现并修复更下游的完整证据丢失，而非继续做
更容易的 endpoint 控制。外部API/GET、新业务标签、check/LockedTest、发布均为0。

## 原材料给出的可行边界

[独立材料审查](../runs/diagnostics/mining_capability_frontier_20261023_v1/independent/material-review.md)
在结论前冻结263份 dev8 原件/content hash、原始 opaque 组别/时点及 exact stable18。
没有反序列化新的真实结果标签；旧 source/hash 复核同。结论是材料可能性，不是候选。

- 12个确定性函数都已被 stable Signal 覆盖，改名/改阈值不能证明新能力。不同的
  `lookback_observations` 确实改变价格动量的 operands；7/8案有材料，case-005缺失。
  1097个 raw价格与metadata同，但调整口径未知，case-006有100天断档，只能称
  “供应观测间隔”，不能称固定交易天数、三个月或含股息总回报。
- source1507/case-005 有明确、带日期的管理层 ICFR 重大缺陷及未修复结论；
  source1500/case-006 有明确相反结论，source1501有“可能发生”的假设反例，
  source1768保留对象/术语歧义。这是区别于六个 stable narrative skill 的干净材料族，
  不证明股价方向或 magnitude 效应，也不把 disclosure-controls 等同于 ICFR。
- case-007/doc1010 的 InventoryNet 和 AssetsCurrent 同 us-gaap/USD/2024-09-30
  instant，材料支持新组合，但无现有注册函数实施该公式。不能借现金比率函数或
  LLM 改写绕过 S5。未添加新公式或默改测量定义。

原件记录的 PIT 合格不单独证明历史正文真实性。Company Facts 保留 retrospective
extraction/primary-filing-audit 限制；下一次正控仍须核原件版本/时间和适用定义。

## 实际断点与修复

[实现前独立反例](../runs/diagnostics/mining_capability_frontier_20261023_v1/handoff-review/before-controls.json)
冻结后复现五种同族丢失：

1. 真实1179的 `EntityCommonStockSharesOutstanding` 整行692字符被截为600，末尾
   tag/taxonomy/unit/value 的原始 JSON 被裁掉。单独字段仍重复提供 concept/unit/value，
   但 namespace 未交接，所谓 exact literal 已非法；不能直接推断新模型必然算错。
2. 13条真实事实引用只交接12条，且无遗漏说明。
3. 已执行的 document-tail read 可被合法引用，engine只收 facts/events，S5无正文。
4. event-tail 已读内容被最初 discovery preview 代替。
5. 合法 relation-only 引用的关系及 operands 没有进入实现输入。另发现按 doc ID
   猜来源类型会把1179的 accession 当 source_type。

现由生产 Controller 的 `materialization_evidence()` 单向导出该 seed 的完整来源单元：
事实保 whole row/taxonomy/period/unit/value/hash 和实际 source_type；关系保顺序 operands；
document/event 只交接真正执行的 readable windows、target/ref/case/hash/offset/时钟。
不同 target/case 即使 raw range 相同也保留独立绑定；相同执行范围重复读取去重，不声称
逐次执行 ledger ID。原始 ledger仍append-only。未读文档、隐藏 markup、私有未披露
metadata不被当作已读正文；已有标题仍是标题。event discovery preview 不冒充 raw read。

Engine只取提出候选的原 seed，不混用另一个 seed 的读窗；spec/skill/tests共用完整
引用展开，无600/12裁剪。缺失引用/过期关系依赖在模型请求前记为实现前提失败。
source-family gate使用实际 cited/dependency单元，native reversible egress继续屏蔽身份。
这些是运行时交接，不改 canonical 业务schema、原文、fact refs或旧完成阶段。

## 验证与限制

- [独立修复后9/9](../runs/diagnostics/mining_capability_frontier_20261023_v1/handoff-review/after-v2/results.json)：真实692字事实/namespace/实际类型进入 native spec/tests，后段读窗进入 native spec/skill/tests；5个诊断待答inbox，0原答/receipt/生产模型/网络。它们不是旧stage重入。
- [最终初始声明9/9复验](../runs/diagnostics/mining_capability_frontier_20261023_v1/handoff-review/after-v3/prompt-source-contract-audit.json)：三模块明确声明readable windows/ordered operands及raw-source/view hash区别，5份payload与前版同，仅增加来源字段指引；没有新回答。补充审计曾错期望尾随空格，已按原记录slice纠正，未改产品或输入。
- [402最终关联测试](../runs/diagnostics/mining_capability_frontier_20261023_v1/associated-tests-final.log)通过，网络tripwire0，126 tested bindings前后同；另经真实 engine路径验证两seed同doc不同窗口不串用。
- [最终 pre-push lint](../runs/diagnostics/mining_capability_frontier_20261023_v1/pre-push-final.log)通过，已亲读 `.lint-feedback/pre-push-last.log`；该检查只证明代码和管理记录一致。
- EOF请求长度与实际字数、原始/可读投影、跨case/target、再次fetch、完整relation operands、未知引用前置拒绝均核过。原失败反例未覆盖或改写。
- 首次174测试中旧 sibling-reuse fixture 没有任何引用来源，现补同一原有合成 revenue source，保原重用目标；新单测另误用了不存在的 `ratio` 名称、把已披露标题当成未读正文，两处fixture错保日志后纠正。产品未因此放宽。

审查首版把 H1/controller 的 cap 推定给 S5，是审查范围错误，原记录保留。S5不默继承
H1上限；未配置的S5输入cap仍未知。若 caller 明确给定原生请求cap，超限现在作为
`MiningRequestBudgetExhausted` 控制流向上传播，单次停止/0inbox，不转模型纠错或
无模式结论。整单元增长须在下一正控冻结完整输入/纠错预算前检查，不靠裁剪过关。

本轮没有新候选/忠实实现/准入/后继使用结果，原模块0/2、旧taxonomy1/2及所有其他
分母不改。局部交接修复不关闭整体S4/S5/MVP。下一步优先用 ICFR 的实际/相反/
假设/歧义材料核历史版本、定义及真实完整路径成本，再冻结方向/magnitude能力正控；
不得用这个材料审查、已有手写Signal或纯输入检查替代 fresh Mining→实现→准入→复用。

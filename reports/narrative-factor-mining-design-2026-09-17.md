# 叙事/非结构化因子挖掘设计修改方案 v1（2026-09-17）

> 目标：让挖掘 Agent 的提案分布不坍缩到单一模态——结构化因子与叙事
> （非结构化）因子在发现、验证、执行三段享有对称的机会。
> 本方案是设计文档，未实施；实施分阶段见 §6。
> 用户决策语境：经 V98 入库达成后的设计讨论（见 prompt 审计报告同日各节）。

## 0. 目标与非目标

**目标**
1. 叙事因子（例："近 90 天新闻中是否存在 ≥$50M 的订单确认"）成为提案
   分布的常态组成部分，而非偶发；
2. 模态不坍缩是**机制保证的结果**，不是某次提示词的运气；
3. 一切机制可泛化：新语料、新主题、新证据族接入时**零代码特判**。

**非目标**
- 不放开状态机执行权（动作封闭、运行时执行工具、账本/预算不变——
  这是 PIT/掩码/重放/反捏造四类不变量的载体）；
- 不放宽任何验证门（两道方向底线、fixture、配对门原样）；
- 不用硬性配额强制多样性（配额制造假探索，见 §3.4）。

## 1. 根因与设计原则

### 1.1 根因（实证）

提案分布由"决策时刻可见的对比表面"决定，与 Agent 自由度无关：

- V98 视图实测：121 个概念有正/反例覆盖矩阵（概念名+覆盖数），
  120 个叙事事件只有一个裸计数和不透明引用——决策信息 100% 偏向结构化；
- r2 影子在同一状态机内提出过叙事因子（事件引用看似可用时）；
  legacy H1/E1/E2（更松的多轮角色）同样滑向结构化（V75：E1 观察槽
  被 XBRL 记录对占满）。**约束松紧不是变量，信息界面对称性才是。**

### 1.2 五条设计原则（泛化性的载体）

- **P1 对称性**：给结构化证据的每个表面（索引、聚合、对比、引用
  校验、物化示例、执行路径），叙事证据必须有同构对应物，反之亦然。
  坍缩 = 表面不对称；对称是机制级防坍缩。
- **P2 数据驱动**：词表、目录、指标一律由语料或冻结契约**派生**，
  代码中不出现任何主题名/行业名/族名特判。新语料接入 = 重派生，不是改代码。
- **P3 状态机不变**：新能力全部以"封闭动作 + 运行时确定性执行"的
  形式加入；模型仍只决策，不执行。
- **P4 偏差可观察**：模态足迹进账本 → 反思消费 → 跨周期自纠。
  观察代替强制。
- **P5 预算分维**：发现类操作与验证类操作不共享预算（复刻 v2.1 方案
  双维度预算的同一教训：混用必致发现被验证挤死）。

## 2. 信息界面改造（四件套）

### 2.1 Case Briefs（用户提案 1 落地）

每个 dev case 在开局视图获得约 150 词的**脱敏业务简介**：

```json
"case_briefs": {
  "case-007": "Clinical-stage biopharmaceutical company developing
   targeted oncology therapies; pre-revenue, Phase 3 pivotal trial
   ongoing; funded through 2027 via prior placements; NASDAQ-listed."
}
```

- **来源**：复用 legacy 的 PIT profile 机器（`_point_in_time_profile_fields`
  /`_usable_business_description`，至今仍在），从该公司 `available_at ≤
  prediction_time` 的文档确定性抽取行业/主营/阶段/流动性画像；
- **掩码**：经 `_mask_identity_values`（现有 alias 库），公司名/代码/
  品牌不出现；行业用受控词表（SIC 一级）防指纹反查；
- **无数值结论**：简介只给定性画像，不给"增长 25%"这类可当因子用的
  数字——因子必须走证据链；
- **成本**：32 × 150 词 ≈ 6K tokens，进开局视图。

**泛化性**：简介生成规则与行业词表入 spec；任何新公司自动获得同构简介，
无逐司特判。

### 2.2 统一文档索引与浏览（用户提案 2 落地，泛化为任意族）

把"工具形接口"（fetch → 不透明引用）升级为"文档形接口"：fetch 之后，
模型获得一份**可下钻的目录**，浏览是新的封闭动作：

```text
动作 browse_sources(case_ref)
  → [{family: "news",      documents: 4, windows: {"2025H1": 2, "2024H2": 2}},
     {family: "filing",    documents: 9, windows: {"2025Q1": 3, ...}},
     {family: "financials", documents: 2, windows: {...}}]
     （目录树由 available_source_families × 实际 fetch 结果生成，
       空类目不展示——空架子诱导假探索）

动作 browse_documents(case_ref, family, window, max_items=8)
  → [{doc_ref, title, date, summary}]
     title/summary 由确定性规则生成（见下），经掩码

动作 read_document(doc_ref, offset)   ← 既有 read_span 的文档版，重动作
```

**title/summary 的确定性生成规则（P2，非逐族硬编码）**：
- title = 文档元数据派生：filing → `"<form> <period> <accession尾号>"`；
  news/transcript → 原标题（掩码后）；financial facts →
  `"<taxonomy> facts <latest period>"`；
- summary = 可见文本（复用 `_h3_document_visible_text`）首句/首 N 词
  （≤60 词），金额/日期保留，身份掩码；
- PIT：windows 只含 `available_at ≤ prediction_time` 的分桶。

**成本模型（三级漏斗）**：目录（每 case ~50 tokens）→ 摘要列表
（每篇 ~80 tokens）→ 全文（重动作）。浏览类动作消耗 browse 预算
（§4），不与 heavy 竞争。

**泛化性**：层级结构（族 → 时间窗 → 标题+摘要 → 全文）对任何族统一；
新数据源（如未来接入 analyst_recommend）自动出现在目录里，无需改
浏览代码——只要它能被现有族分类器归类。

### 2.3 属性抽取层（"主题层"的泛化形式）

Fact 是"结构化文档的确定性投影"；对称地，引入**AttributeProjection**：
叙事文档的确定性投影，产出属性事件：

```json
{
  "attribute_ref": "attr-<hash>",
  "kind": "theme",                       // 可扩展 kind 注册表
  "name": "order_confirmation_disclosed",
  "attributes": {"amount_usd": 120000000, "event_date": "2025-02-11"},
  "exact_span": "announced a definitive purchase agreement valued at
                 approximately $120 million",
  "doc_ref": "document-...", "content_hash": "...", "available_at": "..."
}
```

- **抽取是确定性代码**（模式：披露动词 × 商务宾语 × 金额/日期共现，
  span 逐字、PIT 判定，与 Fact 同一纪律）；
- **词表不在代码里**：冻结时跑一次**零调用语料派生 pass**——统计全部
  叙事文档的高频"动词×宾语×金额"模式，取满足最小支持度的 top-K
  （K 由契约冻结，初值 24），连同派生规则哈希入 run contract。
  换语料 = 重派生；扩主题 = 调 K 或调派生参数（spec 变更），非改代码；
- **接入点三处对称化（P1）**：
  1. `evidence_digest` 增 `attribute_case_coverage`——与概念矩阵并排，
     同一排序、同一字段（`{name: {positive_cases, control_cases}}`）；
  2. `compare_groups` 统一接受 `targets: [{type: concept|attribute, name}]`
     ——runtime 对两类目标计算同构的组间对比（可用 case 数 + 例证 +
     属性值的组分布）；
  3. 证据校验对称：测量文本点名的属性名必须由同名的 attribute_ref
     引用满足（与现有概念规则同一条逻辑，类别外延）。

**泛化性**：kind 是注册表（theme 先行；未来 sentiment_shift /
management_tone / entity_mention 各自成 kind），投影器接口统一
`(documents) -> [AttributeEvent]`；每个新 kind 是一次 spec 变更 +
一个投影器，核心代码零修改。

### 2.4 物化与执行的双形态对称（P1 收尾）

- 物化提示词的示例成对出现：财务 JSON 摘录 → 比率型 spec；新闻 span
  摘录 → 布尔/窗口型 spec（"窗口内存在 ≥ 阈值的 order_confirmation_
  disclosed 属性事件则 positive，逐字引用"）；
- fixture 示例同样成对：合成新闻稿文档（含"证据未披露 → unavailable"
  的 PIT 边界 case，已由 631854b 修复支持）；
- LLM 技能执行链路不变——V98 已证明其端到端可用。

## 3. 反坍缩机制（跨周期，无配额）

### 3.1 双矩阵并排 + 未探索模态披露

digest 永远同时呈现概念矩阵与属性矩阵；视图尾部一行机器生成的
事实陈述（非指令）：

```json
"modality_footprint": {
  "structured_families_fetched": 5, "narrative_families_fetched": 0,
  "concept_proposals_so_far": 2, "attribute_proposals_so_far": 0,
  "note": "narrative families remain unfetched this seed"
}
```

### 3.2 manifest 的族覆盖（防 check 侧理性避险）

`measurable_evidence_manifest` 增 per-family **dev 覆盖统计**
（`news: 23/32 cases`），模型在提案前能看到叙事族的执行可达性——
不加码 check 信息（check 原始证据仍不入生成上下文，§5.2 边界不变）。

### 3.3 模态足迹进反思闭环（P4）

mining ledger 的终局记录携带本 seed 的模态足迹；它作为 feedback unit
进入下周期 reflection——"cycle N 两 seed 均未探索叙事族"成为可被
反思泛化的教训，指导下周期的 fetch 策略。自纠靠学习，不靠强制。

### 3.4 为什么不用配额

配额（"每 seed 必须探索 ≥1 叙事族"）会触发：假 fetch（刷足迹）、
在无叙事数据的语料上浪费预算、以及语义上最危险的——为过配额而
包装成叙事的结构化提案。披露 + 反思让偏差成本由下一周期真实承担。

## 4. 预算设计（回答"浏览深度怎么定"）

三维预算，各司其职（P5）：

| 维度 | 初值 | 覆盖动作 | 理由 |
|---|---|---|---|
| heavy | 12 | fetch / read_document / compute / compare / propose | 验证与成型 |
| light | 4 | inspect_manifest / inspect_catalog | 枚举 |
| **browse（新增）** | **24** | browse_sources / browse_documents | 发现 |

- browse 每步字节上限（目录 2KB / 摘要列表 6KB），总量入账本；
- 24 ≈ 8 家 × (1 目录 + 2 摘要页)，允许"正例 4 家 + 对照 2 家"式的
  抽样式阅读后仍有余量回到聚合工具；
- 数值冻结进契约前，用影子轮校准（§6 Phase U1 验收项）。

## 5. 不变量与风险边界

**全部保留**：PIT（窗口/属性事件的 available_at 判定）、身份掩码
（title/summary/简介全过 alias 机器）、账本 append-only 与可重放
（浏览也是账本条目）、证据逐字回溯、两道方向底线与配对门、
check/holdout 隔离（manifest 只加 dev 统计）。

**风险与对策**：
- **伪特征（被报道度 ≠ 语义）**：属性矩阵必须同时披露
  `narrative_coverage_cases`（正/反）作为对照变量；若某属性的区分度
  与覆盖数本身的区分度不可分离，证伪条件应把它显式列为竞争解释；
- **词表派生的覆盖瓶颈**：派生 pass 的最小支持度会滤掉低频主题——
  这是诚实的取舍（宁可 evidence_unavailable，不造稀疏对比）；K 与
  支持度参数冻结在契约里，可调可审计；
- **语料稀疏**：23/32 家有叙事文档是当前底数；对比矩阵按实际覆盖
  呈现，不为满屏好看而填充；
- **成本增量**：browse 预算全用满约 +15–25K tokens/seed；属性抽取
  确定性零调用；check 阶段叙事 LLM 执行 16 次 ≈ 现状（V98 已付）。
- **analyst_recommend 类**：目录由真实可用族生成，该类当前语料近空
  则不展示；接入新数据源属于数据侧工作，不在本方案内。

## 6. 分阶段实施与验收

**Phase U1（纯界面，无新语义）**：case briefs + 统一目录/浏览动作 +
browse 预算 + modality_footprint 披露。
验收：影子轮中模型实际使用浏览（账本计数）；不变量四项全过；
结构化提案能力无回归（现有 830 测试 + 已晋升链路 fixture 复跑）。

**Phase U2（属性层）**：语料派生 pass（词表入契约）+ AttributeProjection
+ digest/compare/证据校验三处对称化。
验收：零特判审计（`grep` 确认 src 无主题名硬编码）；影子轮出现
属性矩阵驱动的提案（计数目标 ≥1，定性要求引用 attribute_ref）。

**Phase U3（对称收尾 + 闭环）**：物化/fixture 双形态示例 + manifest
族覆盖 + 模态足迹 feedback unit。
验收：一次生产运行中，两 seed 的提案模态分布非单一；若全为结构化，
reflection 下一周期足迹字段被消费（wire 级验证）。

**总验收（对应本方案目标）**：连续两个生产周期内出现 ≥1 个叙事候选
到达配对门（无论晋升/暂缓/拒绝——到达即证明通路），且结构化因子
产出率不低于 V98 基线。**明确不设**"叙事因子必须晋升"的验收——
门的裁决不受模态影响，这是对称性的最后一步。

## 7. 与现有 spec 的关系

- `signal_mining_agent.md`：动作枚举 +3（browse_sources/browse_documents/
  read_document 并入既有 read_span 语义）；Evidence Graph 增 Attribute
  节点与派生 pass 契约；视图字段增 case_briefs/attribute_case_coverage/
  modality_footprint；预算表增 browse 维；
- `signal_evolution.md`：证据校验的"点名概念"规则外延为"点名概念或
  属性"；manifest 契约增族覆盖；
- 行动方案 v2.1：本方案作为其后继增强项并列记录，不修改其已完成结论。

## 8. 决策点（待用户确认后进 Phase U1）

1. browse 预算初值 24 与字节上限是否认可（或先影子轮校准再冻结）；
2. 词表派生 pass 的 K=24、最小支持度阈值（建议 = 覆盖 ≥6 个 dev case）；
3. case briefs 是否纳入开局视图全量 32 家（成本 ~6K tokens）还是按需
   inspect（更省但降低开局语境）。

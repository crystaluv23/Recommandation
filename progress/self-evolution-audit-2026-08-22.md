# 当前信息方案自进化系统审计 - 2026-08-22

## 结论

当前 `HEAD=23b2657db7bf7afb88af431d1c0d1151627cbcf0` 的自进化流程尚不能判定为
“可跑通”。本次在两个全新隔离 workspace 中真实调用 DeepSeek，并检查了持久化的
system prompt、user payload、canonical wire body、响应、轨迹、失败件、attempt ledger
和权威指针：

- `self-evolution-system-audit-20260822-v1`：1 个候选，53 次已完成调用，
  278,501 tokens，实际成本 `$0.08246252`；完成 5 个 case 后，Signal 路由的唯一纠错
  响应仍超过 4 个 `context_tags`，候选被拒绝。
- `self-evolution-system-audit-20260822-v2`：3 个候选，155 次 attempt（154 完成、
  1 次 TLS EOF 失败后精确恢复），1,089,911 tokens，实际成本 `$0.32196556`；
  三个候选分别在 1、9、2 个已完成 case 后失败。第一个仍是 Signal 路由纠错输出
  超过 240 字符，后两个超过每 case 120,000-token 上限。
- 两次实跑合计实际成本 `$0.40442808`。两者都写入 `round-0001/rejected.json`，
  `state.json:last_completed_round=0`、`cycle_state.json:last_completed_cycle=0`，
  Registry hash 保持 `4011b59a...`，Locked Test 未打开。

因此，本次“真实跑通”的事实结论是：**当前默认合同在 Fast loop 内 fail-closed，无法
完成并提交一轮，更没有触发当前实现的完整 Slow loop。** 这不是审计缺少执行，而是
执行本身证明了当前流程被内容与预算问题阻断。继续重复付费运行不会提供新信息，应先
修复下面的 P0 项。

## 审计范围与证据边界

- 当前实跑合同：
  - v1 contract hash `8085936c...`
  - v2 contract hash `8a6fb1131846f021525a9dbeb5d486637c3234e128c52c2ccd29b264d589d6e6`
- 数据：批准的 v13 manifest（hash `13772d03...`）、全局 Raw Info oracle、14 个
  stable Signals。
- 当前实跑实际触达：共享数据 gate、Plan proposer、Basic Info、`H_init`、Signal
  路由/执行、`H_reflect`/finalize、Blind Predictor、post-hoc reflection。
- 后半程补充证据：
  - 最近一次提交完整 Fast/Slow 周期的 `deepseek-v4-flash-signal-context-window-20260822-v4`
    提供 Plan critic、Round reflection 和旧 Slow loop 的真实请求；它绑定旧 revision
    `c286459`，所以旧 Slow-agent token 只作为历史基线，不冒充当前实现。
  - `/private/tmp/signal-mining-pipeline-live-20260822` 是重构后 H1/H2/H3 的三次真实
    DeepSeek 请求，合计 13,513 tokens、`$0.003969`。当前 HEAD 的 Mining 角色合同
    与这些实际请求一致；之后的 Update 重构没有进行新的外部验证。

## 逐环节真实 context / prompt 审计

| 环节 | 实际检查内容 | 判断 |
| --- | --- | --- |
| 冻结与共享数据 gate | `new` 阶段零 LLM 调用；16 Anchor + 8 Random 的快照在 proposer 前准备。三个不满足 Signal readiness 的 prospective Random case 被跳过，随后补齐 24 个 ready case。 | 符合设计。共享数据缺口没有变成 Plan fitness，也没有推进指针。 |
| Plan proposer | 完整打开请求 `3814f7...`：system prompt、`fixed_prior`、两个历史父 Plan、空 `meta_info`、proposal slot/constraint、8,469-byte canonical wire body；recorded SHA-256 与本地重算一致。 | 线协议正确，语义输入不正确。两个父 Plan 仍要求“无条件/条件概率”“final Signal classification”，并把 surge 说成由 Signal Registry 定义。三个新 Plan 全部继承了这一过时语义，而固定 Predictor 实际要求四档 judgment 和 evaluator 定义的 2x 股价标签。 |
| Plan 的 Basic Info policy | 三个实际 Plan 的 `B` 都逐项解析。候选 2 请求 `analyst_reports`/`sector_news`，实际每个 case 都得到 `adapter_missing`；proposer payload 没有可用 source-type catalog，提案验证也只校验 market backbone。 | 不符合可执行 Plan 设计。模型可以生成运行时无法满足的数据请求。 |
| Basic Info resolution | 检查了 KGC、BMBL 等实际 bundle 中的 market/news 原文 span、offset、hash、DataGap。KGC 候选 2 是 4 个 market spans + 8 个 news spans + 1 个明确未解析请求。 | 解析、point-in-time `available_at`、DataGap 和 lineage 正确；但 market JSON 每行重复带 2026 年 `retrieved_at`，将事后采集元数据送入 2025 as-of 模型上下文，虽非未来价格标签，仍是无用的时间污染。 |
| `research_controller_initialize` | 实际请求只含 `basic_info` 与当前 Plan 的 `H_init`；KGC 响应形成 5 条 beliefs、1 条假设、5 个信息需求。 | 边界基本正确，但 `ResearchState.supporting_evidence` 是不可本地校验的自由文本，没有 document/span ref；system prompt 也没有把来源明确声明为不可信数据，存在 source prompt-injection 风险。 |
| Signal 路由 | 完整打开原请求和 correction。payload 包含 information needs、未执行 cards、先前 results/fingerprints。实际请求 `e30dd0...` 面对 5 个需求直接选择全部 14 个 Signal。 | “smallest unique batch”只有自然语言约束，没有数值上限或 token-aware budget。实际行为与设计意图相反，是两次实跑失败和 token 长尾的直接原因。 |
| Signal 路由纠错 | `ceb409...` 已明确收到 `selection_reason <=240` 的错误，但纠错响应仍返回 249、250、250、268、249 字符；另一次纠错曾把 5 tags 修成 4。 | fail-closed 正确；让 LLM 修复字符串长度/tag 数量不合理。这些非语义格式问题可以本地确定性截断/去重，当前实现反而重复整个 payload 并可能丢弃整个候选。 |
| Signal 执行 | 检查 `signal_spec`、完整 skill、as-of、document ids/hashes、24k literal projection、真实响应和 citation。KGC `financing_listing_action` 从新闻中引用了可在完整 Raw Info 精确验证的 span。 | 结果合同、`unavailable` 与 evidence 一致性、完整文档本地校验正确。context 质量很差：43 个请求发送 1,028,330 个 source chars；其中 filing spans 1,001,600 chars，HTML tag 本身 544,519 chars（54.36%）。大量 6-K header/HTML boilerplate 挤占 24k 窗口。 |
| `H_reflect` / finalize | 实际请求分别包含旧 state + 一整个 Signal batch，以及 state + termination trigger。 | 一次批量反思的方向正确。finalize prompt 先要求 `decision=finalize`，随后复用的 output 示例却仍给出 `decision=continue` 和非空 need，内容内部矛盾；当前样本碰巧都按前者输出。 |
| Blind Predictor | 检查 KGC 请求 `ddcf40...` 的完整 final context。名称、ticker、CIK、document id 均替换为 `[MASKED_COMPANY]`；system prompt 明确定义 5 日均价 baseline、未来连续 5 日均价最大值、6 个月、四档判断及 binary mapping。 | 固定 Predictor 合同和当前 case 匿名化符合设计。但同一请求仍携带过时的 `H_analyse`（要求概率与 Signal 分类），只能靠 system prompt 的 override 避免语义漂移，不应让冲突内容进入。 |
| Post-hoc reflection | 实际 payload 是完整 original context + immutable prediction + revealed truth + deterministic correctness/四档反馈。KGC 响应正确复制了 framework correctness。 | label reveal 时机和不可改写 prediction 正确；但为每个 case 再发一次几乎完整的原始上下文，当前实跑消耗 128,105 input tokens。 |
| Plan critic | 历史完整请求 `04824f...` 输入 41,802 tokens。当前 `_plan_critic_trajectory` 仍把未掩码的 `information_needs` 原样放入 compact rows。真实请求含 `Kinross`、`Wynn Resorts`、`Bumble` 等名称。 | **违反 spec。** 该角色应只有 opaque case index；当前 field-name blacklist 不检查字符串值，也没有 alias mask/scan。 |
| Round reflection / FIFO meta | 真实 critic 输出按公司名列举 FP/FN；Round response 又写入 `Kinross`、`Stitch Fix`、`FTAI Aviation` 等名称，并持久化到 `meta/round-0001.json`。单个 meta entry 83,565 bytes。 | **违反匿名 meta-info 设计并污染后续 proposer。** 这不是日志展示问题，而是可进入下一轮 LLM context 的学习状态。 |
| 当前 Signal Mining H1 | 真实 `3d9cf...` payload 含 meta/backlog、14 张 stable cards、7 种实际 source types、limits；模型给出 3 个可证伪 hypothesis。 | source-type 枚举和窄角色合同正确。若输入的是当前真实 meta，前述身份和固定语义污染会继续流入 H1。 |
| 当前 Signal Mining H2 | 真实 `b6ccbe...` 只见 opaque refs 和 label-hidden briefs。批准 Discovery 的 8,755 cases 中，business description、industry、market cap、development stage、revenue segments 的非空数全部为 0；确定性 32-case sample 只有 2 个有任何本地文档，32 个的 business/industry/sector/market-cap 全为空。 | 隐私边界正确，排序信息不足。实际两张 brief 除 exchange/listing-age/coverage 外不可区分，模型只能对三个完全不同 hypothesis 返回同一排序，逻辑上不能完成“按适用性选 case”。 |
| 当前 Signal Mining H3 | 真实 `d9a54f...` 输入 9,970 tokens，以 label-visible positive/control evidence 做两个 contrast，输出两个 `refine`、零候选。身份已 mask。 | label timing 正确。两个 hypothesis 重复发送同一 positive/control evidence；31,255-char user payload 中约 10k chars 是可去重重复。AMD positive packet 的 4 篇新闻里包含 Salesforce、Synopsys、GlobalFoundries 主体文章，说明 provider ticker-association 不能等同于 company-specific evidence。 |
| 当前 Signal Update | 当前 run 未提交 Fast round，所有 profile 仍为 zero-observation，因此不会产生 actionable target；重构后的 `H_U` 只有本地选 target/induction/hidden holdout 后的一次 `no_change/defer/update` 调用。 | 零 target 零调用符合设计，但当前实现尚无一份 end-to-end 当前合同下的真实 Update 请求，因此不能宣称外部内容验证完成。 |

## 主要问题（按优先级）

### P0 - 阻断正确运行

1. **默认合同无法完成一轮。** 3/3 候选分别被路由结构错误或 120k token cap
   淘汰；已有 12 个完整 case 的付费工作全部不能进入 fitness。
2. **Plan critic -> Round meta 的身份泄漏。** 当前代码与真实 artifact 共同证明公司名
   进入 outcome-aware FIFO，并可在下一轮进入 proposer；这直接违反架构/spec 的匿名约束。
3. **Signal 路由没有硬 batch cap 和预算感知。** 一个实际请求选择全部 14 个 Signal；
   4 个完成 case 各执行 14 个 Signal，其中一个单轮 6 次 soft-Signal 调用使 case 达到
   99,217 tokens。
4. **Slow H2 缺少可排序信息。** 全部 8,755 个 Discovery case 的关键 profile 字段为空；
   当前 brief 不能支持“哪个公司适用于哪个 Signal hypothesis”的核心判断。

### P1 - 显著降低学习质量或浪费预算

1. 历史父 Plan 与 fixed Predictor 语义不兼容，但 seed compatibility 只校验结构/版本，
   没有阻止过时概率/Signal-classification 语义继续遗传。
2. proposer 不知道当前可用 source types，也没有校验 `B` 中除 market backbone 之外的
   source types，已真实产生 `adapter_missing` 请求。
3. soft Signal 上下文的 SEC HTML boilerplate 占 filing span 54.36%，既浪费 token，
   又让实际 guidance/order 等正文落不到窗口里。
4. budget 只在一次模型调用返回后计入并检查。两个失败 case 已经完成 Blind Predictor
   调用才发现超过 120k；调用和前序研究都已付费。
5. H3 的 provider news 有明显“只在 ticker_sentiment 中提到目标、正文主体是别家公司”
   的噪音；当前 evidence ranking 没有 target-relevance floor。
6. post-hoc 全量重发 original context；Basic Info、Predictor、post-hoc 还累计发送了
   1,336 个 `retrieved_at` 标记。
7. ResearchState 证据是自由文本，缺乏 source refs；所有 source-bearing role 缺少明确的
   untrusted-data / prompt-injection 指令。
8. stage-specific prompt 没有 stage-specific output 示例；finalize 的强制值与通用示例
   相互冲突。

## Token 审计

当前 v2 的 154 个成功请求共使用 1,029,945 input tokens、59,966 output tokens：

| stage | requests | input tokens | 占 input | 最大单请求 input |
| --- | ---: | ---: | ---: | ---: |
| `llm_signal_execute` | 43 | 386,937 | 37.6% | 11,290 |
| `blind_predictor_predict` | 14 | 168,637 | 16.4% | 27,283 |
| Signal routing + correction | 33 | 150,288 | 14.6% | 8,306 |
| `research_controller_initialize` | 15 | 131,748 | 12.8% | 21,641 |
| `blind_predictor_posthoc_reflect` | 12 | 128,105 | 12.4% | 23,648 |
| controller reflect + finalize | 34 | 59,244 | 5.8% | 4,149 |
| Plan propose | 3 | 4,986 | 0.5% | 1,662 |

可量化的优化空间如下；数字彼此有重叠，不能简单相加：

1. **先清理 SEC model-facing text。** 当前 Signal requests 中 544,519 个字符是 HTML tag；
   按本轮 wire-byte/token 比例约等于 150k input tokens 的量级。应保留完整原文/hash 和
   offset mapping，但向模型发送可回溯的 normalized text projection。
2. **省略全零 learned profile。** 33 个 routing payload 中 376/376 张 card 都是零观测
   profile；重复 profile 占 218,711 chars（整个 routing user context 的 48.5%），
   约 60k input tokens。可在 payload 顶层声明一个 default profile，只发送非默认差异。
3. **按共享文档批处理 soft Signals。** 43 个请求只有 16 个 document-id sets；扣除同一
   请求 chunk overlap 后，跨请求重复发送的原文至少 374,211 chars，占 36.5%。多个
   Signal 可以共享一次 evidence projection，再分别输出和校验 versioned results。
4. **压缩 post-hoc 输入。** 它单独占 128,105 input tokens。完整匿名原文继续本地持久化，
   reflection 可接收 prediction、final state、compact Signal results 和受控 evidence index，
   仅按需展开原始 span。
5. **H3 case packet 归一化。** 将 unique case packets 放在顶层，hypothesis comparison 只
   引用 case refs；真实三调用 probe 中可立即少发约 10k chars / 3k tokens。
6. **去除 market row 重复元数据。** `source`、`symbol`、`retrieved_at` 应成为 document
   metadata，而不是每个 bar 重复；这同时减少时间污染。
7. **防止 meta 线性膨胀。** 历史一个 24-case meta entry 已有 83,565 bytes；FIFO 10
   entries、每轮最多 3 个 Plan 会让每个 proposer 请求线性增长。完整 artifact 应继续
   本地持久化，但 proposer 改用 identity-free learning atoms + 可选择展开的 refs。
   这项会改变当前“完整 FIFO 全量入 prompt”的 spec，需要先做设计决策。
8. **最后再压 system prompt。** Predictor 的 3,053-char system prompt 多次重复 possible、
   uncertainty 和 50% 概念；精简有帮助，但远小于原文、profile、post-hoc 和 meta 问题。

## 建议修复顺序与验收条件

1. 先更新 spec：定义所有 retrospective/meta role 的 value-level identity mask+scan、
   Plan 可用 source-type catalog、Slow brief readiness floor、每轮 Signal hard batch/token
   budget，以及完整 meta artifact 与 model-facing compact view 的关系。
2. 再修实现：critic 前 mask、meta 落盘前 alias scan；proposer source-type validation；
   deterministic route normalization；pre-call token reservation；SEC/market normalized view；
   H2 profile gate；H3 dedup 和 target relevance。
3. 加 exact artifact regression：用本次真实的 `04824f...` identity leak、`e30dd0...`
   14-Signal selection、`ceb409...` overlength correction 和 HTML-heavy Signal context 作为
   固定失败样本。
4. 修复后的新合同必须满足：3 个候选至少有一个完整评估 24 cases；
   `last_completed_round=1`、`last_completed_cycle=1`；critic/meta/proposer 请求对全部 24
   case alias 扫描为零；H2 brief 达到预设语义字段覆盖；H1/H2/H3/Update 的真实请求与
   响应均持久化；默认 120k cap 下没有 post-call overflow。

## 已确认正常的部分

- canonical provider body 的 bytes、length、SHA-256 与发送前重建一致。
- exact request cache 在跨 Plan Signal 调用和 TLS resume 中生效；失败的 attempt 116
  实际成本为 0，resume 只重试同一 request hash。
- point-in-time `available_at`、完整 Raw Info 本地保留、Signal citation validation、
  `unavailable` fail-closed、shared-data pause/replacement、Locked Test 封闭均按设计工作。
- rejected round 没有推进 Plan/Cycle 指针，没有提交学习 event，也没有改变稳定 Registry。

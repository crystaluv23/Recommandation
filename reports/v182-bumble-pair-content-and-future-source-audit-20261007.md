# v182 Bumble 双 Plan 内容与未来来源审计

日期：2026-10-07。运行：`runs/cold_start/minimal_rounds_v182_integrated`；冻结源码 `85ffff9ed976cc4597b7e6e26a2dfe7537ab4099`；审计前主目录 checkpoint `43d88a6c`。案例 `cik_0001830043:20250930`，预测截止 `2025-09-30T00:00:00+00:00`。

**验收未通过。已确认实际模型输入包含未来业绩内容；另有问题被过早关闭、比较依据漏读及学习归因失真。** 这两条预测均为正确的 non-surge，但正确标签不能证明输入满足 PIT，不能证明原因正确或自进化有效。本次没有外部模型调用、来源迁移、后继启动或旧结果改写。

## 亲读范围与证据绑定

1. 亲读本案 16 次原始输出，包括 Initialize、Routing/付费 patch、两个 LLM Signal、Reflect/native patch、Predictor 和 Posthoc；核对请求消息与 cache 原答逐值一致，逐文件保存 SHA-256。六种固定 system prompt 的 hash 与此前全文亲读的 Enbridge 构造相同；本次另亲读六段真实进化技能。
2. 按十个有界组亲读全部 **68 个不同 projection id、118,451 字符**的可见源窗。四处重复投影仅匿名 token 编号不同，原编号与新编号均记录，规范化后的其他字符逐字相同；这不表示不同阶段匿名编号可互换。
3. 亲读 16 张 Routing 卡。两 Plan 的卡逐值相同；卡内重复的 `performance` 与 `learned_profile.performance` 完整相等，后者已亲读。其解释明确为 observational association，不能当因果效果。
4. 亲读实际 Reflect 首 20 张目录卡：45 eligible、25 omitted、`next_cursor=20`，两 Plan 除匿名编号外相同；没有翻页/fetch 的实际动作。上次目录链路修复属于主目录代码准备，没有进入冻结 v182。
5. 本案 47 份绑定源文件 SHA 全部一致；它们的全部原文并未都被亲读。全输入 2,875 份 news 文件 SHA 再验一致；本次另亲读 13 条 `/overview/` 家族完整 provider 摘要并追踪模型请求，不能据此称全部新闻内容/时间已验收。

JSON 伴随文件保存原调用 hash、可见窗口、全部原答、目录/路由/need 合同、落盘 state/delta/Signal/预测/反思、生产回放和来源链。四条案例内容链已有 Enbridge/Bumble 成对审计；其余 **44/48** 仍须逐环节内容复核。全流程没有 PASS 标记。

## 已证实的未来内容

Bumble 新闻 `avnews_82c6cc3e5143825f6225f673`，正文 hash `e3fa9e10193ccb7d57c63d8a3602d521845ddbc7897bee1a1d1e0882663786f6`：

- `published_at=available_at=2025-04-24T17:52:47+00:00`；实际回补读取时间 `2026-08-16T05:07:30.317105+00:00`。
- 原 URL 为 Stock Titan 的动态股票概览 `/overview/BMBL/`。摘要描述已经公布的 Q4/全年 2025 业绩，包含全年收入下降 9.9%、净亏损 906.6 百万美元。
- 公司正式披露这些业绩的日期为 **2026-03-11**，财年截至 **2025-12-31**，两个数字与摘要一致。这证明正文包含案例截止之后的信息；它不证明动态页面整段正文的精确创建时间，不能直接把整条记录改成公告日期。[Bumble 官方全年业绩公告](https://ir.bumble.com/news/news-details/2026/Bumble-Inc--Announces-Fourth-Quarter-and-Full-Year-2025-Results/)
- **实际进入 attempt 18 的订单 Signal 输入**，projection `projection_ebdbbd8c4bb720ea857ac78d`。扫描全部 656 个保存请求，只有这一请求包含该 document/hash/projection 标识；603 份 completed 输出及其他阶段的实际 payload 未见该标识或这组未来数字。
- 订单结果为 domain unavailable，support/counter 都为空；两 Plan 的结果及输入 fingerprints 逐值相同，c02 对这两个 LLM Signal 的 batch usage 为 `llm_calls=0/cost=0`，不是再次检验源时间。两个落盘 trajectory 均保留了污染源 fingerprint。未找到下游引用不等于证明模型没有受影响。

同类 13 条动态概览中还发现：

| 冻结输入 | 旧 available_at | 正文冲突与确认程度 | completed 模型命中 |
| --- | --- | --- | --- |
| VCV：`avnews_1dea1d693b66e92ab27d4dd4` | 2025-04-25 | 明确写“截至 2026-03-03”的当前价格；不能把它作为 2025 年行情。价格数值本身未独立核验。 | 无 |
| PX：`avnews_91686218edaaba6aa27c42e6` | 2025-04-24 | 更名 Ridgepost、改 ticker 为 RPC 的公告实际在 2026-01-12 发布，生效日为 2026-02-11；与摘要描述一致。 | 无 |
| 其余十条 | 各自旧时间 | 本次未仅凭 URL 判定全部污染；需要正文版本证据。 | EVG：50/51；SFIX：65/69/70/293/297/298；其余无 |

更名日期依据为 [P10 官方公告](https://ir.p10alts.com/news-releases/news-release-details/p10-announces-upcoming-name-change)。PX/VCV 出现在 MS 的 provider 查询响应中，相关公司文章被绑定到查询公司；不能把 related-company news 自动当成错误主体或客户订单。

三条冲突均在原供应商 raw cache 的原始 feed 行中存在。分别读取两个 cache 原件并保存 file hash，以实际 `tickers/time_from/time_to/limit/sort/retrieved_at` 调用生产 `_normalize_news_item`，**完整 canonical RawInfoDocument 逐字段复现相等**。归一化把 provider `time_published` 直接作为 `published_at/available_at`，数值时间过滤本身运行正常，却没有证明所返回摘要属于那个历史版本。这是来源正文版本与可用时间的契约缺口；不是审计转录错误，也不能归咎于 LLM 生成了这段未来内容。

## 原始来源与 Signal 内容

已读 Q2 10-Q 财务表有明确“千元”和季度/半年列头。半年收入、亏损、现金、债务与期末股数可分别定位，不能把不同日期/度量的股数混用。市场 180 日卡与原窗口一致；MSN 摘要的 $9.08 与同日行情 $7.05 冲突仍是待核对问题，未猜测具体成因或修改来源。

Q1 transcript 旧指引是 Q2 收入 235–243 百万美元、adjusted EBITDA 79–84 百万美元；6 月 25 日 filing 更新为 244–249、88–93。早期两项范围也在 [Bumble Q1 官方公告](https://ir.bumble.com/news/news-details/2025/Bumble-Inc--Announces-First-Quarter-2025-Results/default.aspx) 中明确披露。这里核验内容，不改待选择的 transcript 可用时间规则。

`guidance_acceleration:v3` 要求 current/prior 两组 span 同时可见，但 attempt 17 的 16 个窗口没有旧数值。模型明确据此返回 `neutral/partial`；c02 从同一缓存取得同结果。**缺少比较输入不能证明没有上调。** 旧数值实际上在 c02 Basic Info 的完整可见窗以及 Predictor 259 的请求里；posthoc 260 的 compact context 却没有它们，反思把读取遗漏写成旧指引缺失。

订单 18 的 18 个窗口包括诉讼、薪酬/签字股权、供应商/cloud 采购、回购及这条未来摘要，没有把它们编造成公司客户订单。domain unavailable 的空证据结果符合对象区分，但不能洗净该次输入污染。

`net_share_retirement_yoy:v3` 用原 financials 文档和冻结执行代码重放，**完整 canonical 结果与原件相同**：`1 - 104319154 / 127490453 = 0.181749...`，两个分母/分子都是各自半年加权平均股数，来自同一已披露 accession、相同单位、2025/2024 的可比期间。它不是以 December 31 期末股数与 June 30 期末股数计算；不能把这个正确结果当成错值修复，也不能用它证明预测时点还有多少回购额度。

## Initialize、问题关闭与反思损失

原 c01 eight beliefs/eight refs 落盘为 four/four；c02 eight/eight 为 four/two。冻结生产 Controller/完整 parser/fallback 脚本回放复现非引文 state 与引用数量：日期/数量没有在同一 claim 的字面引用里、不同数值跨引用混用，以及伪造 `computed_metrics` projection 被隔离。这里不放宽文字证据权限，也不补造引文。

该回放是零外部的诊断：匿名 wire quote 的恢复与外部 transport 没有重放；c01 scripted caller 被调用两次，而真实 completed Initialize wire 只有 attempt 14。不得把两次脚本调用称为新的 live 执行、付费纠错或 exact transport replay。

两个 Plan 在 Routing 都将 guidance 标为 Q3 问题的 full answer。实际结果只有 Q2、coverage partial；但 Reflect 的运行时 `need_transition_contract` 仍将它写为 available full answer，指令是“若采用其证据则删除原问题”。19/257 原答执行了这一指令，**两条持久化 delta 真实把 Q3 问题移入 resolved**。此后还有五条 unresolved need；预算终止本身按规则 finalize，但没有得到 Q3 答案。

原 terminal patches 20/258 包含进一步改写引文/claim 的动作；实际 terminal delta 只改变 decision，未把所有模型拟写内容落盘。报告同时保存原 patch 和最终 delta，不能把模型提出的修改当成已接受 state。

## 预测正确与学习真实有效的区别

21/259 均 unlikely/null/medium，实际 non-surge、最大倍数 `0.9217739451801663`。这一对子没有高 magnitude 预测，不能评估 3–10x/10x+ 的能力。

Predictor259 已看见 Q1 回购 $29M 与当次 call 的剩余 $50M，仍把资本配置 timing/magnitude 统称未披露。应区分已知早期行动与未知的 9 月剩余额；不能把 May 的余额自动延续，也不能抹掉已知历史金额。

两份 Posthoc 亲读后发现：虽然 limitations 提到单案不足证明因果，部分 `fact` 正文仍把收缩和距 2x 门槛的距离归为二元预测正确的主要原因。baseline 与其 2x 门槛的比例是定义恒等式；正确单案不能证明这一特征有鉴别力。260 又继承旧指引不可见的错误诊断。这些只是已保存的研究反思，尚未构成有效教训或独立 benefit；Slow memory 依然 failed/processed 0，新方向 v3 仍 pending_use/unverified。

## 系统性修复边界与后续验收

处理同类来源时保留原 oracle/cache/请求/评分，核验历史正文版本可用时间，准备可审查的 append-only 新记录与新输入 manifest；不能猜时间洗净污染，不能直接重启旧输入。它也不能用公司/年份 regex 代替证据：其他公司的 FY2025 可能早在 2025 年初结束，PIT 文件也可能合法讨论未来预期；动态 URL 有历史快照时不能仅凭 URL 删除。

问题关闭要贯穿 Routing intent→实际执行结果→coverage/对象/期间→Reflect 合同→validator/typed correction/fallback→持久化→反思→下周期消费；potential full capability 不等于 actual full answer。保留有用的部分事实及未答部分，不以 Bumble/Q3 特例修复。读取/比较修复必须保持 Signals、原预算和 provenance，不将少调用当成优化。

学习路径需要保留“哪个消费者缺少哪段上下文”的来源信息。读取不足、数据不存在、经济中性、技术失败与因果假设分别有不同证据要求；格式和引用通过不能替代语义真值。现有时间政策与独立评价方案仍待用户选择，本次没有新增研究/评分定义。

v182 正式 Fast/Slow **1/1**、case 技术排除 **0**，但 Signal 校验失败仍 **6**；新 magnitude Signal 入库 **0**，29 个正向幅度仍全部 **2–3x**。三项用户验收都未完成。继续剩余实际内容与消费者链审计；污染输入不得用于有效性背书。

验证：报告一致性断言、16请求/cache、47本案源与2875新闻file hash、三条完整producer归一化回放、冻结v3回购完整canonical回放均通过；仓库lint PASS（最新反馈UTC 2026-10-06T23:51:04Z已读取）。本轮只写审计/进展/经验记录，未改运行代码，因此未重复运行全量单元测试。所有离线脚本外部调用0，不构成live改善证明。

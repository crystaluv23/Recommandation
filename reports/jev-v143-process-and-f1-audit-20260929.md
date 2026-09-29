# V142/V143 过程、反思消费与 F1 独立复核

日期：2026-09-29。审计代码 HEAD `2e6d7c5`；V142 冻结执行代码 `4de815b`，V143 为 `ebf1d83`。本次只读历史运行文件、检查当前代码、离线复算；没有外部调用，没有修复运行代码、修改阈值或重跑预测。

**结论：F1 有真实的同案例退化，但“每轮越学越差”不是准确的指标描述。更重要的是，之前的审计高估了闭环完成度：高层筛选没有成功产出，部分重要反思被选择性丢掉，Slow 的真实挖掘分支没有收到已经读取的反思原文。当前不能认定完整自进化设计已经得到公平验证，也不能把所有剩余失败归于研究能力。**

## 1. 核定运行与比较边界

- 工作区：`runs/cold_start/evolution/information-evolution-jev-dual-self-evolution-20260928-v142` 和 `information-evolution-jev-dual-self-evolution-20260928-v143`。下文的相对运行路径均以此为根。
- 两者 `state.json.last_completed_round=2`，但 `cycle_state.json.last_completed_cycle=1`，`active_cycle=2/slow_loop`。即两个 Fast round、一个完整 Fast+Slow cycle；第二个 Slow 未完成。
- V143 ledger 为 1,252 attempts，已记录实际费用 $5.31383776；最后一个 `slow_source_read_correction`（attempt 1252）仍为 `in_progress`。Fast checkpoint 已提交，不等于外部调用干净收尾，也未在本次审计执行恢复验证。
- V142/V143 dataset、同轮 evaluation snapshot、Registry v6 一致；但 code、seed manifest、slow-history、Raw Info inventory、实际 Plan 均不同。V141→V142 连固定 priors hash 也变化。因此“唯一变量是代码”的说法不成立，不能从单次差值估计代码改造的因果效应。
- V143 新四个 Signal 没有任何晋级；下一轮仍使用同 hash 的 v6，Fast 轨迹未出现四个新 ref。它们尚未构成改善渠道，不能说它们被使用后拉低了 F1。
- V143 最新候选 .56 没有替换本工作区保留的 .60 最佳记录；跨工作区历史成绩、当前候选曲线与当前保留最佳值必须分开。

## 2. F1 复算：下降发生在哪里

以下只列完成全部 24 案、获得正式 fitness 的 Plan。TP/FP/FN 直接从落盘预测及标签复算，技术失败的正例保留在 FN 内。

| Run / Plan | 综合 F1 | Precision / Recall | Anchor F1（16案） | Random F1（8案） | TP / FP / FN | 技术排除 |
| --- | ---: | --- | ---: | ---: | --- | ---: |
| V142 r1 c01 | .6667 | .6250 / .7143 | .8000 | .4000 | 10 / 6 / 4 | 4 |
| V142 r1 c02 | .6897 | .6667 / .7143 | .8000 | .4444 | 10 / 5 / 4 | 2 |
| V142 r2 c02 | .7200 | .8182 / .6429 | .6250 | .8889 | 9 / 2 / 5 | 4 |
| V143 r1 c01 | .6000 | .5625 / .6429 | .6316 | .5455 | 9 / 7 / 5 | 2 |
| V143 r2 c02 | .5600 | .6364 / .5000 | .7368 | .0000 | 7 / 4 / 7 | 3 |

V143 r1→r2：固定 Anchor 反而提高，8 个 Random 全部换样。r2 Random 的 5 个正例全部漏掉（1 个技术失败、4 个正常执行后的 unlikely），另有 1 个 FP，拉低综合分数。小样本和轮换样本使这一段不能直接称为“同样本连续退化”。

**V142 r2 与 V143 r2 是相同 24 案，.72→.56 的差异确实存在。** 具体变化是：4 个原 TP 丢失、2 个原 FN 恢复为 TP、2 个原 TN 变为 FP，净 TP 少 2、FP 多 2。两个版本都预测 11 个正例，并非仅仅整体更保守。

| 同案变化 | 案例 | 已核验归因 |
| --- | --- | --- |
| TP→技术 FN | `cik_0001114995:20250530` | H_init 多个数字没有得到同 claim 的 literal refs 支撑，纠错耗尽 |
| TP→研究 FN | `cik_0001309402:20250530`、`cik_0001855644:20250731`、`cik_0001051627:20250930` | possible→unlikely；具体证据丢失见下一节 |
| FN→TP | `cik_0001164727:20250731`、`cik_0000723125:20250731` | 两个 Anchor 恢复 |
| TN→FP | `cik_0001174922:20250731`、`cik_0001563411:20250731` | Anchor、Random 各新增 1 个误报 |
| 技术 FN→研究 FN | `cik_0001847806:20250530` | 执行恢复但仍判 unlikely，F1 未改善 |

技术排除从 4 降到 3，技术正例从 3 降到 2，故本次同案下降不能归结为技术失败总数增加。技术错误仍直接损伤绝对分数，也会影响学习内容。

当前 `score_predictions` 的机械 TN 还包含技术负例：V143 r2 TN=6，其中 1 例技术排除，只有 5 例是正常研究的 TN。本审计保留历史分数，并在 JSON 中另列 `research_true_negative`，不把技术弃权称为成功研究。未完成 Plan 的局部 F1 不参与表格及优劣结论：V143 r1 c02 15/24、r2 c01 19/24；V142 r2 c01 9/24。

## 3. 三个原 TP 丢失：关键证据没有走到预测输入

对照均使用 `plans/plan_r0002_c02/record.json` 中对应 case 的 `basic_info`、`initial_state`、`final_context`，并核对文档 hash、可见 spans。详细摘录和投影坐标保存于[内容证据](jev-v143-content-evidence-20260929.json)。

**AXT（1051627）：Basic 选中了文档，却没有把关键片段提供给模型。** V142 的 operating-report 请求不带 query，两个 SEC 文档提供 3 个 spans，包含 2025-08-19 出口许可、恢复磷化铟发货、未纳入 Q3 指引的数百万新增收入；最终研究状态保留该催化剂和 AI 需求。V143 增加 `business risk factors management discussion segment economics` query，同两个文档只显示 1 个诉讼 span；forward-bridge 请求显示的是一般“业绩不达指引则股价下跌”的风险声明，新闻也换成长期亏损叙述。所有可见 Basic spans 和最终状态都没有出口许可/磷化铟。

两版共同文档为 `sec:cik_0001051627:000143774925026516` 与 `...:000143774925027362`。这不是“原始资料不存在”，而是有界抽取/查询选择丢失了实质催化剂。`resolved`、`contract_satisfied=true` 和选中文档数不能证明有效研究内容可见。

**GPRE（1309402）：Basic 已经有信息，H_init 没承接。** 两版都看到 `projection_769153192620ea75471db12f` 的 CEO 离任、潜在出售等新闻；V142 另由 filing 识别战略评估。V142 初始和最终状态保留 takeover/strategic alternatives，V143 初始和最终状态均没有，最终输入主要是负现金流、弱动量、缺量化桥梁。V143 的 forward-bridge 请求还存在 resolved/contract_satisfied 为 true 而 visible_span_count=0 的情况。

**ZURA（1855644）：临床催化信息不可见，决策前状态另有目标与算术错误。** V142 可见新闻有三款临床资产和分析师目标 16.50；V143 所选文档虽包括相关新闻，但模型可见 span 改成机构持仓报道。V143 `final_research_state` 将最近收盘 1.44 称为 operative starting reference，固定五日均值 baseline 实为 1.57；又说盘中 2.18 已超过两倍阈值，并把假设写成 sustain at least twice。1.44 的两倍也是 2.88，这项算术明显错误。错误已经进入决策前研究状态，不能只归为解释文案错误。该案 Jev unlikely=.47、possible=.45，处于近边界。

持续性措辞并非 V143 首现；ZURA 该版进一步错误绑定了固定起点和阈值。这些证据支持“取证与证据承接退化、量化桥梁叙述过度主导”的诊断；尚不能离线确定每项变化对决策的独立因果贡献。`Require a quantified forward bridge` 已存在于导入种子，不是 V143 新造规则；部分新 brief 主张更保守，另一些则提醒缺桥仅是覆盖缺口，不能简单归为所有反思一致推动保守化。

**Jev 证据限制：** StructuredCaller 的 `requests/` 没有独立保存 Jev direction HTTP body；Jev client 直接调用 transport。审计从持久化 `final_context` 按同版纯函数 `_jev_prediction_state` 重建决策 state，不能称作 Jev wire 实录。该函数删除 `analysis_prompt`，因此 Plan 中 Require bridge 原句未直接作为 Jev 指令传入；错误 baseline、缺桥判断与催化剂丢失则确实存在于其 `evidence_context`。

## 4. 高层筛选没有正常工作，而且丢失的经验并不随机

### 4.1 实际完成度远低于“全部收敛”

- 已提交记录：V142 72 个 case-plan 观察中有 19 次 posthoc validation failed；V143 48 个中有 11 次（r1=8，r2=3）。这些分母包括技术/预算跳过，不是 posthoc 调用成功率的分母。
- V142 3/3、V143 2/2 已提交 Plan 的 critic 全失败。V143 两轮的 6 次 critic 调用全部在 4,000 output tokens 截断，留下不完整 JSON；对应 failed-response attempts 482/483/484、1247/1248/1249。
- V142 唯一 round-reflector 调用失败。V143 每轮仅一个完整 Plan，`evolution_plan_roles.py:2712` 的 `<2` 分支直接返回空 RoundMetaEntry，没有模型调用。
- **V143 8 个方向正确但幅度低估的 case-plan 观察，均未留下非空 reflection_items：5 次校验失败，3 次 budget_skipped。** V142 对应 16 次中 11 失败、3 跳过、仅 2 有条目。这是 case-plan 观察数，重复案例跨 Plan 分别计数；非空条目不代表其语义质量已获验证。

原离线验收验证了脚本响应能够通过新协议，没有证明真实模型可在给定输出额度内完成这种任务。Plan critic 同时要求 detail、brief、scope、refs、outcomes，却没有控制 authored items 总量；首包截断后只能整包重来，继续用相同限额。当前“有效部分由程序保留”只覆盖解析成功后的 correction frontier，没有做到独立经验逐条完成与持久化；一条错误耗尽仍可能丢掉整份反思。

### 4.2 真实反思遭遇未完整告知的类别规则

`evolution_reflection_memory.py:465–488` 要求 successful_patterns/decision_drivers 的 outcome claims 全正确，why_prediction_failed 等类别全错误。首次合同只说 claims 应匹配 canonical facts，没有把混合轴的类别规则说清。

例如 V143 request `2bec6309e93433daa3a7719fe8e9acf955dd050951692fdd2b64ee7abe84d177`：反思正确描述“binary 对、2-3x 幅度低估了真实 10x+”，同时填写 binary=true、magnitude=false，却因 why_prediction_failed 中含 true 被拒。反馈重点授权修改 category，没有明确指出应如何表达混合轴事实；模型原样回填类别，最终整份 4 条反思丢失。严守 canonical facts 有必要，但这里不是事实错误，应让归因轴与背景事实能被无歧义地表达。

### 4.3 原文在库不代表已按重要性使用

V143 proposer 首轮首屏仅含 138 条中的 31 条，第二轮首屏为 188 条中的 28 条；全是 case 层。分别 7/31、4/28 是 legacy_unreviewed 的 `budget_skipped`，却占据 plan_issues/action 槽位。高层 preferred selection 为空时，`brief_view` 按层交错、反向插入顺序填充，并非重要性筛选。

V142 4 次、V143 5 次 proposal 初始响应都直接产 Plan，没有请求 read_refs 或 browse_memory，披露数组为空。应将本次证据限定为“读了部分 briefs”，不能声称 few-shot 原文机制已经被使用并验证有效。

来源校验也不保证经验可执行。V143 首个 proposer 请求 `a22894b8...` 中 `reflection:0075d30d314780a51cdf6cd79d9de67bd4ee039b2dd1d2d47dd4a107b5ddccfb` 建议 before finalizing 搜 post-prediction-time price action。这是来源可解析但违反前瞻研究时点的建议。实际后继 Plan 未照抄，**本次未发现由此发生的真实 PIT 泄漏**；它证明 sources_checked 不能被解释成语义已审定。

## 5. 首答合同和验证器仍在制造纠错甚至误删研究需求

**H_reflect 改成 patch 时遗漏了部分状态规则。** 当前首答 prompt 拼接 PATCH_INSTRUCTION，却没有原 `_REFLECT_RESEARCH_STATE_OUTPUT` 中的 open_questions 与 next_information_needs 去重、字段形状等完整规则。实际 V143 保存的 158 份 reflect correction 请求中，56 份含 open_question_duplicates_need，22 份含 research_state_text_invalid；有的把 contradictions 写成 evidence 对象而非字符串。计数是保存的纠错请求，不是独立案例数，也不等于全部已发送。

**runtime-input guard 会误拒正常取证问题。** V143 r2 c02 `cik_0001801368:20250331.failure.json` 把“截至预测时披露了哪些 guidance/backlog/RPO/orders/analyst targets 来支持翻倍研究”当成索取系统 baseline，强制 remove。`evolution_research_validation.py:544–550,652–718` 的近邻规则把 `share price ... prediction time` 中的 prediction time 错当请求对象；左扫 `by` 又不能通过 reference-use 检查。

离线确定性复现：原句被拒；仅把 `by the prediction time` 换成 `by the cutoff` 即通过。事实需求完全相同。V143 共 17 份 initialize correction 请求触发 runtime-input 类错误，其中多个明显在问发行人披露或市场定价而非 baseline 数值；不能将这些纠错都算模型不服从。该 MP 案最终技术 FN；另一些正常 need 在纠错中被删除，即使案例后来完成，也可能损伤研究。

**Slow selector 同样遗漏初始约束。** `evolution_signal_roles.py:180` 要求至多 8 refs，初始 prompt（196–201）和 payload 没告知该上限。cycle1 H1 首答选 17 refs，attempt487→488 纠正为7并完成；cycle2 prior-memory 首答选11，attempt1252纠错仍 in_progress，不能称已收敛。这正是此前要求消除的“验证器知道、模型首次不知道”。

## 6. Slow 管线未崩溃，但学习输入断开、候选仍有技术失败

### 6.1 付费读取了原文，实际 controller 没收到

V143 使用 controller_multi_axis。`signal_evolution.py:6510` 先构造 `_mining_context`，取得 Fast briefs/catalog/选读原文及 Slow method memory；随后 6516–6576 创建 `LabelAwareMiningController` 时，只传 backlog、catalog、evidence manifest、prior modality footprints，没有传这些反思内容。

44 个真实 `mining_controller_step` 请求均不含 meta_info、meta_memory_disclosures、slow_method_memory。hypothesis backlog 的 129 条全是 unmatched_signal_need，没有 reflection_item_ref 或 meta_reflection_action。旧 footprints、未满足需求确实有进入，并不是所有历史信息都缺失；但本次新改造的“经验 brief→原案例→挖掘行动”在此断开。

已读取 Fast 原文的证据是 selector 请求 `c81d895e...`，纠正后请求 `b05c2540...` 选择了 7 refs；它们未进入实际挖掘模型。Update 的另一路接收 method memory，不能证明 controller 路径也接收。此前测试覆盖 `_mining_context`/旧 H1 payload，遗漏生产 multi-axis 分支，是验收覆盖不足。

### 6.2 四个新候选不是四个无工程问题的研究判定

`experiments/cycles/cycle-0001/slow_loop_result.json` 的 candidate_effectiveness 显示：

| 新候选 | 可用 / decisive | TP / FN | 技术失败 | 最终状态 |
| --- | --- | --- | ---: | --- |
| named_customer_order_or_contract_award_disclosed | 15 / 3 | 3 / 4 | 1 | provisional |
| new_customer_commitment_value_disclosed | 12 / 1 | 1 / 6 | 1 | provisional |
| qualifying_order_disclosure_120d | 10 / 2 | 2 / 3 | 2 | provisional |
| disclosed_customer_commitment_value | 效力未运行 | — | fixture 合同冲突 | rejected |

前三个候选确有召回不足/decisive support 不足，但另外 4 个 candidate-case 执行失败来自 projection-edge、缺返回 ref 等校验耗尽，不能混称研究阴性。导入旧候选还另有 2 个技术失败。

第四个的 `skill.md:13` 明确 generic contract funding 是 lookalike，应 neutral；`tests.json:114–120` 用该类文本却要求 unavailable。执行器遵守 skill 返回 neutral 后被拒，effectiveness=not_run。拒绝矛盾合约是正确保护，不能称真实研究效果已判不佳。

12 次 materialization 中有 8 次重做，仍整包生成 spec/skill/tests，尚未采用局部模块纠错。这是尚未迁移的 Slow 角色，不能把 Fast delta 生效外推为全系统分步生成已完成。

四个新候选高度集中在订单/客户承诺，引用的若干 discovery 片段却是 CFO 离任、财报封面、临床结果、IPO、generic funding。请求 `60bdf3aa...` 与 `a91416a9...` 可复核。可解析的 source refs 不能证明支持提出的经济机制；目前应称候选假设，不能称已学到四条有效信号。

## 7. 对原审计的具体更正

| 原表述 | 本次复核 |
| --- | --- |
| posthoc 全部收敛 | 已提交 V142/V143 分别 19/11 次校验失败；幅度低估经验尤其严重 |
| 高层问题仅是 Round canonical outcome 严格 | Plan critic 全失败，V143 6 次调用均截断；V143 Round 根本没调用 |
| Slow 全部研究性判定、无代码性失败 | 存在 candidate-case 技术失败、fixture 自相矛盾与真实 controller 输入断链 |
| V142 c01 两轮都截断，19/24 与 9/24 | r1 最终已完成 24/24并提交；19/24是中间状态。r2为缓存不可变冲突后剩9条 |
| V143 c02/c01 被评估门截断 | r1 c02第15例未finalize/budget_exhausted；r2 c01第20例解释请求预算预留95182>94594；不是统计证明效果差的提前淘汰 |
| 修复后的管线已获得公平验证；cycle2 slow起点处干净停止、workspace一致可续 | 完整学习链路仍有断点；Fast round2提交，但Slow cycle2未完成，存在in_progress外部attempt；恢复未实测 |
| 相同输入、唯一变量是代码 | 实际history/Plan/Raw Info/seed manifest变化；跨V141还改变priors |

## 8. 下一步优先级与验收边界

1. **先修丢失学习与合同误杀。** 混合 direction/magnitude 反思应明确归因轴；独立有效条目可保留；critic 分批输出或以选择低层条目为主；补全首答规则；用真实 MP 问题修 runtime guard。验收检查哪些经验被选择性丢弃，不只报纠错率。
2. **接通真实消费分支。** 必须在 multi-axis controller 最终模型请求中看见所选 brief 和原文，并追踪其引用到候选；移除 budget_skipped 等技术诊断对研究经验槽位的占用，验证筛选实际产出，检查 PIT 不可执行建议。
3. **修取证与事实承接。** 用 AXT/GPRE/ZURA 的同文档、同 span 对照检测“选中文档但关键内容不可见”“Basic可见但状态丢失”“baseline/算术/目标被重述错误”。保留 source coverage 与 model visibility 两套检查。
4. **修 Slow 生成合同与效力归因。** fixture/skill 语义一致，materialization 局部纠错，投影引用失败单列；在技术路径运行正确之后再判断研究假设是否有效。补齐 Jev exact-request 审计。
5. **最后才做研究增益实验。** 上述均可先离线复放。真实 F1 是否恢复需要另行授权的同 cohort、可比输入/预算、基线与修复版配对测试；不要用换样本候选序列代替受控对照，不降低证据/PIT/晋级门槛求分数。

本次不启动新测试调用。结论强度是：已确认若干工程/合同/证据承接缺陷和同案例预测退化，尚未量化每项的独立因果贡献；没有证据据此否定结构化、有来源、渐进披露的记忆方向，也没有证据宣称它已成功带来收益。

## 复核产物

- [指标与状态复算 JSON](jev-v143-process-and-f1-audit-20260929.json)：14 个历史最终 attempt、逐案例转移、技术/研究诊断分离、29 个关键输入 SHA256、validator 误拒复现。
- [反思、Slow 与原文证据摘录](jev-v143-content-evidence-20260929.json)：人工审计证据清单，包含原请求/记录路径；不是新的模型评测输出。
- [离线复算脚本](../scripts/audit_v142_v143.py)：`PYTHONPATH=src <bundled-python> scripts/audit_v142_v143.py --output /tmp/v143-audit.json`。不写 evolution 工作区、不发请求；检查读取前后关键输入哈希。
- 运行时源代码、历史运行状态和原始请求/响应均未修改；本次验证为离线复算与 repository lint，不宣称重新执行了完整 live 或全量模型测试。

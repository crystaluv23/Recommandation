# V130／V138 F1 回退与实际信息流审计

日期：2026-09-22。只读检查运行工件；没有调用模型、恢复运行或修改运行代码。审计代码 HEAD 为 `8b752f9`，并核对 V138 冻结 revision `b056e0c` 的生产入口。

## 1. 结论

1. V130 与 V138 round 1 是相同 24 案；F1 由 0.800 降到 0.689655。主要可定位差异是三只 V130 的 TP 在 V138 因技术纠错失败成为 FN，而非正常 Predictor 一致变得更保守。
2. V138 并未实际启用多 Plan 并行。生产 `evolution_control` 构造 PlanEvolutionEngine 时没有传 evaluator_factory 或 max_parallel_plans，后者默认 1，走串行分支。不能将此次下降归因于并发串扰，也不能把本次运行当成并行实机验收。
3. V138 不仅包含 magnitude／并行改动，还包含 same-request guard、technical exclusion carry-over、cap 提升至 6、纠错提示变化等。不是“两项修改”的受控 A/B。
4. 真实纠错请求存在具体接口矛盾：反馈建议修改／增加引用，但 required_change_paths 只授权 claim。Ciena／Wynn 的 response 改 evidence_index，被 projection 还原为原无效输出，再被 no-progress guard 终止。守卫阻止死循环是正确作用，却没有解决上游不可用的纠错路径。
5. 技术弃权与研究性 insufficient_information 共用反馈分类，已经污染 critic 的归因。Round 2 critic 把无真实研究轨迹的技术失败案例归因为 unavailable Signal 被当作负向证据。这不是可靠的研究经验。
6. V130、V138 两轮所有真实正向预测仍然全部为 `2-3x`，没有一例 `3-10x` 或 `10x+`。Round 2 macro-F1 上升不足以证明高幅度辨别能力改善；8 个 Random 案例也换了。
7. 第一轮父本内容和导入 meta 相同，Predictor system prompt 完全相同；实际 final_context 及生成 Plan 不同。无法仅凭现有运行证明 provider 模型发生了改变，或量化 magnitude 提示的独立因果贡献。

## 2. 工件与比较口径

运行根目录：

- [V130](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v130)
- [V138](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260922-v138)

| 项目 | V130 | V138 |
| --- | --- | --- |
| 冻结 revision | af5966b | b056e0c |
| Python | 3.12.14 | 3.13.13 |
| round pointer | 1 | 2 |
| cycle pointer | 0 | 1，cycle 2 slow 中断态 |
| 初始 Registry | v6 / ced38829… | 相同；cycle 1 后仍相同 |
| dataset manifest hash | 13772d03… | 相同 |
| round 1 snapshot | bf38ca13… | 完全相同 |
| round 2 snapshot | 无 | 9f4a6e4e…，保留 16 Anchor、换 8 Random |
| 单案限制／模型路由／temperature | 冻结契约记录 | 与 V130 相同 |
| 总预算 | 5800 attempts／$28.50 | 1600 attempts／$6.50 |
| Raw Info inventory hash | fc8e03e3… | 68b07ee3…，不同 |

读取全部三个已提交 Plan record，使用当前 `ExecutionTrajectory.from_dict` + `score_predictions` 离线重算，所有指标与保存值逐项相同。未发现指标算术实现导致的数值偏差。

| Plan | TP/FP/TN/FN | F1 | mag accuracy | mag macro-F1 | 技术弃权 |
| --- | --- | --- | --- | --- | --- |
| V130 r1 c01 | 12/4/6/2 | .800000 | 5/14 | .175439 | 0 |
| V138 r1 c01 | 10/5/5/4 | .689655 | 4/14 | .156863 | 5（3 正、2 负） |
| V138 r2 c02 | 8/2/8/6 | .666667 | 5/14 | .222222 | 6（3 正、3 负） |

技术弃权在当前用户批准的 carry-over 实现中是 finalized negative：真实正案计 FN，真实负案计 TN；source-evidence eligibility 对 exclusion 豁免。该行为不是本审计发现的算术错误，但其负案 TN 不能被解释为研究成功，valid_case_count=24 也不表示模型真实完成了全部研究。

## 3. 第一轮下降的逐案分解

下表仅列影响二分类混淆矩阵的变化；同一组 24 案其余方向不变。

| 案例 | V130 | V138 r1 | 原因类别 |
| --- | --- | --- | --- |
| Ciena / cik_0000936395:20250930 | TP possible | FN 技术弃权 | H_reflect correction 无进展 |
| FTAI / cik_0001590364:20250731 | TP possible | FN 技术弃权 | H_init correction 无进展 |
| cik_0001920294:20250530 | TP possible | FN 技术弃权 | H_reflect 需求转换＋数量引用验证耗尽 |
| Life Time / cik_0001869198:20250331 | TN unlikely | FP possible | 正常预测翻转 |
| Newmont / cik_0001164727:20250731 | FN unlikely | TP possible | 正常预测翻转 |

Wynn 与 Enbridge 也技术弃权，但由原 TN 变为合成 negative/TN，不改变二分类计数。

可复算的描述性分解：

- 把 V130 对 V138 五个技术弃权案例的预测替换为 V138 弃权，其余保持 V130：TP9/FP4/TN6/FN5，F1=.666667。
- 再加入两次正常预测翻转，得到 V138 实际 .689655。
- 仅在双方都正常完成的相同 19 案上，V130 F1=.750000，V138=.769231。它只用于定位退化来源，不能作为替代正式成绩，更不能剔除失败后宣布系统变好。

这说明“模型正常研究时的方向识别普遍退化”不符合第一轮证据。技术完成率是首要问题；正常模型判断另有个案漂移。

## 4. 实际纠错 prompt／response：确认的授权范围矛盾

### 4.1 Ciena：补引用被回滚

[原请求](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260922-v138/requests/c5d612e8037dfb6b86c8b4368b3c541a8045be12345e7b1748d70d0b94888991.json)

- 失败 claim 同时陈述现金 1,055,976,000 与经营现金流 435,016,000，却只引用 supporting[0]。
- validation_feedback 明示 435,016,000 在同 Signal 的 supporting[1]，建议 add exact evidence ref tuple 或收窄 claim。
- 机器授权仅 `supporting_evidence[13].claim`，没有 evidence_index 或完整引用元组。
- 实际 response 保留 claim，将 evidence_index 从 0 改为 1。
- 离线直接调用生产 `_scoped_correction_drift_paths`，结果为 `supporting_evidence[13].evidence_index`；`_project_scoped_correction` 结果与原 invalid_output 完全相同。
- failure.json 随后记录 identical correction request 被 same-request guard 终止，框架生成弃权。

注意：模型只替换引用未必足以支撑整个双数值 claim，因此不能声称“该 response 本来已完全有效”。确认的缺陷是反馈建议的引用修复路径与授权路径不一致，导致这次引用改动被无条件撤销，无法作为真实纠错进展接受后续验证。

### 4.2 Wynn：同类问题复现

[原请求](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260922-v138/requests/8119a7cd98bc613f53f553b7de7bd90b2c8d5d5b2d31aa15788983ec75573d4b.json)

- 数量反馈提示 guidance supporting[2] 的 2027，以及 financing supporting[1..3] 的多个金额／日期。
- 授权为 supporting_evidence[8].claim、[9].claim 和 current_beliefs[7]。
- response 修改 [8].evidence_index 0→2、[9].evidence_index 0→1。
- 生产函数重放认定这两个 evidence_index 越界，projection 完全还原 invalid_output。

### 4.3 其他失败不是同一个原因

- Enbridge 与 FTAI 的相应 correction 原始 response 与 invalid_output 完全相同；属于模型没有执行修复。错误主要是跨证据价格／日期和文字数量支持。
- cik_0001920294 的 failure 明确含 `next_information_needs` cosmetic narrowing 与同 claim 数量缺引用两类问题。
- 不能把全部 failure 归咎于授权范围，也不能因以上矛盾就放松 literal evidence 或允许任意整对象改写。

## 5. 并行与数据传递核对

V138 冻结 revision 的 `evolution_control.py` 在 PlanEvolutionEngine 构建时未传 `evaluator_factory`／`max_parallel_plans`。引擎默认 factory=None、parallel=1，并仅在 factory 非 None 时进入并行分支。功能存在于引擎和测试不等于生产已接线。

本次按实际模型请求进行以下核对：

| 检查 | V130 r1 | V138 r1 | V138 r2 |
| --- | --- | --- | --- |
| 正常案例 final_context 与 Predictor 请求逐项相等 | 24/24 | 19/19 | 18/18 |
| provider 原始预测与保存预测一致，扣除框架派生 is_surge | 24/24 | 19/19 | 18/18 |
| 持久 signal_round information_needs 在实际 routing payload 中找到精确匹配 | 86/86 | 67/67 | 57/57 |

三组 Predictor system prompt 的 SHA256 完全相同：`9feff8ccc6a064f6e35623406ec91b49ba0b09fe5e46bf9287eceb99f276436e`。

范围限制：routing 核对是 needs 与请求的精确存在性匹配，不是每一步 accepted ResearchState 到下一请求的全链唯一身份重放。未完成对全部 source span、所有时点和所有未提交候选的逐项语义审计；不能据此宣称所有信息流绝对无误。

第一轮 proposer 收到的父本完整内容 hash 与导入 meta hash 在两次运行间一致，父本均为 historical_seed_197c4388…；magnitude 提示的改动及随机生成使新 Plan 并不相同。Raw Info inventory 也不同，不能把差异解释为单独的模型版本变化。

## 6. 正常预测如何变化：不是统一变保守

Life Time 的原始响应表明，V130 与 V138 都知道约 31.8 的基准、13%／17% 的增长、23,000,000 股售股及 30.40 发行价。

- V130 将增长不足以支持 2x、售股压力及缺乏价格确认放在关键理由，给 unlikely。
- V138 r1 将同类增长和 momentum 放在关键理由，给 possible；同时在 uncertainties 承认增长不足以桥接 2x、融资压力与供给压力。
- V138 r2 仍为 possible，甚至将售股解释为 removed overhang，虽然 uncertainties 又承认募集资金未进入公司。

这更像证据权重与 narrative framing 漂移，不能简单归结为数据完全缺失。两次执行的 Signal 组合和上下文并不完全相同，因此尚不能独立量化模型采样与上下文变化各自贡献。

另一个正常翻转 Newmont 则从 FN 变成 TP，所以首轮没有普遍保守化证据。

## 7. 跨轮 reflection → proposer → 执行：有效传递与错误归因并存

### 7.1 反思确实进入下一轮

V138 round 2 proposer 请求包含 imported meta round -1 和本地 round 1；本地记录含幅度诊断与 critic 反思。

[r2 c02 proposer 请求](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260922-v138/requests/3665caa109d0634830bf5ba520bc9dae2c3e9aa050c8caf06e7a436969c09d1d.json)

r2 c02 的 H_reflect 新增：供给压力、内部人售股和弱流动性要作为 constraints，而非 mere uncertainties；出现反复低估时继续索取 analyst targets、backlog conversion、cash runway、dilution。与 r1 critic 中相应问题对应，说明 meta 没有简单丢失。

但是 H_analyse 与 r1 保持相同，仍要求 quantified forward bridge 才将正面催化视为 sufficient。这项要求 V130 已有，不是 magnitude 新增发明；r1 critic 已同时指出它有助避免 FP，也会造成 FN，r2 没有解决这组权衡。

共同 Anchor 中 ONDS/cik_0001646188 从 r1 possible 变成 r2 unlikely：同类订单／收入证据仍在，r2 将 Nasdaq 合规、稀释、客户集中和缺少 2x bridge 作为核心负面理由。这与新增 falsifier/constraints 方向一致，但仍是观察性链路，不是证明单句 prompt 因果作用的消融实验。

### 7.2 技术失败已被误归因为研究经验

框架为技术失败创建空 basic_info、空 final_context、无 signal_round 的 finalized insufficient_information；self_reflection 只在 plan_issues 放 technical_case_exclusion。

然而 critic 输入同时得到通用 candidate_judgment_feedback：

- 真实正案：`false_negative_information_gap`，指导识别哪些信息 absent／not acquired／not converted into Signal。
- 真实负案：`correct_negative_information_gap`、binary_correct=true。

[r2 critic 请求](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260922-v138/requests/05595c87267a74a8bc6e038ba1e901276b2d9426c70fbb575a5da86973e270f4.json)

实际 r2 critic 写出“Treating unavailable signals as neutral-to-negative … contributed to missed surges (cases 12, 15, 20, 22, 24)”。其中 12、15、24 是技术弃权，无正常预测理由和完整轨迹，不能据其合成记录得出这种研究性因果解释。

该错误反思已经进入 round 2 record/meta；由于运行停在 cycle 2 Slow，尚未见 round 3 proposer 实际消费，不能宣称它已经造成第三轮行为退化。r1 critic 能识别技术排除，说明不是每次必然误归因，但当前契约没有可靠隔离。

## 8. magnitude “改善”为什么需要重新解释

| Plan | 正向预测总数 | 预测 2–3x | 预测 3–10x | 预测 10x+ |
| --- | --- | --- | --- | --- |
| V130 r1 | 16 | 16 | 0 | 0 |
| V138 r1 | 15 | 15 | 0 | 0 |
| V138 r2 | 10 | 10 | 0 | 0 |

因此两个高幅度档位 recall 均为 0。macro-F1 提升可能来自低档命中变化和对高档案例预测负向后减少了低档 false positives；它可以在高档辨别能力没有改善的情况下上升。这是现有指标的数学性质，不是重算错误，也不是模型有意作弊的证据。

r2 全集更换了 Random，不能把 .156863→.222222 的 +41.7% 直接解释为进化因果效果。固定 Anchor 上也从 .166667→.242424 上升，但仍无人预测高档；Anchor Binary F1 同时由 .736842→.750000，而全体 F1 下降，进一步说明 Random 构成和技术失败需要单列。

cycle 1 Slow 无晋升，Registry hash 不变，magnitude_contribution=false；没有证据说明新幅度 Signal 已帮助第二轮预测。动态 learning profiles 可以变化，不应把 Registry 不变误解为所有运行上下文不变。

## 9. 对既有运行报告的修正意见

[旧报告](live-run-v138-20260922.md) 的指针／完整 cycle 里程碑成立，但以下判断过强：

- “链路无错误”：纠错修复授权矛盾和技术失败归因污染已有具体证据。
- “F1 微降在噪声内”：没有重复运行或配对不确定性估计，不能根据 24 案就作统计判断。
- “magnitude 首现改善／+41%”：数值确实上升，但不是高幅度区分能力或因果研究效果的证明。
- “V130 成功归因于 code-era/provider-side model behavior”：代码／生成 Plan／上下文均变，provider 变化没有被独立证明。

本审计保留原运行工件，不回写历史分数，也不把扣除技术失败后的子集结果替代正式指标。

## 10. 推荐后续顺序

1. **先修纠错接口一致性。** 对实际 Ciena／Wynn 请求建立回归：反馈允许的引用编辑必须有精确、最小授权路径；仍完整验证 claim、引用来源和未授权字段。模型只是切换索引但仍漏引时继续给出真实新反馈，不允许整对象自由漂移。
2. **隔离技术失败反馈。** 保持已批准正式评分暂不变，新增独立技术完成率和失败分类；critic/proposer/Slow 不把合成 negative 当真实研究观点。空技术轨迹不能支持“忽略反证”“Signal 权重错误”等归因。
3. **纠正进展报告。** 同时展示技术完成率、二分类、各幅度预测分布／recall、低估／高估、Anchor 与 Random；不只盯 macro-F1。
4. **先做零外部调用重放。** 原始 request/response 与同一 validator 下验证修复；这不能推断修复后的 Predictor 必然恢复 V130 的 TP。
5. **再做独立授权的最小对照。** 固定 Plan、样本、原始数据、Registry／learning、model 参数，分别比较纠错修复、magnitude prompt、串行／真正接线并行。不要同时改三类变量；正常完成后才比较研究质量。
6. **另行确认研究权衡。** quantified 2x bridge 是历史延续的强条件，既可减 FP 也可增 FN。对 Life Time、Newmont、ONDS 等代表案例做相同上下文下的提示消融，再决定如何修改，不由事后涨幅倒推必须乐观。

本轮只完成审计和两例生产投影函数离线重放，没有实施上述修复，也没有新的外部费用。Provider 漂移、每条源证据的时点正确性、所有失败候选的全链路语义，以及修复后的实际 F1，仍需后续针对性验证。

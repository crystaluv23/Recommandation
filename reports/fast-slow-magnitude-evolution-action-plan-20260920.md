# Fast／Slow 双目标进化行动计划：Binary F1 与 magnitude

日期：2026-09-20。证据基线：代码 `af5966b`、V130 已提交的 Fast round 1。

**状态：待确认的实施提案，不是已生效规格，也不是已完成实现。** 本文只规划后续工作；不修改现行评分、选择、Signal 晋升规则，不恢复暂停运行，不授权新的模型或数据调用。

> **2026-09-20 评审修订（已获用户批准执行）。** 评审核实第 2 节基线全部属实后，补充四项约束：
> （1）P0 回归清单必须以 campaign 记录为源头文件，并点名两个至今未修复的开放缺陷；
> （2）`candidate_judgment_feedback` 禁止原地扩展，magnitude 逐案反馈一律走旁路派生块；
> （3）`prediction_outcome.correct` 保持现行混合语义不变，二元与幅度对错以新增确定性字段并列；
> （4）P4 选择入口盘点显式包含 `evolution_benefit.py`，benefit 判定保持 Binary F1 门（F1 保护），magnitude 只作观察报告。
> 批准范围：P0–P6 离线实施与测试；P7 实机运行仍需单独的模型、数据与预算授权。

## 1. 目标与成功定义

让模型既改善“能否发现上涨机会”，也改善“上涨幅度档位判断”，同时保持 Fast／Slow 的数据边界、验证、恢复和提交机制正确。

这里的 magnitude 进化指档位预测更准确，不是预测值越来越大。真实为 `2–3x` 却预测 `10x+` 同样是错误。标签、预测窗口和价格基准维持现行定义。

最终验收必须同时覆盖三类结果：

1. **机制正确：**幅度错误从确定性评分进入逐案反思、Plan 反思、已提交 meta、下一轮 proposer，并影响明确的候选选择规则；适合转成信息因子的缺口进入 Slow，晋升结果在下一 Fast 可见。
2. **流程正确：**真实引擎完成 Fast → Slow → 下一 Fast，重启前后快照、指针、缓存、学习事件和 Registry 一致；失败不产生虚假提交或晋升。
3. **研究有效：**在事先冻结的配对评估中，幅度指标改善，Binary F1 满足预先确认的保护规则。机制走通、测试通过、单轮分数上升，都不能单独证明研究有效。

若流程正确但效果没有改善，应记录“机制完成、效果未证实”，继续用失败轨迹修正研究假设，不修改标签或挑选有利样本。

## 2. 已核实的起点

### 2.1 当前机制

| 环节 | 已实现行为 | 缺口 |
| --- | --- | --- |
| Predictor | 正向判断必须输出幅度；负向判断幅度为空 | 不能靠要求输出更大档位解决准确性问题 |
| 逐案 post-hoc | 真实上涨案例须方向和幅度都正确；模型看到预测与真实幅度 | 整体 correct 混合两类错误，没有独立的确定性幅度反馈结构 |
| Plan critic | 收到完整指标、预测、真实标签和逐案反思 | 没有强制分解幅度错误、反事实风险和验证任务 |
| Round／meta | 保存逐案、纵向 Plan、横向 Round 反思；单个有效 Plan 时跳过横向 LLM | 不应把跳过横向比较误判为丢失全部学习；幅度任务尚无稳定结构 |
| 下一轮 proposer | 消费已提交的回顾性 meta | 无需明确说明采用、拒绝或延后哪项幅度假设 |
| Plan 选择 | eligible archive 按 Binary F1 降序，再做相似度去重和随机探索 | magnitude 不影响排序；同 F1 时按 plan_id 打破平局 |
| 父子比较 | 仅完全相同快照提供二分类指标差值 | 没有显式 magnitude 差值和错分迁移 |
| Slow | 幅度判断策略可归为 fast_plan_action；可复用信息缺口走因子研发 | 有效性主要评价方向；幅度贡献未形成独立验收闭环 |

### 2.2 V130 实测

V130 的 round 1 已提交；cycle 尚未提交，active phase 为 slow_loop。不能称为已完成最新完整 Fast／Slow cycle。

已提交 Plan `plan_r0001_c01` 共 24 案，TP=12、FP=4、TN=6、FN=2：

| 指标 | 数值 |
| --- | --- |
| Binary F1 | 0.800000 |
| Precision／Recall | 0.750000／0.857143 |
| Magnitude accuracy | 5/14 = 0.357143 |
| Magnitude macro-F1 | 0.175439 |
| 正确识别上涨案例中的幅度准确率，补充诊断 | 5/12 = 0.416667 |

完整幅度分解：

| 真实类别 | 预测负向、无幅度 | 预测 2–3x | 预测 3–10x | 预测 10x+ |
| --- | --- | --- | --- | --- |
| non_surge | 6 | 4 | 0 | 0 |
| 2–3x | 2 | 5 | 0 | 0 |
| 3–10x | 0 | 5 | 0 | 0 |
| 10x+ | 0 | 2 | 0 | 0 |

模型的全部 16 个正向预测均为 `2–3x`。七个“方向正确、幅度偏低”的案例均产生了明确反思；Plan critic 已提出分离二分类与幅度校准。因此问题不是模型完全看不到 magnitude，而是学习缺少结构化检验与选择压力。

另有反思提出调整价格参照来避免低估。这属于需要审核的模型建议：固定标签基准不能改变。一个已实现的未来大涨也不能证明当时必须判断为 likely，不能据此重写四分类概率含义。

### 2.3 可复核证据

- [V130 已提交 Plan 和完整轨迹](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v130/plans/plan_r0001_c01/record.json)
- [V130 实际 Plan critic 请求](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v130/requests/6c582cd79203f0d8cdc7164e558064753bec9e0c06d4082733a30183ac07ba50.json)
- [V130 已提交 meta](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v130/meta/round-0001.json)
- [V130 round 指针](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v130/state.json)
- [V130 cycle 指针](../runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v130/cycle_state.json)
- [指标、meta 和 archive 选择实现](../src/stock_opportunity_agent/research/evolution_core.py)
- [Predictor／critic／reflector／proposer 实现](../src/stock_opportunity_agent/research/evolution_plan_roles.py)
- [Slow 有效性与晋升实现](../src/stock_opportunity_agent/research/signal_evolution.py)
- [Slow 角色与 fast_plan_action 路由](../src/stock_opportunity_agent/research/evolution_signal_roles.py)
- [Fast／Slow 联合正确性审计（P0 回归清单的源头文件）](fast-slow-joint-correctness-20260919.md)
- [Campaign 状态与逐轮独立复核记录](../.delegation/fast-slow-20260919/state.md)

## 3. 先冻结不可退化的边界

以下均为后续每个阶段的准入条件，而非最后才补的检查：

1. 预测仍先持久化，再揭示标签。回顾性幅度反馈、案例结果和学习任务不得进入 blind Predictor、执行时研究状态、Raw Info 或 Signal 证据。经匿名化的通用研究方法可以通过 Plan 进入下一轮；具体历史案例和结果不能被编码回 Plan。
2. 维持现行四分类到二分类映射、三个幅度档位、价格分母、时间窗口和 point-in-time 可用性。评估标签与预测时价格基准的一致性先审计，不以模型抱怨为理由更换分母。
3. 不改变 Anchor／Random 样本契约；缺失共享数据仍走独立恢复机制。失败、无效、不完整案例不能被剔除后重新计算“更漂亮”的成绩。
4. Combined 指标由完整案例集合重新计算，不平均分组 F1；技术性失败与研究性失败分开记录，eligible gate 不放宽。
5. 保留 outcome-aware meta 的身份清除、整条 FIFO、提交后可见性、导入历史负编号和本地正轮号规则。新增学习字段不能重写旧反思。
6. 保留 correction 的有界重试、授权字段修复、完整重验证、原始证据和失败隔离。不要通过新增大量自由文本守卫制造新的死端，也不要为了减少纠错放松证据要求。
7. 普通局部失败不消费未处理需求、不生成虚假 candidate；授权、预算、provider 暂停、共享数据暂停和用户中断继续沿控制面传播。
8. Slow 的证据、point-in-time、induction／holdout 隔离、版本绑定、paired effectiveness、provisional、原子晋升与 Registry 可见性全部保留。
9. round／cycle pointer 是完成依据；staged artifacts、缓存、日志和模型自述都不是完成标记。stats 和学习事件恢复仍需幂等。
10. Locked Test 继续封存；研究只使用批准的 evolution validation 数据。任何正式泛化结论必须另走既定 Locked Test 流程。

## 4. 先确认的研究选择

当前 [vision](../spec/vision.md) 明确要求新 Plan 通过更高 F1 替代旧 Plan；[architecture](../spec/architecture.md) 和 [scheme_evolution](../spec/src/stock_opportunity_agent/research/scheme_evolution.md) 明确规定 F1 是唯一选择 fitness。**包括 magnitude 同分优先在内的任何选择变化，都是上层契约变化。** 本文件列出提案，不覆盖现行约束。实施前须确认，然后从 vision → architecture → owning module specs 自上而下更新。

| 待确认项 | 建议起点 | 后续扩展的条件 |
| --- | --- | --- |
| 次目标 | 沿用现有 magnitude macro-F1；accuracy、分档 recall、低估／高估作诊断 | 不先引入人为加权总分 |
| 选择顺序 | eligible 后，F1 主序、magnitude macro-F1 次序、plan_id 最后保证确定性 | 需要容许 F1 下降时，另行确认容忍幅度和证据门槛 |
| F1 平局 | 用混淆计数构成的有理数比较，避免浮点舍入制造近似同分 | 不擅自采用“差 0.01 也算同分” |
| 幅度辅助指标 | 保留当前真实上涨全集口径；增加命中上涨子集的条件指标 | 条件指标只能诊断，不能单独用于选择 |
| 历史父本 | 保存旧分数与快照来源，允许统一的已确认排序读取已有幅度指标 | 不因 Registry 更新而重评旧 Plan；不声称跨快照差异是因果改善 |
| Slow 晋升 | 第一版保留全部现行门槛，增加幅度贡献观察 | 纯幅度改进通道需单独设计、确认和实测 |
| 效果判据 | 配对评估要求幅度改善、F1 不下降，明确样本量与不确定性 | 若允许非劣性区间，需要先冻结阈值、分析方法和样本预算 |

**同分优先是第一版保守方案，不是完整的多目标最优解。** 它只能在 F1 相同时提供幅度选择压力。若同分稀少，或有明显幅度进步的候选因微小 F1 损失被长期淘汰，应将此作为有证据的第二版设计输入。候选方案可为带 F1 下限的 Pareto 保留，但本计划不提前设置任意权重、下限或新父本槽位。

## 5. 按依赖顺序执行

### P0：固化基线与失败轨迹

**工作**

- 保存当前代码 revision、冻结契约、Registry、dataset snapshot、round／cycle 指针和相关工件哈希。
- 对 V130 24 案只读重算二分类与幅度指标，逐项对齐 record、meta 和实际 critic request；建立上述错分矩阵。
- 核对标签分母与 prediction_baseline 的实际生成链路；将“改基准”“从结果倒推更强信心”等反思标为待审核建议，不采纳为学习规则。
- 将已有正确性故障列入回归清单：correction 漂移／缓存死端、未解决需求丢失、meta 导入轮号碰撞、stats 缺失、学习事件重复、pause／resume 和中断路径。逐项注明已修复、仅离线验证或仍未解决。**清单生成必须以 [`reports/fast-slow-joint-correctness-20260919.md`](fast-slow-joint-correctness-20260919.md) 与 [campaign state.md](../.delegation/fast-slow-20260919/state.md) 为源头逐轮摘录，不靠回忆。** 其中两个缺陷在当前 HEAD（af5966b）仍为**未修复**，必须以开放项身份进入矩阵：
  1. **第三类缓存重放死端**：full-revert projection 加 identical revalidation 会重放完全相同的缓存请求（round28 记录明确标注 unfixed，需要通用 same-request guard）。P2／P3 恰好要在 correction 反馈结构附近加字段，这是最可能再次触发该死端的区域。
  2. **SIGINT 中途吞信号**：V127 与 V130 两次暂停均复现 SIGINT 无效、被迫 SIGTERM 硬杀。任何未来需要中途暂停的实机运行都继承此风险。
- 冻结当前测试命令和运行时路径；不把历史测试数量当作当前验证结果。

**交付**：基线审计 JSON／Markdown、固定工件引用与哈希、回归矩阵。

**验收**：重算得到 F1=0.8、幅度准确率 5/14、macro-F1≈0.1754385965；七个幅度低估与两个 FN 分开；源 workspace 不发生任何改写。

### P1：先落规格与字段契约

**工作**

- 确认第 4 节研究决策；只将确认部分写入上层和模块规格。
- 优先在现有反馈、指标、meta、proposal 审计记录中增加最少字段，不新建并行进化引擎。
- **禁止原地扩展 `candidate_judgment_feedback`。** 该字段同时受三处严格校验约束：生产函数（`evolution_core.py` `candidate_judgment_feedback()`）、`ExecutionTrajectory.from_dict` 重载时的重新推导精确相等校验、`CaseReflectionEvidence.__post_init__` 的六字段集精确匹配。magnitude 逐案反馈一律作为**旁路派生块**（如同级 `magnitude_feedback` 键）由框架从已保存 prediction／truth 计算，使旧工件的重载路径保持字节兼容；旧记录缺该块时按"可从原始预测／标签只读派生"处理。
- **`prediction_outcome.correct` 语义保持不变**：继续复制现行混合了 magnitude 的确定性 `framework_prediction_correct`（canonical 反思记录不动）；`binary_correct` 与 `magnitude_feedback` 作为并列的新增确定性诊断进入 payload，提示词必须说明三者的先后关系，避免反思模型收到互相矛盾的 correct 语义。
- 定义字段生产者、消费者、是否允许看 outcome、持久化位置、版本和缺失语义。
- 明确旧工件兼容：原始预测／标签完整时可只读派生新诊断，注明 derived 来源；只有旧自由文本时不得虚构结构化字段。legacy unknown 不等于零分，也不等于通过。
- schema／prompt／selection policy 纳入冻结契约及缓存身份；候选 Plan 无权改指标权重、排序、标签和固定 prior。
- 检查现有 token 预算，优先传递小型矩阵和引用，不能靠截掉旧反思、Signal 覆盖或必需证据来容纳新增字段。

**交付**：自上而下规格变更、字段表、兼容与契约迁移说明。

**验收**：每个字段均有对应输入、输出和读写方；无 ancestor 冲突；现行运行与新契约边界清楚。

### P2：实现确定性的 magnitude 反馈

**逐案建议结构，最终字段名以 P1 为准**

按评审修订，以下字段以同级 `magnitude_feedback` 派生块形式进入 post-hoc payload、critic 压缩轨迹与 meta 案例证据；**不写入** `candidate_judgment_feedback` 本体：

```json
{
  "binary_correct": true,
  "magnitude_applicable": true,
  "predicted_magnitude": "2-3x",
  "true_magnitude": "10x+",
  "magnitude_correct": false,
  "error_kind": "underestimate",
  "ordinal_distance": 2
}
```

- `error_kind` 至少区分 correct、underestimate、overestimate、missed_surge、not_applicable。真实 non_surge 的幅度为不适用，即使是 FP；其错误仍由二分类负责。
- FN 单列 missed_surge；其幅度仍按现行规则计入全集指标的未命中，但不能虚构预测档位或跨档距离。
- `ordinal_distance` 只在两个真实存在的档位间取差，表示档位距离，不表示收益误差；不直接进入总 fitness。
- 所有字段由框架根据已保存预测和 truth 计算，模型不得重判。

**Plan／Round 聚合**

- 保留现有 magnitude accuracy 和 macro-F1 的数值定义，macro-F1 仍按现有三个固定类别计算；另报每类 support，避免将缺类或小样本造成的数值误读为稳定能力。
- 增加完整错分矩阵、FN 数量、低估／高估计数、预测分布、真值分布、条件幅度准确率及分母。
- 条件指标的分母为 TP；TP=0 时标记 undefined，不伪造 0 或 1。全集指标继续约束漏判。
- 对同一快照的父子比较增加 magnitude 差值及逐案转移汇总；跨快照只展示原始指标和不可配对说明。
- Anchor／Random／Combined 分开报告；Combined 必须从并集重算。

**验收**：V130 重放精确复现；覆盖边界 2x／3x／10x、全部压低档、全部夸大档、全部负向、FP／FN、缺类与 TP=0；旧二分类数值和 eligibility 逐项不变。

### P3：让反思生成可检验的幅度学习任务

**逐案**

- 在现有 post-hoc 调用中传入确定性幅度反馈，明确先区分方向错误与档位错误。**`prediction_outcome.correct` 的复制规则保持指向现行混合确定性值**；`binary_correct` 与 `magnitude_feedback` 是并列诊断，提示词需说明幅度对错不改变复制结果。
- 幅度归因须分清：已有证据解释不足、需要新增的预测时可获取信息、无法根据现有证据确定。允许“不知道”，不强制模型编造上涨原因。
- 同时要求思考高估反例；真实收益只说明发生了什么，不能证明某个 Signal 当时必然应有更大权重。

**Plan／Round**

- Plan critic 接收矩阵与分母，分别归纳二分类问题、幅度问题和两者权衡；只在有多个有效 Plan 时做横向比较。
- 每项学习任务包含：缺陷类型、匿名证据引用、改进假设、拟改 Plan 部位或信息缺口、适用条件、高估／F1 回退风险、验证办法。
- 若单个有效 Plan 导致 Round LLM 跳过，仍必须保留逐案／Plan 层任务，不能依赖横向调用才生成下一轮学习输入。
- 硬校验只负责字段、引用和确定性一致性；反思是否合理依靠明确 rubric 与人工审计样本，不用复杂关键词规则伪装因果判断。

**持久化与 proposer**

- 继续使用同一条 additive FIFO；新增结构化任务不得替代原始反思。只读兼容旧记录，原始工件不可重写。
- proposer 针对有关任务记录 adopted／deferred／rejected 及理由，并将 adopted 项映射到 B／H_init／H_reflect／H_analyse 的实际差异。
- 该映射作为 proposal 审计旁路，避免无必要地扩大四字段 Plan 本体；冻结 prior 与原有 change-focus 约束仍有效。
- 不能要求每个候选都处理所有任务；无适合证据时允许延后。但如果整个候选批次忽略明显幅度缺陷，须有批次级解释。
- 预测时仅出现可泛化的研究要求，不携带历史案例标签、公司标识、真实收益或后验答案。

**验收**：真实角色序列化路径中能追踪“七次低估 → Plan 学习任务 → 已提交 meta → 下一 proposer → 实际 Plan 差异”；重启和 FIFO 淘汰不丢层、不重复；执行时 label 扫描仍通过。

### P4：加入第一版幅度选择压力

**工作**

- 在 P1 获确认后实现统一比较规则：eligibility → Binary F1 → magnitude macro-F1 → 稳定 ID；保留现有相似度去重和确定性随机探索。
- 全仓盘点并标记所有选择入口：screening／promotion shortlist、champion、archive Top-K、父本选择、historical seed ranking、停止条件、dashboard／报告、**`evolution_benefit.py` 的双臂比较（显式点名，实现者不得遗漏）**。不能只改一个 sort，让其他路径继续隐式只按 F1。benefit 判定保持 Binary F1 门作为 F1 保护，magnitude 差值只进入观察报告，不进入 gate。
- 每个入口明确“应用新策略”或“保留现行语义”的原因；historical seed 的批准 tie-break、较弱 cohort 等规则不能被一个通用排序意外覆盖。
- 不重写旧 Plan 分数，不因 Registry 变化自动重跑历史 Plan。已冻结 seed manifest 不变；新契约才使用批准后的新策略。
- 若 legacy 记录缺次指标，不填零参与比较；优先从完整已存轨迹派生，否则明确无法比较并使用已冻结的兼容处理。
- 在审计日志解释每次选择的决定因素，区分“F1 胜出”“幅度同分优先”“多样性排除”“随机探索”。

**验收**：同 F1 时幅度更好者获优先；更低 F1 不因幅度高而反超；幅度高但不 eligible 者仍被排除；全相同指标时顺序稳定；重启父本和 seed 一致。统计真实历史候选中多少次选择会改变，明确第一版选择压力的实际强度。

**升级触发**：若回放表明同分规则几乎不生效，或连续配对实验发现低幅度质量仍系统性占优，提交第二版双目标保留方案。不得把第一版的有限作用包装成已完成充分双目标优化。

### P5：将 Slow 接入幅度学习，保留晋升正确性

**第一阶段：反馈与信息供给**

- 为幅度学习任务保留跨阶段来源引用，进入既有 Slow source view／backlog，而非另建一个 Mining 回路。
- 纯分析策略、证据权重、档位校准归 fast_plan_action；对预测时可测量的新事实、归一化或适用条件的需求进入正常 Mining／Update。
- 候选因子可探索订单兑现规模、收入／利润弹性、估值变化条件、融资与稀释等可验证机制；这些只是研究方向，不能从未来涨幅反向发明定义。
- 维持真实来源、literal evidence、时点、匿名化、跨发行人检验、holdout 与完整恢复链；所有既有 promotion gate 保持。
- Slow 报告明确区分：未生成候选、候选验证失败、方向性晋升门槛未过、通过并晋升、幅度贡献尚未评估。

**第二阶段：观察最终预测贡献**

- 对通过既有门槛的少量候选，开展预先冻结的 Plan 消费实验：同一 Plan、相同案例和数据快照、相同模型设置，仅受控改变候选 Signal 的可用性／版本。
- 两个 arm 各自进行盲预测，随后一次性揭示结果；报告方向与幅度差值、逐案变化和成本，完整保留失败。
- 若改变 Signal 导致后续路由不同，报告为该干预的端到端效果；不能把它声称为单条 Signal 数值的纯直接因果效应。
- 该实验先是诊断，不改写历史 Plan，也不绕过真实晋升流程。相同输入复用缓存；不同输入不能复用旧预测冒充重测。

**明确限制**：现有 Update 严格增益判据主要是 availability／directional correct／wrong。只改善幅度而方向指标完全不变的 Signal 可能仍被拒绝。因此保留旧门槛的第一阶段不能声称完成了“纯幅度因子晋升”。

**后续决策包**：若观察实验确有纯幅度贡献，单独提出 magnitude-aware promotion：既有所有 correctness／availability／directional floors 保留，是否允许“方向不退化 + 稳健的幅度配对增益”替代原来的方向严格增益。冻结 Plan arm、评估样本、最低 support、非退化规则、重复试验和成本上限，再获得确认并修改上层规格。没有证据前不实施这个例外。

**验收**：至少用真实引擎的离线测试覆盖一次正常 candidate→验证→晋升→下一 Fast 可见，以及一次纯幅度需求仍被现行 gate 拦下的可解释结果。离线 scripted 角色仅证明流程，不证明 LLM 能产出有效因子。

### P6：跨轮恢复与系统回归

**执行顺序**：确定性单元测试 → 角色请求／解析测试 → V130 工件离线重放 → 真实引擎多轮故障注入 → 全套测试 → repository lint。

重点覆盖：

| 场景 | 必须证明 |
| --- | --- |
| 逐案标签揭示 | 新反馈只在预测保存后存在；blind 输入不出现真值 |
| 单有效候选 | 无 Round LLM 仍保留幅度任务并被下一 proposer 消费 |
| 不同快照／不同 Registry | 不生成非法 paired delta，不重评或重写历史分数 |
| 导入历史 + 本地三轮提交 | 负编号导入前缀与本地 1／2／3 不碰撞，FIFO 整条淘汰 |
| round commit 后崩溃 | stats、learning、meta 恢复幂等，下一轮学习完整 |
| Slow staged validation 中崩溃 | 不提前晋升；恢复不重复更新 Registry 或消费需求 |
| 晋升后、cycle commit 前崩溃 | transition 与 cycle pointer 协调恢复，下一 Fast 只看有效 Registry |
| malformed reflection／proposal | 有界修正和完整校验；不改动无关已正确字段 |
| magnitude 缺字段／旧版本 | 兼容语义明确，unknown 不被当作改善 |
| 预算、provider、共享数据暂停 | 保留证据并安全传播，不被包装为低质量模型输出 |
| 空 Mining／无晋升 | 合法 no-op cycle 可提交，下一轮照常学习；不伪造成功 Signal |
| 有效晋升路径 | 下一 Fast 的实际请求含新版本，旧预测和 metrics 保持不变 |

主要现有测试入口：`test_information_plan_engine.py`、`test_evolution_reflection_roles.py`、`test_evolution_routing_plan_roles.py`、`test_plan_evolution_engine.py`、`test_signal_evolution_engine.py`、`test_evolution_control.py`。实际测试类由 `rg` 检查后选择，使用项目兼容的 bundled Python 与 `PYTHONPATH=src`。

每个失败都更新累计失败轨迹：失效层、原始请求／响应、上下游影响、恢复是否一致、修复覆盖的相邻场景。不得以单点测试通过代替跨轮验收。

### P7：有限实机试验与效果验收

**先解决运行边界**

- V130 保持暂停且不可原地升级契约。仅文档 commit 也会改变 HEAD；恢复原契约必须使用其匹配 revision 的 checkout／worktree，不能默认在新 HEAD 继续。
- 新实现用新 workspace、新冻结契约和批准的继承入口；只导入允许的 committed history／seed／Registry。V130 未完成 Slow 工件不能被当作完成历史。
- 如需先完成 V130 当前 Slow，使用原 revision 和原契约单独恢复，待其真实提交后再决定继承；不与修改源码并行运行。
- 新实机运行前确认模型、数据调用范围及 attempts／费用预算。本文件不沿用旧 cap 作为新实验授权。

**分两类实验，避免把流程和效果混为一谈**

1. **流程 smoke**：真实模型至少完成 Fast₁→Slow₁→Fast₂；验证实际 wire 中幅度反馈、meta、proposal 改动和最新 Registry 的连续传递。若无 Signal 候选或晋升，完整记录，此次只验收 no-op Slow 路径；晋升路径仍由离线测试及后续合适实机案例覆盖。
2. **效果配对**：控制组为现行策略，实验组为已确认新策略；冻结模型、Registry、数据快照、候选数量及预算上限。先评估仅 Fast 改动，避免同时改变 Signal 库导致归因不清；再做完整双循环系统实验。

效果实验需预先记录：候选预算、样本列表与 support、主／次指标、失败计入规则、重复次数、停止条件和判定标准。具体数量根据 P0 的成本与可用样本决定，在看新结果前冻结，不预设未经论证的样本量或显著性阈值。

- 使用批准的 validation 池内、与开发反思案例隔离的评估面板；已经用于反思的 V130 只用于回归，不能再冒充独立泛化证据。
- 比较真实上涨全集的 magnitude macro-F1，同时报告 accuracy、二分类指标、各档 support／recall、低估／高估、预测分布、条件准确率、技术失败和成本。
- 三个档位都要有可解释的样本支持，避免只靠单一发行人的 10x+ 案例下结论；按发行人／相关日期成组分析不确定性，不能把高度相关案例当独立样本。
- 先看配对逐案变化，再看汇总；检查是否只是统一提高幅度导致低估减少、高估增加。
- 如需重复模型采样，提前冻结重试／随机设置并保留全部结果；不能反复运行只挑最好一次。相同请求的缓存命中不算独立重复。
- 第一版建议效果门槛为幅度指标改善且 F1 不下降；小样本结果只记为初步证据，稳健性不足则扩大预先批准的验证，不宣称已解决。

**验收产物**：真实执行账本、逐阶段请求引用、完整指针／Registry 证据、配对效果报告、未完成项和下一次决策。

## 6. 变更落点与提交拆分

| 建议提交 | 主要落点 | 完成边界 |
| --- | --- | --- |
| A：批准后的目标与契约 | vision、architecture、scheme_evolution、evolution_runtime、evolution_signal_roles 相关 specs | 研究规则清楚，未实现项明确标注 |
| B：确定性反馈与诊断 | evolution_core 及相应测试 | 数学、旧行为、序列化兼容通过 |
| C：反思与跨轮任务 | evolution_plan_roles、meta／workspace 相关路径 | 实际请求与持久化闭环通过 |
| D：选择策略 | archive、engine、seed 与控制层实际入口 | 所有排序调用点审计，重启确定性通过 |
| E：Slow 来源追踪与观察 | evolution_signal_roles、signal_evolution | 不放松晋升，反馈可追踪，受控实验可审计 |
| F：恢复／回归验收 | 现有测试、重放工具和 reports | 真引擎跨轮与全套测试／lint 通过 |
| G：独立授权的实机证据 | 新运行 workspace 和验收报告 | 流程与效果分别给结论 |

每个代码阶段先更新 owning spec，再写实现，再做对应测试；同步 progress。小步提交，提交只包含本阶段文件。不趁此重构无关控制器、变更数据供应商、缩减检索覆盖或清理旧实验。

## 7. 暂停、回滚与不可接受的捷径

- 若发现标签进入 blind 输入、样本被静默丢弃、固定分母被改变、pointer 越过未完成阶段、Registry 非原子更新：立即停止新实验，保留工件，先修正确性。
- 若只是幅度没有改善或 F1 退化：保留全部结果，不把研究失败包装成技术异常重试，也不提高预测档位凑指标。
- 新策略的 run 与旧策略的 run 分离；回滚通过已知代码 revision 和匹配契约的 workspace 执行，不在同一 workspace 改指标／缓存键继续跑。
- 不回退已经有效提交的 pointer 或覆盖 Registry；任何迁移都必须显式、可重放，旧工件保持原貌。
- 不取消信号证据、no-match、unavailable、literal grounding、修正和晋升守卫来换取调用数下降。
- 不用“高 magnitude accuracy”替代 F1 保护，不用 TP 子集准确率奖励只挑简单案例，不用修改基准或预测窗口改善成绩。
- 不把离线 scripted Slow、测试通过或完成某个 paid request 称为真实完成一个 evolution cycle。

## 8. 下一步建议与完成清单

建议先批准并实施 P0–P3，完成结构化幅度学习和离线闭环；同时确认 P4 的保守次目标规则。随后实施 P4–P6，再进入另行冻结预算的 P7。P5 的纯幅度晋升扩展保留为有证据后单独决策，避免一次改动过多研究语义。

- [ ] 基线与累计失败轨迹已冻结，V130 重算一致。
- [ ] 上层双目标选择契约已确认并自上而下更新。
- [ ] 幅度反馈确定性计算、分母正确、无标签泄漏。
- [ ] 逐案／Plan／Round／meta／proposer 保留独立职责，单有效 Plan 也能学习。
- [ ] 候选修改与学习任务有可核验关联，不能只输出一段漂亮反思。
- [ ] magnitude 已获得实际、可解释的选择作用；第一版作用范围有量化说明。
- [ ] Slow 区分策略与测量需求，晋升守卫未退化，纯幅度局限明确。
- [ ] 新旧工件兼容、导入历史、三轮重启、stats／learning 幂等通过。
- [ ] Fast→Slow→下一 Fast 的实际请求与提交证据完整。
- [ ] 配对效果报告包含高估风险、F1 保护、稀有档支持和不确定性。
- [ ] 全套测试和 lint 通过；代码可回滚；实机授权与本地完成状态分别记录。

本计划的完成状态只表示文件已形成。上述实施、实机运行和研究效果均需逐项验收，不能从本文件存在推断它们已经完成。

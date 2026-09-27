# 自进化多轮迭代复盘

日期：2026-09-27。审计基线：`381f32a`。本次是证据复盘和工作方法记忆更新；不修改运行代码、研究阈值、晋升规则或上层架构，不启动外部运行。

## 判断

不能从目前的失败推出“让系统学习 Information Plan 和 Signal 的方向错了”；也不能因为出现过完整 cycle、Signal 晋升或较高 F1 就断言方向已被证明。更准确的判断是：**方向有合理的可检验结构，但可靠性、持续运行的规模约束和独立效果验证没有同步成熟，开发过程又多次用局部修补和测试通过代替完整验收。**

有三层问题必须分开：

1. 工程上能否完整、可恢复地执行指定流程。
2. 学习链上反馈是否正确、是否到达并改变后续行为。
3. 研究上这种改变是否带来可复现、独立的增益。

前两层失败会遮蔽第三层，甚至制造错误的“学习经验”。跑通第一层只是允许检验第三层。当前没有足够证据宣布自主进化已能持续改善研究质量。

## 证据范围与限制

核对了当前 vision/architecture、相关模块规格、Git 历史、进度记录、多轮审计报告，以及 V138/V140/V141 的 authoritative pointers、Slow 结果和 Registry 身份；最新修复按真实冻结产物做了零网络重放。早期事件主要由当时保留的逐请求审计和修复记录复核，并非本次逐条重新运行所有历史调用。

版本短名在不同日期可能复用，必须连同完整 run path、日期、code revision 阅读。旧报告中“首次”“已完成”的表述只能按当时任务范围解释。旧报告与后续逐请求审计冲突时，保留原始工件，以后者更精确的解释为准。

当前核验对象：

| Run | round / cycle 已提交指针 | 实际能说明什么 | 不能说明什么 |
| --- | --- | --- | --- |
| `information-evolution-dual-self-evolution-20260922-v138` | 2 / 1 | Fast 两轮、一个 Fast→Slow cycle 已提交；下一轮收到前轮 meta | 生产 Plan 并行已启用、幅度改善有因果证据、系统持续增益 |
| `information-evolution-jev-dual-self-evolution-20260926-v140` | 1 / 1 | cycle 状态提交且故障有记录 | ge3 真实挖掘成功；两套 controller seed 实际构造失败 |
| `information-evolution-jev-dual-self-evolution-20260926-v141` | 1 / 1 | ge3 控制器真实执行；Jev 反馈进入后续反思；周期完成 | Signal 已晋升或贡献已证实；new validated/promoted 均为 0，Fast consumption 未评估 |

三个工作区均位于 `runs/cold_start/evolution/`，Registry 仍为 v6 / `ced38829…`。V141 冻结代码为 `628516d`；本次工作基线 `381f32a` 的修复没有被这些旧运行实机验证。

## 为什么总在下一轮发现问题

### 1. 我们把过多确定性状态维护交给了开放式生成，再逐个补守卫

模型同时承担研究推理、精确数字引用、need 身份与多重性维护、PIT 措辞、引用坐标和最小范围修改。验证端严格拒绝是必要的，但生产端不一定收到等价、可操作的合同。

- V126 的 34/34 routing 首答被拒，原因之一是正常 prompt 没有告知已经执行的 selection_reason/residual 规则。
- V127/V128 的无安全投影纠错重新产生字节相同请求，响应缓存反复给回相同错误；“允许两次 correction”并不等于有第二次真实修复机会。
- V138 反馈建议增加或修改引用，机器授权却只有 claim 字段；projection 又把模型的引用修改撤销。此后同请求守卫终止了死循环，却没有解决上游矛盾。
- V141 的 duplicate-request guard 又暴露出 transport 终止与 typed fallback 交接问题，最新修复才使两者正确组合。

这不是“只要把 prompt 再写长一点”。它要求生产者、验证器、纠错授权、确定性 fallback 使用同一套合同，并把公式、坐标、状态转换等可确定的工作放在相应确定性边界。PIT、literal evidence 和不可越权修复的底线仍须保留。

证据：[V130/V138 逐请求审计](v130-v138-prompt-flow-audit-20260922.md)、[累计状态记录](../progress/status.md)、[最新技术归因经验](../memory/experiences/technical-failure-before-quality-attribution.md)。

### 2. 多轮系统曾主要按单个阶段验收，生命周期缺陷直到走到那里才被发现

- 2026-08-24 V32/V33 已复现 Fast 需要缺失能力、Slow 又等待 Fast 成功提交的冷启动循环依赖；后来经确认加入 slow_bootstrap 才解除，说明确实发生过需要架构修正的问题。
- V109–V114 pooled evidence 的生产记录是嵌套结构，旧测试却构造不存在的平铺键；实际 decisive 恒为 0，候选不可能按 pooled 门晋升。
- V126 提交 Fast round 后，definition-only Registry 缺 `stats.json` 才触发崩溃。
- V129 随后又在 imported meta 与本地 round 1 的编号冲突处失败。
- V138 引擎具备并行实现，生产构造没有传相应 factory/参数，实际仍串行。
- V140 的 ge3 descriptor 缺 `axis_id`；测试恰好 mock 掉真实 controller 边界，旧 H/E 测试也无法覆盖生产组合。

这是开发与验收责任，不能归咎于 LLM 随机性。测试数量增长有价值，但不回答“实际入口是否把这些已测零件正确组合起来”。以后必须以真实 producer 的持久化结构驱动真实 consumer，覆盖提交、恢复和下一周期消费；不能 mock 掉正在声称已验证的连接处。

证据：[变更历史](../progress/changelog.md)、[V140 故障与测试盲点](jev-v140-test-20260926.md)、[历史 Slow 审计](slow_round_prompt_audit_20260913.md)、[累计状态记录](../progress/status.md)。

### 3. 持久化完整性与模型输入完整性混在了一起，这是实际的设计问题

完整、不可变的历史有助于审计；把保留历史原样放入每次 proposer 则有成本和上下文上限。V141 下一周期 proposal 的估算需求为 403,119 tokens，超过冻结单请求上限 256,000；重试不能改变输入大小。

这不只是忘记加截断：`architecture.md` 要求 additive FIFO 保留各案、各 Plan 和跨 Plan 反思，不以总结替换原层；`PlanMetaMemory.model_view(max_chars=48_000)` 当前直接忽略 max_chars，序列化完整保留条目。FIFO 限条目数并不等于限制每条的大小。

建议的设计方向是分别定义“完整审计存储”和“受预算约束且可追溯的模型视图”，明确重要经验如何召回、遗漏如何检测、跨轮收益如何验证。这涉及现有上层完整反思约束，必须先评审并自上而下改 spec；本次不以静默截断或删除历史来处理。单纯提预算或每次新开工作区只能延后问题，不能证明持续自进化。

证据：[V141 周期 2 上限](jev-v141-cycle1-20260926.md)、[架构](../spec/architecture.md)、[PlanMetaMemory](../src/stock_opportunity_agent/research/evolution_core.py)、[proposer](../src/stock_opportunity_agent/research/evolution_plan_roles.py)。

### 4. 技术故障曾污染研究反馈，形成学错方向的风险

V130 与 V138 r1 的同 24 案 F1 从 0.800 降到 0.689655，主要可定位变化是三个旧 TP 因纠错故障变为技术 FN。后续 critic 又将部分空研究轨迹解释成“把 unavailable 当成负向证据”，把没有发生的研究行为当成错误原因。

正式系统分数必须保留失败的代价；研究归因又不能把技术失败当成普通研究反例。两个视角必须同时报告，不能通过删掉失败样本让分数变好，也不能因为正例失败计 FN，就驱动 Signal/Plan 学习一个虚构的信息缺口。

V141 当时报告将候选未晋升概括为“全部被证据诚实拒绝”，这个表述过宽。最新冻结重放表明 `disclosed_order_value_to_revenue_ratio` 是 mixed modality，应在物化前记 `capability_gap/split_required`；这并没有证明经济假设无效，也没有证明假设有效。其他真实验证不达标的候选仍应拒绝或保留 provisional。

同样需要更正候选数量的口径：V141 的三个幅度研究提议中，只有 `material_named_order_disclosure:v1` 成为正式新 candidate；ratio 与 clinical 提议在 materialization 失败。clinical 的具体失败是 fixture `company_id` 格式，不是效果检验失败。不能把三个提议写成三个已成功物化、已接受效果检验的因子。

Jev 也有一个对照：原 shadow F1 为 0.588，核对有效指令后发现传入的 analysis_prompt 与固定 screening contract 冲突；修复任务边界后，同 21 案与历史 LLM 的二元判断完全一致，F1 为 0.800。这说明先核对实际输入合同，才能把差异归于模型能力；这组小样本仍不证明样本外增益。

证据：[V130/V138 归因审计](v130-v138-prompt-flow-audit-20260922.md)、[V141 原报告](jev-v141-cycle1-20260926.md)、[Jev 输入边界复核](jev-v139-prompt-boundary-and-fn-audit-20260923.md)、[最新冻结重放脚本](../scripts/replay_v140_v141_reliability.py)。

### 5. “有反馈”“有晋升”和“变得更好”曾被说得太接近

有反思文本不等于后续模型收到它；收到不等于采取动作；采取动作不等于产生增益。Signal 入库也不能替代 Predictor 的 absent/present 结果，更不能替代整个系统的独立对照。

已有实质进展不能抹掉：历史 V114 记录过叙事 Signal 的真实晋升，V138/V141 有 cycle 提交，V141 ge3 修复后确有真实挖掘。但最新重放中 V141 c02 的 24 案有 5 个技术排除，19 个正常方向结果；11 次幅度请求全部选 `2-3x`。流程完成、反馈可见、confidence 有分布，仍不足以证明幅度区分能力。

既有 `evolution_benefit.md` 已定义同案例四臂：baseline/candidate Plan × baseline/candidate Registry，并区分 promoted、used、benefit_confirmed。问题的一部分不是缺少设计文字，而是没有持续把这条证据链作为完成标准。不同样本、数据快照、预算或多项同步变更下的分数变化只能作诊断；小样本未检出下降也不等于证明等价或有效。

证据：[独立收益确认契约](../spec/src/stock_opportunity_agent/research/evolution_benefit.md)、[V139 同案例审计](v139-live-replay-and-slow-axis-repair-20260923.md)、[最新重放](../scripts/replay_v140_v141_reliability.py)。

### 6. 经验记录很多，但没有充分改变每次工作的准入与验收

本项目早已有“从 accumulated failure trajectory 检查全链路”的要求，也有大量具体经验。然而此后仍出现同类接口形状错配、测试绕开生产路径、跨轮状态丢失和报告过度归因。继续加一篇“要更小心”没有用。

我应承担的责任是：过去多次沿着最新报错推进，验证了局部修复就继续扩展；没有始终先说明故障属于哪一层、此前同类失败为何能再次逃过检查、什么证据才足以关闭问题。有些“链路无错误”“幅度已改善”的表述也超过了当时证据，后续审计才收回。

因此这次记忆写成可触发的工作约束与复盘问题，并挂到 GUIDE 和 meta insights；同时在助手跨会话记忆中保存入口。它是后续行为承诺，不宣称已经新增了自动化检查或修好了当前运行。

## 后续收敛顺序

以下是建议顺序，不是新增生产阈值或外部执行授权。

1. **先固定一个可比较的基线。** 固定 cohort、数据快照、模型/预算、Plan 与 Registry 身份；列明技术失败、数据缺口、正常研究失败和未知归因。停止用不同工作区的最佳分数拼接“进化曲线”。
2. **先证明一个可重复生命周期。** 从真实生产入口覆盖 proposal→研究→提交→Slow→Registry 读取→下一轮；以完整旧失败记录重放，并覆盖提交前后中断、重启、导入历史、多个周期的上下文增长。阶段可执行不等于子目标达成；允许诚实 no-candidate。
3. **对当前阻塞做架构收敛评审。** 优先解决记忆读取的规模边界，核对生产 controller 与祖先文档的迁移状态措辞；减少同一概念多处独立定义。不要通过弱化证据或晋升标准来提高跑通率，也不要在此时同步扩大模型、目标轴和分析机制。
4. **再做已有契约下的独立收益确认。** 同样本配对、必要的独立重复、Plan/Registry 消融、实际 Signal 消费证据和失败分母一起报告。确认效果前只称“可执行/已消费/局部支持”，不称“自进化有效”。
5. **最后增加复杂度。** 若工程完成率稳定，独立结果持续无增益，才有更充分理由重新评审学习目标、候选空间、数据和评价代理；不能永远归咎工程，也不能永远加 guard 回避研究有效性问题。

原有 PIT、身份/标签隔离、Locked Test、原子指针、精确版本、独立晋升门都应保留。需要收敛的是职责分配、上下文规模和验收方法。长远产品仍是有证据与验证合同的机会研究；历史标签 F1 是实验代理，不能单独证明已经改善真实 watchlist 质量。

## 本次落地

- 新增项目长期经验 [Self-evolution convergence and acceptance](../memory/experiences/self-evolution-convergence-and-acceptance.md)，包含下一次迭代必须明确的故障类型、生产连接、生命周期、反馈消费和增益证据。
- 更新 GUIDE 触发索引、meta insights、经验查阅计数、usage log 和进度记录。
- 向助手长期记忆的 ad-hoc notes 新增一份简短项目规则与入口；不改写旧 memory registry。
- 本次验证为持久产物核验、最新修复零网络重放、文档检查和 repository lint。没有新 live cycle、独立增益实验或代码修复。

验证结果：`PYTHONPATH=src <bundled-python> scripts/replay_v140_v141_reliability.py` exit 0、`network_calls=0`；两个真实纠错请求均可重新载入 typed state，混合候选保持不可物化。13 个任务文档的本地链接、查阅计数和 run 路径检查通过，`git diff --check` 与 `scripts/lint_repo.sh` PASS。本次未重跑全量代码测试；历史 1091 tests PASS 属于上一轮修复证据。

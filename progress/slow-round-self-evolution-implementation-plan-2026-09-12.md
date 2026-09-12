# Slow Round 自进化：代码修改与验收方案

状态：计划内 DeepSeek/SEC 外部调用及两轮、200 次模型尝试、400 次数据请求、5 美元上限已获明确授权。V61 在合同 `59bb2450...c908c0` 下真实提交两轮，权威指针 Fast 0 / Slow 2；20 次尝试、93 次 SEC 请求、成本 `$0.11558708000000001`，两轮 H 与独立 E 都运行且 bounded method-memory 修复使 H1 请求正常发送。Locked Test 封闭、Registry v1 不变，两轮均无候选/验证/晋级/更新，目标 `unmet`。跨轮 reflection 仍未验收：cycle 2 选中含全部五个本地 cycle-1 refs 的 13 个单元，但响应归一后遗漏五个 owner；完整覆盖只在 adapter 成功后的 engine 层检查，故没有 correction，最终 memory fail-closed 且不消费 refs。后继把全部遗漏 refs 纳入 adapter 内一次结构化 correction，engine 等集检查继续兜底。所有 744 项测试与 lint 通过；V61 保持不可变，下一次执行必须冻结新合同。P6 仍只有 manifest/ledger scaffold，尚无三条件生成和真实独立确认，方法能力未被证实提高。

目标：让 Slow 每轮主动挖掘信号，从自己过去的挖掘、验证、晋级和真实使用反馈中学习，并能在没有新 Fast round 的情况下连续运行。最终产物是质量可验证、可使用的信号库，以及有证据支持的挖掘方法经验。

本文中的字段、函数及 CLI 新名称是拟实现接口；代码定位以现有符号名为准。执行时先核对基线差异，保持用户正在进行的其他工作。

## 1. 先固定目标和验收语义

### 1.1 必须满足的设计约束

1. **每轮都挖掘。** Fast 提出的 signal need 是方向建议，可以不成立。没有新需求、H1 无假设、建议不可测，都不能跳过独立探索。
2. **反馈覆盖完整生命周期。** 包括无候选、候选验证失败、更新失败、晋级、晋级后的使用及尚无使用；不能只学习成功进入 Registry 的信号。
3. **方法经验追加，原始证据保留。** 新总结不能覆盖旧反思。旧经验被新证据质疑时，追加带引用的修正记录；不能悄悄删掉原结论或其适用条件。
4. **案例不为假设服务。** 先冻结中立样本及开发/检查边界；不能根据能否找到支持证据、结果是否有利而换公司。
5. **质量门槛不由模型修改。** 保留 PIT、literal evidence、可执行契约、版本隔离、成对效果验证及晋级边界。
6. **保持实现简单。** 复用现有 Registry、学习事件、cycle workspace、角色调用、恢复和评估设施；不引入第二套信号库、向量数据库、通用多智能体框架或模型微调。

### 1.2 “正确跑通”分开报告，不能互相替代

| 维度 | 验收含义 | 不能当作通过的情况 |
| --- | --- | --- |
| 执行完成 | cycle 正确提交，可恢复，计费/状态/Registry 一致 | 只有日志结束、staged 文件或测试通过 |
| 内容正确 | 实际 prompt、response、证据和后续动作符合接口及研究逻辑 | JSON 合法、引用存在、模型自称已学习 |
| 信号产出 | 每轮目标至少一个新的、有意义的信号；分别记录候选、合格、晋级数量 | 空跑、只提出 hypothesis、只更新旧信号、改名重复信号 |
| 方法学习有效 | 具体反馈进入方法经验并影响合适的后续行动；独立评估检验效用 | 反思字数增加、轮数增加或使用次数上涨 |

建议把 `min_new_signals_per_cycle=1` 固定进新运行合同。这里的“合格新信号”须通过可执行契约、测量语义检查、非重复性检查及现有效果门槛；仅生成 draft 不满足最终信号产出验收。单独保留 `new_candidate_count`，方便判断卡在生成还是验证。

运行结果至少同时报告 `new_candidate_count`、`new_validated_signal_count`、`new_promoted_signal_count`、`updated_signal_count`，及 `signal_goal_status=met|unmet`。Promotion 必须仍由原有边界提交，不能提前计数。通过验证却未成功晋级，是另外的运行问题，不能隐藏在合格数量里。

正式提交报告中，`signal_goal_status=met` 当且仅当本轮通过全部验证、非重复、属于新 signal ID 且实际晋级的数量达到 `min_new_signals_per_cycle`，并且 cycle pointer 已提交。旧 signal 的新版本不计入这个数量。staged 结果不代表已达成，验证通过但 transition 未完成仍属运行未完成；数量要求不授予任何绕过晋级门槛的权限。

**不能在有限预算和任意数据条件下保证每轮都有真实有效的新信号。** 实现应保证每轮实际搜索、为独立探索预留预算、对未产出作有界恢复；预算耗尽仍没有合格信号时，保存诚实结果并标记目标未达成。允许提交失败经验供下一轮学习，不把该轮称为完整验收通过，不降低门槛、不制造信号、不无限重试。

本文提出上述严格验收口径，实施时应在 spec 中明确记录；若只做到“生成一个可执行候选”，交付报告必须明确这是中间里程碑。

## 2. 当前系统的实际情况与缺口

主要代码入口：`signal_evolution.py`、`evolution_signal_roles.py`、`plan_evolution.py`、`evolution_control.py`、`signal_library.py`；均位于 `src/stock_opportunity_agent/` 对应模块中。CLI 是 `scripts/evolve_information_schemes.py`。

| 当前实现 | 结论与修改理由 |
| --- | --- |
| `_validate_cycle()` 已无条件调用 Mining，再调用 Update | 不是单纯“Fast 没需求便不挖”。问题在探索覆盖、信息反馈及产出验收 |
| H1 已看到 Fast meta/backlog、stable cards 的 learning profile、部分 `prior_slow_work` | 不能说 Slow 完全没有自身反馈；它缺少完整、持续、可归因的方法学习闭环 |
| `SignalLearningEvent` 有 exact `signal_ref`、case、选择理由、结果、真实标签及 reflection attribution | 这是反馈事实的主要基础，直接复用，避免新造一份 metric |
| `_mining_context()` 只拼最近三个 validation 的部分内容，且未统一按 committed pointer 过滤 | 丢失失败、晋级及长期后续使用；可能读到未提交工作 |
| H1 输入指纹未包含 prompt 中的 `prior_slow_work` | 新的 Slow 反馈可能被旧 no-hypothesis 缓存挡住 |
| E2 输入是 signatures/slots/契约，缺少共享方法记忆和信号库视图 | 独立探索未真正继承 Slow 学到的方法，也不利于避免重复 |
| E 默认按周期触发，H 的部分空结果会 fallback，部分 rejected/refine 路径会结束 | 不能保证每轮都有独立于 Fast 建议的探索机会 |
| H2 有行业、规模、关键词等筛选及固定顺序截断；后续又按证据匹配替换 induction/recompute holdout | 可能让样本向容易支持假设、容易取到证据的公司偏移 |
| E 基础小样本是固定排序；Update 先选错/对/中性案例再分 induction/holdout | 周期变化不等于中立新样本；更新诊断可能影响检查集构成 |
| H1 的 `update_existing` disposition 不直接进入 Update target 调度 | “建议了更新”不等于“后续执行了更新” |
| validator 检查 fixture 可执行性，语义重复主要是规范化文本比较 | 描述说测 A、实现实际测 B 仍可能逃过当前测试；改名也不构成新能力 |
| `slow_bootstrap` 只允许一次特殊 Slow | 不能拿它循环复用来声称支持独立长期 Slow |

当前测试中存在一个测量语义盲点：`tests/test_signal_evolution_engine.py` 的 scripted success 案例把“segment breadth”的描述与 total revenue growth 函数组合。这说明测试没有独立验证“实现是否真的测量了声称的概念”，不意味着已证明同样错误发生在所有真实候选上。

历史审计边界也应保留：V45 的真实 Slow 已提交，但 H1 语义失败；其 E2 insufficient-evidence 经原文比较是合理结论。V47 只是经过检查的零调用冻结边界，不是新一轮成功运行。旧轮次曾出现零正确的 Update 因相对少错而晋级，后续绝对质量门槛已修复；不能把旧晋级作为当前有效库或自进化成功的证据。

## 3. 目标数据流：在每轮入口学习一次

```text
已提交 Fast 使用事件、原始 reflection       已提交 Slow 全部实验及验证结果
                 \                         /
                  冻结本轮 slow_input + 样本清单
                               |
                 有新增事实时：一次有界方法反思
                 原始事实 + 具体反思 + 新增方法经验
                               |
                形成有来源闭包的 learning_context
                     /         |         \
              H1/H3 定向挖掘   E2 独立探索   Update
                     \         |         /
                 先完成开发，再冻结候选版本与 hash
                               |
                固定检查样本执行、验证、Registry 晋级
                               |
               提交 cycle、追加实验事实；下一轮再学习
```

第一版只在**轮入口**设一个逻辑 reflection job。输入来自过去已提交事实，本轮搜索和晋级结果下一轮再进入反馈。“待处理新事实”包含本轮新增及历史尚未成功处理的 pending；二者都为空时零反思调用。不在每个阶段都加反思 Agent。

当前轮中断时，只恢复相同已冻结输入及已完成角色产物；不重新反思、不更换样本、不把未完成轮次算入下一轮历史。一次逻辑 job 的 correction 请求仍逐次计入真实 provider 调用和预算。

## 4. 反馈来源、版本归因和事实语义

### 4.1 直接复用三个来源

| 来源 | 复用位置 | Slow 应学到什么 |
| --- | --- | --- |
| 信号后续实际使用 | `SignalRegistry.load_learning_events()`、`load_learning_profile()`、`SignalLearningEvent` | 当时为何检索/使用、能否执行、在哪些上下文有用或误导、多少独立观察支持结论 |
| 自己的实验经历 | committed `SlowLoopValidation`、`SlowLoopResult`、候选 validation 和新增 experiment lineage | 什么方向可测、什么失败属于数据/实现/假设、哪种修正实际奏效 |
| Fast 原始需求及反思 | 已提交 Plan/round 的原始 reflection、meta-memory/backlog | 下游实际缺什么，signal 的使用是否符合它的定位；建议可以被证据否定 |

`SignalStats` 的检索次数、执行次数、可用性、成本可以辅助，但不能替代逐条事件和去重后的样本分母。现有 profile 已处理跨 Plan 重复 observation 和互相矛盾的观察；沿用这些语义。

### 4.2 必须保持的区别

- 以 **exact signal version** 关联使用记录；同 ID 的 v1/v2 不能混成一个学习样本。晋级前的 proposal 用独立 work id，晋级后再接 exact `signal_ref`。
- 不把未入库候选塞入 `SignalLearningEvent`。它表达实际 Plan 对合法 Signal 的使用，不表达所有搜索尝试。
- `event_id` 统计使用事件，`observation_key` 统计独立观察。不能把跨 Plan 重复执行当成更多独立市场证据。
- 增量由事件及来源身份计算，不只拿两份累计 metric 相减；历史冲突的隔离可能让有效样本数下降。
- “未使用”“数据不足”“技术错误”“方向判断失败”分别记录；新信号未被使用不等于坏信号。
- 标明反馈属于历史回放还是真实后续使用，时间窗口是否成熟、标签何时可知；未成熟结果保留 pending，不能算负样本。
- 使用后的正确率只是观察关联。`reflection_attribution` 是模型诊断，不能伪装成 Signal 对最终预测的因果贡献。
- 所有 profile 和方法经验都保留分母、适用范围、缺失及矛盾证据。不能把少量成功概括成“某类信号总是有效”。

反馈面向方法的问题应是：“之前为什么选择这个测量？在什么证据条件下成功？失败发生在哪一层？下一次具体应如何改变测量、来源检索或适用范围？”不能只输出信号排行榜。

## 5. 追加式 Slow memory：避免灾难性复写

### 5.1 三层内容同时存在

| 层 | 保存内容 | 写入规则 |
| --- | --- | --- |
| 原始事实/episode | 完整 feedback source、原始请求响应、证据段、结果、版本和样本分母 | runtime 保存并校验 hash，LLM 无权重写 |
| 具体实验反思 | 针对某次 work 的失败原因、支持/反对证据、修正建议和未解决问题 | 每次追加，引用精确 source；保留原文 |
| 跨实验方法经验 | 可执行 guidance、适用条件、反例、局限、所依赖的具体反思 | 每次追加；不能替代前两层 |

这是对现有 Meta-memory 追加思路的延伸。永久存储追加，与 prompt 使用有界窗口是两个概念；不能因为窗口只展示一部分就删除旧历史。也不能每轮要求模型“输出更新后的完整 memory”。

新方法经验至少含：`lesson_id`、`guidance`、`applicable_scope`、`support_refs`、`counterevidence_refs`、`limitations`、可选 `qualifies_refs`/`challenges_refs`。ID 由 runtime 分配；引用必须在当前可见来源中解析。

同一次反思响应可以产出具体反思和方法经验：请求由 runtime 为已选 work 预分配 `episode_ref` 与新增 lesson slots，模型引用这些 ID，不能自造全局 ID。允许 unused slots，不强迫填满。runtime 先验证 episode 的完整 source coverage，再验证 lesson 引用图，一次封存；`processed_feedback_refs` 由实际成功覆盖的完整事实集合派生，不能只因为某个 ref 在 payload 出现过就算处理。

新发现推翻旧结论时，追加“L9 challenges L2，证据为 X/Y，适用范围改为 Z”。旧 L2 和它的原始证据保留。派生的读取视图把两者及争议一起展示；不能只因“较新”就视为真，也不自动把旧条目改成被删除。

不用 LLM 维护累计 helpful/harmful 次数、版本号、confidence 分数或消费进度。这些若需要展示，应由真实事件推导；模型仅给出有来源的解释和建议。

### 5.2 新增三份 cycle 级 artifact

复用现有 `experiments/cycles/cycle-NNNN/`，不建立新的全局可变 memory 数据库。

**`slow_input.json`：本轮输入事实与来源快照。**

```text
schema_version, cycle_id, contract_hash, registry_hash
source_cutoff: committed_fast_round, committed_slow_cycle
source_manifest: exact ref + content hash + visibility scope
feedback_rows: typed facts + subject_ref + exact source_refs + limitations
sampling_manifest: seed, population_hash, eligibility, dev/check case ids,
                   issuer groups, selection order, exclusions, initial snapshot refs
previous_memory_head, previous_memory_hash
feedback_hash
```

`feedback_rows.kind` 使用有限类型：`signal_usage`、`candidate_result`、`search_result`、`technical_failure`。保留每类自己的事实字段，避免万能大 schema。来源 manifest 保存完整增量，模型实际看到哪些内容另有投影 manifest。

**`slow_memory.json`：本轮新增记忆条目，不是重写的全量 memory。**

```text
schema_version, cycle_id, input_hash, parent_memory_hash
reflection_work_hash, status: appended | no_new_lesson | reused | failed
processed_feedback_refs, pending_feedback_refs
episode_reflections[]: source refs + concrete reflection + unresolved questions
lesson_additions[]: guidance + scope + evidence/qualification/challenge refs
model_view_manifest: included refs/hashes + deferred refs/reasons + coverage counts
usage_ref, failure_ref
```

没有新追加事实且没有可处理的历史 pending 时，写一个 `reused` 的来源连接，历史 memory 不复制、不改写。不能让预算遗漏的 pending 因之后没有新 Fast 数据而永远失去处理机会。模型看过新事实但确实没有新经验时允许 `no_new_lesson`；不能强迫每轮凑固定条数。

`processed_feedback_refs` 只包含实际进入完整输入并被成功处理的事实。预算省略、失败及尚未读取的证据保留 pending，不能按最新 cycle id 一口气推进消费水位。`failed` 不推进相关事实的消费进度；可继续用上一份有效经验搜索，但本轮学习状态必须报告不完整。

有界 correction 在封存最终 delta 前完成，每次请求/失败写不可变 attempt。若中断发生在封存前，恢复相同 job 及剩余预算；一旦本轮 `slow_memory.json` 封存为 `failed`，该文件不再改成成功。本轮沿用旧有效经验，未处理事实留到下一轮；不会为了重试而覆盖失败原文。

**`slow_experiments.json`：本轮全部搜索与候选经历的封存清单。**

```text
schema_version, cycle_id, input_hash, memory_hash
attempts[]:
  work_id, stage, proposal_hash, parent_signal_ref
  need_refs, lesson_refs, action_summary
  outcome, candidate_ref, candidate_hash
  evidence_or_evaluation_refs, failure_ref, usage_ref
```

没有候选的 work 也必须存在。涵盖 H1 无假设、H3 refine/rejected/inconclusive、E1 失败、E2 无模式、Update defer/no-change、fixture/语义/effectiveness rejection，以及通过验证。Promotion 的真实结果仍由 `SlowLoopResult` 记录，不能在实验阶段提前宣称晋级。

工作进行中按稳定 work id 写不可变 attempt artifact；一个状态变化追加一个事件，不能覆盖此前失败和 correction。封存时生成 `slow_experiments.json` 索引及 hash。沿用现有 invocation 记录，不重复复制大 payload。

依赖顺序固定为 `input → memory → experiments → validation → result`；引用方向不得形成 hash 环。初始 input 冻结样本身份及当时资料快照；随后为原 case 补取的开发证据写入新 attempt artifact，候选冻结后的 check corpus 写入独立不可变 manifest，再由 experiments/validation 绑定。两者都不回写 `slow_input.json`。

### 5.3 prompt 的构建规则：保留具体性，不无限塞历史

1. 系统协议、学习资料、当前任务分别成段。学习资料是可能出错的数据，不可修改固定 PIT、label visibility、预算、验证和晋级规则。
2. 默认读取近期完整 episode，并按当前 exact signal/version、来源问题、已有 lesson 引用拉取相关旧记录。第一版用已有文件和结构化引用解析即可，不引入向量检索。
3. 展示一个方法经验时，同时加载其相关原始具体反思和支持/反对证据。摘要可以帮助定位，不能成为唯一事实来源。
4. 沿用当前 Meta-memory 对保留条目展示完整内容的原则。超预算按完整 episode/工作单元分批，记录 available/included/deferred 数量和 refs；不做字符串截断，不让 LLM把整库“压成 300 字”后替代原文。
5. 相关经验及其证据闭包仍超预算时，缩小本次处理的工作单元；必要时明确 context-budget failure。不能移除关键支持/反例后还声称应用了该经验。
6. 提供小而有界的引用读取能力，可请求当前许可范围内的确切 episode/source refs；返回经过原有身份和时间边界处理的原文，记录 read refs。没有读过的来源不能被模型宣称为行动依据。
7. 来源定位符是 runtime 管理的 opaque refs，模型不能通过它读取隐藏 check/confirmation/Locked Test 数据或本地任意文件。
8. 输出 `lesson_refs` 只是来源声明。必须同时保存候选的具体定义/实现变化、实际执行及验证证据；不能把“引用了 L3”当成自进化发生的充分条件。

实现共享 `read_slow_sources(refs, role_scope, budget)`，由现有角色 adapter/engine 调用。允许入口 reflection、H1、H3、E2、Update 请求补读；第一版每个逻辑 job 最多一轮补读。模型返回 typed `read_source_refs` 请求后，runtime 校验来源范围与完整条目预算，把返回原文及 manifest 加入下一次实际请求，再要求最终角色输出；补读不能开启无限工具循环。超过一次或完整材料仍放不下时，明确延期/资料不足。补读增加的 provider 请求纳入已冻结角色与全局预算；结构 correction 继续受原有独立上限约束。E1/executor 不获得此读取入口。

3000 字原始反思与 300 字新总结可以并存；前者的内容和 hash 不变。下一轮相关角色须仍能读到其中关键具体条件。新总结若只有“加强验证、注意风险”等泛泛建议，不能替代这段反思，也不能据此报告方法学习有效。

## 6. H/E/Update 的职责与调用修改

### 6.1 每轮给独立探索真实预算

新合同取消“只有每第三轮才主动 E”的主调度语义。每轮安排至少一个有预算的 E1/E2 独立探索批次；H 路径根据当前有意义的方向运行，Update 与新挖掘分别计算产出。

仍复用现有 H1→H2→H3 和 E1→E2。第一版默认最多一个 H 批次和一个 E 批次，保留现有候选数、microbatch 和 correction 上限；不另造无限搜索器。预算在轮入口预留，不能 H1 为解释全部历史 backlog 耗尽预算后让 E2 没机会运行。

H 的无假设、refine/rejected 或开发阶段候选契约失败都不取消 E。开发阶段可以在原预算内修正测量或补齐同一 case 的必要资料。检查阶段结果不回流本轮生成器；不能看完 check 错例后重写候选再测同一 check。

数据基础设施失败或额度不足，应在产物里指出未实际完成的探索阶段；“调过 Mining 函数”不等于成功完成一次探索。

### 6.2 H1：提出可检验方向，减少机械账务负担

- H1 输入：Fast 方向建议、原始相关反思、共享 Slow learning context、stable signal cards/profiles、可用测量能力和预算。
- 允许 `need_refs=[]` 的自主假设；Fast need 不成立可以明确拒绝或搁置，不为满足账务强造测量。
- 全量需求保存在 runtime backlog 中。模型本次只负责所选择工作集的精确引用和 disposition；未选择的条目由 runtime 保持 pending，不要求 LLM 每轮重新解释 175 个需求。
- 不允许某个 broad signal_ref 自动覆盖许多异质需求。沿用 per-need 证据及更新依据校验，但作用于实际选中的工作集。
- `update_existing` 进入 Update 的方向队列，和既有 profile-based targets 合并去重，仍须满足现有 exact-version 可行动依据及重复反馈条件，受原 top-N/预算约束。H1 建议不能独自越过 Update 触发门槛。未调度的建议保留 deferred，不能因为 H1 写了这行就算已执行。
- `fast_plan_action` 保持 Fast 策略建议的边界，不当作挖掘新 signal 的产出。

### 6.3 E1/E2：中立提取、记忆辅助比较

- E1 只做当前开发 case 的 PIT 证据提取；不接触 outcome-aware memory、跨 case 标签或“希望证明的结论”。保留 source-owned 概念、期间、单位及原文证据。
- E2 可以读取开发案例标签、E1 literal signatures、相同的 Slow learning context，以及现有信号目录/可执行能力。它应比较能测量的重复模式及反例，不猜测未提供的行业/业务事实。
- 技术提取失败独立保留；有证据 sibling 可继续，但原样本中缺失的 case 仍出现在分母和缺失记录里，不能静默换成其他公司。
- `insufficient_evidence` 是合法研究结论，必须有具体比较依据；本轮若没有其他合格新信号，产出目标仍未达成。
- 保留 E2 的显式 candidate slots、标签说明、schema 和 source ownership，减少纠错时将原有候选意图抹掉的风险。

### 6.4 H3 和 Update：用同一事实闭环

H3 接受 H1 的明确测量目标、已冻结开发样本、相关方法经验及限定范围的证据；不能拿 sibling hypothesis 的资料伪装成自己已验证。

Update 接受 exact version 的原始使用记录、profile、方法经验及 H1 更新建议，说明改什么、依据是什么。错/对案例诊断只能来自开发集，不能先看全部标签再挑 holdout。

继续保护 stable fixtures 和更新路径；不为让 Update 成功而删掉失败测试、改写旧 fixture 或更换旧版本语义。需要改变既有 signal 的测量定义时，明确新版本/新信号边界，遵守现有 spec，而非用同名换概念。

## 7. H2 和所有路径统一使用中立样本

### 7.1 先冻结 population 与开发/检查分割

在 H1/E2/Update 看到本轮案例结果前，由 runtime 构建同一份 `sampling_manifest`：

1. 从现有 Discovery split 获取候选总体；保留当前身份隔离、PIT、发行人分组及标签定义。
2. eligibility 只检查事先定义的研究总体、prediction time、必要基本数据条件。不能使用后验收益、能否匹配 hypothesis query、是否容易得到正证据等排序条件。
3. 为控制开销，按稳定 hash 随机排序：种子来自冻结 base seed、dataset/scope/protocol 和 cycle id。不能来自候选文字、模型自选 ID、效果结果或运行时随机状态。
4. 先按 issuer 抽样，再在发行人的合法时点中按不依赖 outcome 的规则选 case。需要延续当前正/负样本平衡时，再做明确标记的分层抽样；不能总挑每家公司涨幅最大的时点。
5. 开发与检查按 issuer 分离，case IDs、顺序、比例、排除原因和初始资料快照一次冻结；resume 只恢复，不重抽。开发补证保存在新的不可变 artifact；全部候选 hash 冻结后，再按两臂声明的输入需求、在不看 check 标签/结果的情况下准备和封存共同 check corpus，最后执行检查。

类平衡沿用当前研究评估设置，不把这种样本的命中率解释成真实部署的总体命中率。当前数值门槛保持不变；样本量不足时报告 incomplete/provisional，不能自动降低最低样本量。

### 7.2 对 applicability 的处理

默认在 broad eligible population 中探索。测量确实只对某类业务有定义时，可声明必要的适用范围，但必须在看该候选的检查结果前固定，并记录理由。

第一版不要让 H1 自由组合市值、上市年龄、关键词、交易所、source-richness 条件来缩小成功范围。保留基础资格检查；行业范围若是预先明确的研究域或测量必要条件，使用 source-backed 定义并在该域内随机抽样。

开发阶段发现测量只适用于更窄领域时，可以提出下一轮的领域假设，或者对本轮冻结样本如实输出 out-of-scope/unavailable。不能删除反例后重新定义本轮成功率。论文式“只挑这些公司才能成立”的 scope 不获验证通过。

### 7.3 修改所有隐性重选路径

- H2 删除按业务叙述“更像正例”的排序和固定列表优先截断，改用 manifest 的随机顺序。
- H2/H3 不再按 query 是否命中、证据是否好看替换 induction issuer，不重算有利的 holdout。
- E 的基础抽样也使用 manifest；仅打乱同一批固定公司不算新的中立样本。
- E1 grounded filtering 不改变原 cohort；失败/缺失作为该 case 的状态保留。
- Update 可以在 dev 中选错/对例做诊断，但所有更新候选使用冻结 check；不根据诊断结果决定哪些公司留下检查。
- `SignalCandidateEffectivenessEvaluator._select_cases()` 增加严格 manifest 模式，不进行 preferred cases 后自动补样；缺失检查输入就是缺失。
- baseline 和 candidate 对同一 check、同一冻结 corpus、同一标签执行。identity/hash 必须绑定 manifest、candidate、执行配置和资料内容。

资料不足时只能为**原 case**做有界补取，遵守原 as-of 与资料版本。check 补取由 evaluator 在执行任何一臂前，按冻结的 baseline/candidate 输入需求并集统一准备并封存，两臂共同使用；不能据执行结果选择是否补取。检查开始后缺失保持缺失，或按原共享数据恢复协议恢复同一冻结工作，不能静默换 corpus 重测。共享数据不可用继续走原 `SharedEvaluationDataUnavailable` 控制面，不当作候选差。

### 7.4 防止跨轮慢性污染

本轮 check 不对本轮作者开放；其提交后反馈可以在下一轮参与开发学习。因此这些样本属于持续发展的 Discovery 评估，不能永久宣称是未见过的独立 holdout。

权限必须由统一 source resolver 依本轮 scope 执行，不能只在 prompt 里写禁令。历史 episode、旧反思或 lesson 的来源闭包若包含当前 check 的 issuer/case，也应将相关完整工作单元从本轮作者 context 延期，防止从旧 source 侧门读取检查信息。此前已经向生成器暴露过的发行人不能通过本轮遮蔽被“洗成未见”：manifest 记录 `previously_exposed` 并在报告中只称开发检查；需要未见案例的验收只能从曝光集合之外选择，数量不足报告 incomplete。无论是否历史曝光，本轮冻结候选后都不允许依据 check 反馈修改并重测。

为检验“学会挖掘”的泛化能力，复用 `evolution_benefit.py` 的独立 confirmation 协议，保留从未给 Slow 的发行人及案例；confirmation 的原始标签、案例级错误或可还原信息不回流学习。Locked Test 保持原边界。

现有 `ConfirmationCohortLedger.reserve()` 主要按 case id 排除复用，需要补充 issuer-level 跨时点排除，并核对历史开发曝光来源。旧 ledger 缺少 issuer 信息时，从可验证的原 protocol 重建；无法重建则报告历史隔离未知，不能把未知当干净。不要清空旧 reservations 来获取“新”样本。

## 8. 信号验证必须检查“测量了什么”

继续复用当前 contract fixtures 和 paired effectiveness gate，增加独立测量语义验收，不靠模型自编 fixture 自证正确。

1. **定义到实现一致。** spec 所称概念、输入字段、期间/单位、方向解释，应与确定性函数或 skill 实际读取和计算一致。描述测 segment breadth 却实现 revenue growth，必须失败。
2. **独立证据测试。** 对候选声明的能力，使用独立于候选作者的测试证据/核对过程。至少覆盖支持、反对、资料不足；其中一个例子应能区分目标概念和常见替代概念。
3. **泛化而非公司特判。** 测试使用语义等价但不同命名、顺序、单位/期间表达的输入，以及关键事实改变的对照；执行器不能靠 ticker 或测试文本模式输出。
4. **非重复性。** 先用现有结构和执行定义比较找明显重复，再审查同一功能的改名/改写；语义模型只能提供有证据的诊断，不能用一句“创新”替代验证。第一版不建相似度平台。
5. **效果门槛不放宽。** 保留 availability/decisive 和绝对正确性门槛，Update 同时满足相对不退化及改进要求。通过描述审核不等于方向有效。

不能纯靠 schema 自动证明语义，也不需要把每个可能概念写成 hard-coded validator。确定性不变量由代码检查；开放语义由独立模型审阅、针对性测量测试及人工校准的验收 rubric 共同检查。具体审阅请求、输入、证据、结论都要落盘，预算进入合同。

语义 reviewer 位于**开发阶段**，只读取候选定义/实现及被许可的开发证据，输出 `pass|reject|inconclusive`、来源引用和具体不一致项。独立测量 fixtures 单独保存为 evaluation artifact，依据声明的测量概念和源证据确定 expected state，先冻结再执行；不修改 stable fixtures，不用候选实际输出倒推正确答案。reviewer/fixture 作者不能读取当前 check 或 confirmation 作为创作材料。开发阶段允许有界修正，再审核变化部分；全部通过后才冻结最终 candidate hash 并进入 check。`inconclusive` 不算合格，人工校准在离线进行，不要求 slow_only 每轮等待人工批准。

同一数据上的独立 reviewer 不是独立统计样本。它只能增加内容可信度，不能替代冻结效果检查与独立 confirmation。

## 9. 独立运行模式与恢复协议

### 9.1 增加 `slow_only`，保留单次 bootstrap 的原义

当前 `slow_bootstrap` 是打破初始化依赖的一次性特例。新 `slow_only` 必须作为显式合同模式写入上层 architecture；不通过循环重置 bootstrap 标记绕过限制。

拟新增运行合同字段：`cycle_mode=slow_only`、正整数有限的 `max_slow_cycles`、`slow_history_manifest_hash`、`min_new_signals_per_cycle`，以及 reflection/独立语义验收所需角色预算。Fast 轮数使用现有字段 `limits.plan_rounds_per_signal_cycle=0`，不并行新增一个含义相同的字段。

`max_slow_cycles` 是整个新 workspace 的累计上限，在 `EvolutionWorkspace.start_or_resume_cycle()` 创建下一轮前校验。CLI 的 `--max-cycles` 只是单次 invocation 的进一步限制，反复 resume 不能绕过合同累计上限。复用已有累计 external attempts/cost 上限及单请求/阶段 token 限制；当前没有可直接声称复用的全运行累计 token/墙钟上限，第一版不为本任务另造预算系统。

第一版做有限多轮，不做无人值守永远运行。现有单一 executor、锁及 Ctrl+C 恢复继续生效；不另写第二套 engine。

### 9.2 历史导入以 committed source 为准

为 CLI 增加 `--cycle-mode slow_only` 和 `--slow-history-from PATH`。第一版只支持一个来源 workspace，避免多源合并平台。

复用 Fast bootstrap manifest 的构建模式，增加 `build/validate/apply_slow_history_manifest`：

- 冻结来源 workspace 的 committed Fast round、Slow cycle、所需 Registry exact versions、原始学习记录、候选及方法经验来源 hash。
- 只复制或不可变引用 pointer 可达的历史，不将 rejected/staged/未完成轮次导入为已完成经验。
- 新 workspace 的 Fast pointer 保持 0；导入记录保留 source namespace，不能伪装成新 workspace 已跑 Fast。
- 初始 Registry 从该 manifest 的确切已提交版本构建，不能假定当前默认 seed catalog 与来源相同。
- 验证初始 seed hash 与冻结历史一致；第二轮以后允许 Registry 合法演进，不能继续要求 current Registry 等于初始 seed。
- 不需要新的 Fast round 才能继续：上一轮 Slow 的完整结果足以形成新的反馈；新真实使用出现时再加入事实增量。

### 9.3 提交和恢复顺序

```text
恢复/创建 frozen input
→ 恢复/追加本轮 memory delta
→ 执行/恢复开发与候选实验
→ 冻结候选并运行检查
→ 封存 experiments + stage validation
→ 原有 Registry transition
→ stage result
→ 验证所有 refs/hashes 后推进 last_completed_cycle
```

`SlowLoopValidation`、`SlowLoopResult` 绑定 input/memory/experiments hashes。`EvolutionWorkspace.stage_slow_validation()`、`stage_slow_result()`、`complete_cycle()` 及 run-loop 的 staged-result 快捷路径都要验证同一链，不能只验证新建路径。

已 stage validation 的 resume 不重新反思或搜索；已晋级但 pointer 未提交的恢复不重复晋级。未提交 memory 只允许当前 active cycle 恢复读取，不能被下轮 glob 当作已学经验。

## 10. LLM 协议、缓存与纠错的具体要求

- 将固定协议、可用 schema、示例、错误反馈保持同一版本；优先共享定义/构建函数，避免再出现 system v6、payload v5 的分裂。
- H1/E2/Update 的 work identity 至少绑定实际使用的 feedback/memory view、exact signal versions、样本/资料 manifest、角色协议、模型身份及相关配置。H1 的 `prior_slow_work` 指纹缺口直接修复。
- reflection identity 基于本次从新增及历史 pending 中实际选取的完整事实/source view refs 与 hashes、上一 memory hash、协议和模型，不以 cycle id 变化强制制造“新学习”。同一批全量事实中的不同 pending 工作单元不能误命中同一缓存。技术重放不增加事实；reflection 自身的错误日志仅进入运行审计，不作为新的研究经验触发自我反思循环。
- 保留稳定 prompt 前缀、把动态资料独立成段以便可用时命中 provider cache；正确性依赖本地语义指纹，不能依赖 provider 是否缓存。
- 结构输出和引用检查失败走现有有界 correction。反馈给出字段位置、允许值及真实 source difference；只允许修正受影响字段和明确耦合字段，保留其他有效内容。
- 不把技术 failure 强制修成 `no_signal`/`unavailable`，不把 malformed update 默认当成成功的 no-change。
- 取消同一批积累数据每轮重复全量复写的提示。少量规范示例覆盖一般规律，不再为每个具体公司/词语/历史错误堆专用规则。
- 保存实际 transmitted messages、逻辑 payload、wire/body hash、context projection manifest 及响应。验收以真实输入为准，不能只检查构造函数的理想值。
- H1/E2/Update 同源但不是权限相同：可见材料按角色投影。E1、SignalExecutor 和盲 Predictor 不读取 outcome-aware 方法记忆；执行 skill 必须只依赖当时可知的资料。

## 11. 按依赖顺序交付的代码修改批次

每批先更新对应 spec，再实现，再测试。新增的跨模块边界及 `slow_only` 先写 `spec/architecture.md`，不得留一个与运行行为冲突的旧 bootstrap 约束。本文是提案，实施授权覆盖哪些设计以用户后续的明确实施指令为准。

| 批次 | 文件与符号 | 具体交付 | 本批验证 |
| --- | --- | --- | --- |
| P0 合同与设计 | `spec/architecture.md`；`spec/src/stock_opportunity_agent/research/{signal_evolution,evolution_signal_roles,plan_evolution,evolution_control,evolution_runtime,evolution_settings,evolution_benefit}.md`；`spec/src/stock_opportunity_agent/signal_library.md` | 写清追加式记忆、样本权限、产出目标、独立模式及版本迁移；不改变原标签/数值评分定义 | 祖先/模块无冲突，字段及调用角色一致 |
| P1 事实与持久化 | `signal_library.py` 现有 event/profile；`signal_evolution.py` 新增少量 feedback/memory 验证纯函数；`plan_evolution.py:EvolutionWorkspace` | 新增 input/memory/experiments artifacts 与精确 lineage，committed-only 读取，源事实去重 | 版本归因、失败覆盖、追加不覆盖、hash/恢复测试 |
| P2 中立样本 | `signal_evolution.py` 的 H2、E 抽样、Update buckets、`_select_mining_cases()`、effectiveness `_select_cases()` | 共用 frozen manifest，去掉 query/evidence 结果驱动换样，dev/check 先分后诊断 | seed/restart 可复现、issuer 隔离、缺失不换样、两臂相同 corpus |
| P3 入口方法学习 | `SignalMiningModel`、`LLMSignalMiningModel`；`evolution_signal_roles.py`；`evolution_settings.py` | 增加 `reflect_feedback()`、角色 `signal_mining_reflect` 和共享 `read_slow_sources()` 有界补读；输出只追加，完整来源闭包和失败语义 | 无待处理事实零调用、失败不消费、长反思不丢、反例引用有效 |
| P4 搜索和应用闭环 | `SignalEvolutionEngine.run_cycle()`、`_mining_context()`、`_run_signal_mining()`、H1/H3/E2/Update payload、`_stage_mining_decisions()` | 每轮 E 预算；H1 建议与 Update 真实调度；共享 memory；完整 attempts；修复指纹 | 空 Fast 仍挖、H 失败 E 继续、后续角色实际收到记忆、输出分类正确 |
| P5 独立模式与迁移 | `evolution_control.py`、`signal_evolution.py:DualLoopEvolutionEngine`、`plan_evolution.py:EvolutionWorkspace.start_or_resume_cycle()`、`scripts/evolve_information_schemes.py`、`scripts/run_information_plan_evolution.sh` | slow_only、历史 manifest、累计有限多轮、所有恢复 shortcut 校验 | 0 Fast 连续多 Slow、历史未提交不导入、第二轮 Registry 演进合法 |
| P6 语义及独立验收 | candidate validator/evaluator；`evolution_benefit.py` 与相关 tests | 开发阶段测量一致性审核、独立 fixture、冻结 memory ablation manifest/配对 reservation、issuer-level confirmation 防污染 | 拒绝伪测量和重复；发现无效/有害 memory；不泄漏 confirmation |
| P7 运行审计 | 既有 CLI、trajectory/dashboard/report 接口、progress | 展示学习输入/输出/使用和信号产出状态，冻结新运行并分层验收 | exact wire 审计、真实运行、跨轮学习证据和库的可使用性 |

路径表中的花括号仅用于列举文件，实际实施不要新建一个大一统模块。`evolution_settings.py` 当前是常量模块，不要为本任务引入配置框架。

同步修改 CLI 的 `_committed_no_candidate_diagnosis()` 和 supervisor 展示：当前它会因存在任意 `updated_candidates` 中断无候选统计，新逻辑须分别统计新候选缺失及 `signal_goal_status=unmet` 的连续轮次，Update draft 或失败更新不能重置新信号目标未达成的计数。保留原有有界停滞处理，并先遵守累计 cycle/attempt/cost 硬上限；目标 unmet 可以提交研究结果，不意味着同一轮无限重试。增加 CLI regression 覆盖连续只有 Update draft、全部被拒以及重新启动仍受累计上限约束。

建议新合同统一升级至 `evolution-run-contract-v8`；H1 从 v6 升级为新协议，reflection 使用独立版本。所有 parser、序列化、work key、payload、audit 和脚本版本检查同步更新。cycle state 若只增加可识别 mode 可保留兼容形状；若更改必填字段则显式升版，不给新版关键字段填空默认值冒充有效。

旧 v7 workspace、V47 等冻结证据只读保留，不能原地改合同然后 resume。新协议创建新的 workspace，并通过受验证的 manifest 继承已提交历史。旧活跃采样/账务实现若与新语义矛盾，应删除或限制为只读历史解析，不保留两套可同时运行的语义。

## 12. 测试与审计矩阵

### 12.1 确定性测试：系统不变量

优先扩展现有 `tests/test_signal_evolution_engine.py`、`tests/test_plan_evolution_engine.py`、`tests/test_evolution_control.py`、`tests/test_evolution_benefit.py` 及现有 Signal Library/角色测试，不照抄实现写无意义断言。

| 测试组 | 必须证明 |
| --- | --- |
| 主动挖掘 | 空 Fast backlog、H1 no-hypothesis、不可测建议、H3 rejected，仍完成有界 E；仅 Update 成功不能算新信号目标达成 |
| 生命周期 | 无候选、fixture/effectiveness 拒绝、晋级后零使用、晋级后新增使用全部可回溯到原 work |
| usage 归因 | 同 observation 跨 Plan 不重复计有效样本；v1 不污染 v2；冲突隔离、pending outcome 和技术错误语义正确 |
| 追加式记忆 | 多轮后所有旧原始反思 byte/hash 不变；短新总结不覆盖长旧文；challenge 保留双方和证据；同响应新引用图可验证；封存 failed 不被复写 |
| context 完整性 | source closure、完整条目边界和省略 manifest 一致；被省略事实不被标为 consumed；没有新 Fast 数据仍会处理历史 pending；旧资料引用不能绕过当前 check guard |
| 缓存 | 新 Slow 事实/lesson 使相关 H1/E2/Update key 改变；相同事实重放不会产生重复反思或重复 lesson |
| 权限 | 未知 refs、跨 hypothesis 证据冒用、check/confirmation source 读取和 outcome-aware context 进入 E1/executor 均被拒绝 |
| 抽样 | 固定 seed/hash 重启不变；输入排序变化不改变抽样；随机 seed 变化可覆盖总体；同 issuer 不跨 dev/check |
| 缺失与对照 | query miss/技术失败不换公司；Update 诊断不改变 check；baseline/candidate 同样本同资料 |
| 测量契约 | 声称 A 却计算 B 的 fixture 被拒绝；改名同功能不算新信号；缺资料不能凭空输出方向 |
| 恢复 | 在 input、memory、experiment、validation、promotion、pointer 前后注入故障；不重复反思、计数、晋级，不读未提交历史 |
| 独立模式 | slow_only 连续至少两轮、Fast pointer 始终 0，第二轮确实读到第一轮 committed 结果；bootstrap 单次约束仍正确；resume 不能绕过累计 cycle 上限，Update draft 不伪装新信号产出 |
| 历史迁移 | 原始来源/version/hash 保留；陈旧协议不可伪装新执行；原 seed 与演进 Registry 分开验证 |

### 12.2 LLM 语义验收：不靠固定措辞过关

构建少量成对的真实或经过匿名化的审计任务，保存模型请求、响应、原文证据及人工核对 rubric：

1. **长文具体性保留。** 原反思约 3000 字，含关键测量条件和反例；模型下一轮只写 300 字总结。验证原文保留且后续 action 正确使用关键条件。将关键段放在开头/中间/结尾，检查位置稳健性。
2. **有辨别力的反馈。** 输入结构相同，一组失败因期间不可比较，另一组因方向假设被反例否定。下一步应分别改测量来源或放弃/修正假设，不能都回答“加强验证”。
3. **等义与反事实。** 改命名、顺序、等义表达不应改变核心行动；改变关键事实应改变相关判断；删掉必要证据应承认不能判断。
4. **纠错不遗忘。** 新证据挑战旧 lesson，后续角色需说明适用范围变化并引用两边资料；不能全盘删除旧例，也不能机械坚持旧结论。
5. **诚实独立探索。** Fast 建议无效时仍能提出其他可测量方向；数据确实不支持时允许失败目标，不将 no-pattern 编造成新 signal。
6. **端到端使用。** 上轮候选→合格版本→后续具体使用→本轮反馈→具体方法反思→下轮不同的候选行动，全链需有 exact refs 和真实内容。

自动 grader 要以来源和可观察行为为依据，用人工校准的正反样本检查自身可靠性。不能以是否出现“reflection”“lesson_id”或固定句式判断学会了；不要求不同模型生成同一段文字。

### 12.3 方法能力有没有提高：单独做消融

复用现有 evolution benefit 流程，至少比较：相同 Fast/Registry 起点与预算下，无 Slow 方法记忆、只保留原始 episodes、episodes 加追加式方法经验。需要多次运行或配对样本才能描述波动；不能以一次输出比较断言提升。

现有 benefit evaluator 的四臂是 Plan/Registry 组合，不能直接当成上述三种生成策略。新增一个小型冻结 ablation manifest，记录三个生成条件、共享起点/种子/预算、生成后 exact Registry hashes，以及允许的配对比较；仍由既有 evaluator 评估每个配对的 Plan/Registry 组合，不另造评分体系。确认协议与 ledger 为这个已冻结的比较组预留一次样本，绑定完整比较清单及 manifest hash；只允许组内预声明的配对使用该样本，禁止把这个机制变成任意新协议复用旧案例的豁免。生成策略与候选必须在任何组内确认结果揭示前冻结。

冻结候选生成和审阅预算、开发数据访问边界、模型配置、能力指标与独立确认样本。比较合格新信号产出、独立执行/效果质量、重复与无效候选、资料不可用率，以及成本；不要只统计总候选数。

模型方法经验可能有害。“完整原始 episodes”表现优于“加方法总结”时，应保留事实、通过显式版本变更回退有害读取策略并追加审计记录，不能为了证明自进化而修改评估或丢掉这个结果。确认结果只进入独立审计，不返还案例级内容给 Slow；若开发者据汇总结果调整策略，新策略需用新协议及未使用的确认样本验证，不能在原确认集反复挑选赢家。

独立 confirmation 的最小样本、效应门槛、重复次数及显著性协议使用现有显式协议流程，不自行虚构数值。先冻结并取得研究协议确认，再消耗独立样本；样本不够应报告证据不足。上述具体数值不阻塞 P1–P5 的正确实现，但阻止宣称“元能力已被证实提高”。

## 13. 实施及实际运行的完成清单

1. **本地实现完成：** spec/代码同步、focused/full tests 和 lint 通过；全部不变量及 scripted 多轮闭环通过。此时只能称 local-ready。
2. **请求内容正确：** 冻结全新合同，在发送前审计角色实际 payload、所有反馈/反思原文、投影、hash、权限和预算。修代码或协议后重新冻结，不修改旧审计证据。
3. **真实 Slow 正确运行：** 运行后检查完整 H1/H3/E1/E2/Update/新增反思与语义审阅的请求响应；验证 source、candidate、Registry、committed pointer 和成本一致。
4. **跨轮反馈发生：** 至少连续两轮 slow_only，第二轮确实读取第一轮的新实验结果并形成有依据的具体行动。没有变化时需给出具体证据，而非强迫不同输出。
5. **信号库产出达标：** 逐轮报告新候选、合格、晋级、更新数量及失败原因；任何一轮没有实际提交晋级的合格新信号，不能宣布满足“每轮产出”的验收要求。晋级信号在下一次真实 Signal retrieval/apply 路径可见且可执行。
6. **方法效用有证据：** 独立、预算相同的消融/确认报告支持结论；两轮运行只是反馈链验收，不是长期泛化能力证明。

实际运行涉及新的外部模型请求、费用和数据发送。本文只交付代码修改方案，不执行或代替这些授权。执行者先完成可本地完成的实现、测试和具体冻结请求；若当前会话未授权该外部内容与预算，再在最终发送边界申请具体授权。旧 V47 授权或历史文档中的宽泛说明不自动覆盖新协议。

实施时命令应按当前环境校验；本机可用的 Python 与测试入口为：

```sh
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests
bash scripts/lint_repo.sh
```

先运行修改模块的 focused tests，再运行全套；具体 unittest class 先从当前文件发现，不抄过时测试名。提交前检查 diff、仅 stage 当前任务文件、更新 progress/status/changelog，创建 git checkpoint。报告实际运行过的测试，不复制历史“716 tests pass”当成新验证。

## 14. 近期 LLM 研究如何落到本方案

这些资料支持设计动机，不保证在本项目自动获得提升；具体取舍是针对当前代码和审计证据的工程判断。

- **ACE（ICLR 2026，2026-03 修订）**讨论反复摘要的 brevity bias 与 context collapse，提出增量积累上下文经验。本方案采用带证据的追加条目及派生视图，避免整库重写；不照搬其完整框架或 benchmark 结论。[论文](https://arxiv.org/abs/2510.04618)
- **Useful Memories Become Faulty When Continuously Updated by LLMs（2026-08 修订预印本）**报告其测试中记忆 consolidation 可退化，而保留 raw episodes 的对照有竞争力。因此本方案让原始 episodes 成为一等事实，反思有新事实才触发，并把 episodes-only 作为消融基线。该研究不是对所有模型/任务的定律。[论文](https://arxiv.org/abs/2605.12978)
- **Anthropic 的 context engineering 实践**强调有限注意力、按需获取上下文以及少量清楚的工具/典型示例。本方案据此采用引用读取、完整工作单元的有界输入、清晰角色权限；不把“减少上下文”解释成可以丢原始具体反思。[工程文章](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- **Anthropic 的 agent evals 实践（2026-01）**强调检查实际结果、轨迹及组合式评估。本方案把执行不变量、语义内容审阅、实际产出和独立方法消融分开，避免模型自评代替外部证据。[工程文章](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

优先实现的关键手段是：追加式事实与方法记忆、来源闭包、角色权限隔离、语义输入指纹、有界结构纠错、中立冻结样本、独立语义测试及消融。先把这些做好，无需为了“前沿”增加复杂代理拓扑。

## 15. 可直接交给执行 Codex 的任务文本

> 请按 `progress/slow-round-self-evolution-implementation-plan-2026-09-12.md` 实施 Slow Round 自进化改造。先阅读当前 AGENTS、vision/architecture、相关模块 spec，并核对相对方案基线的现有修改。按 P0–P7 依赖顺序推进：先更新上层和模块 spec，再实现反馈事实及追加式 memory、中立样本、轮入口方法反思、每轮独立探索、H/E/Update 信息流、slow_only 与持久化恢复，最后完成语义测试及独立验收设施。
>
> 原始事件、具体反思和历史经验只能追加，不能让 LLM 重写整库或用摘要替代源材料。后续角色必须能读取相关具体反思和原始支持/反例。复用现有 SignalLearningEvent/profile、Registry 和 workspace，不构建额外平台。Fast need 是方向建议；每轮必须真实挖掘，以至少一个合格新信号为产出目标，未达成要诚实报告；不得靠放宽验证、改名重复、补选有利公司或反复试同一检查集满足目标。
>
> 严格区分执行成功、内容正确、信号产出和方法能力提升。覆盖 exact version 使用归因、no-candidate/失败经历、memory 丢失及矛盾、实际 wire payload、缓存失效、样本隔离与各阶段故障恢复；至少用 scripted 模型跑通连续两轮无 Fast 的闭环，再完成 focused/full tests 与 lint。新增函数和接口写 docstring，移除与新协议冲突的旧活跃逻辑，避免 corner-case 特判。
>
> 完成本地改造和具体可审阅运行材料后，再按当前会话授权决定是否执行外部模型调用；本任务文本本身不授予新的付费发送权限。独立确认涉及的研究阈值按现有协议明确确认，不能默定或污染留出样本。不要原地改写 V47 或其他冻结 workspace。更新 progress、仅提交本任务变更并创建 checkpoint，交付代码/测试/真实运行/独立能力证据各自的完成状态及剩余限制。

# Status

2026-09-23：完成 [Jev V139 输入边界与 FN 复核](../reports/jev-v139-prompt-boundary-and-fn-audit-20260923.md)。21 个 Jev evidence context 与历史 LLM user payload 逐对象一一相等，case/label 映射及 42 个诊断请求 hash 均正确；确认首轮 F1=0.588 的主要原因是把上游 `analysis_prompt` 当作 Jev state 传入，其中“不要预测／要求量化 2x bridge”与历史 LLM 的 4,046 字符固定 screening system contract 冲突。保留旧 state 只移除 magnitude 的方向探针仍偏保守（F1=0.500）；移除 instruction-bearing 字段、补齐固定 screening contract 后，Jev 与历史 LLM 21/21 二元选择完全一致，双方 TP/FP/TN/FN=`10/3/6/2`、F1=0.800。代码与 shadow 共用修正后的 builder；confidence 明确定义为分布集中度而非正确率。另确认 case_020 混入 Aris Water 对 Aris Mining 的 issuer 污染、case_008 泄露 Ciena 身份；剔除后仍保持 Jev/LLM 完全一致。修正后只余 case_011／021 两个共同 FN；其反思可产生 momentum extension 与 financing 双面拆解候选，但无 ex-post 因果证据，须跨案或 held-out 验证后才能晋升。Signal 路由旧结果仍因 `context_only` 过宽而饱和，不接受替换。两组各 21 次真实 Jev 探针合计 $0.01417668、0 retry；未调用新的 chat LLM reflection，生产默认路径与 fitness 未切换。

2026-09-23（已被上一条方向复核更正）：完成 [Jev V139 冻结历史 shadow 与增量价值分析](../reports/jev-v139-live-shadow-analysis-20260923.md)。冻结 V139 `plan_r0001_c01` 的 24 案历史输入，只真实调用 Jev：21 个非空最终上下文做方向判断，80 个历史路由轮做 992 个卡片选择；标签在 101 个响应全部持久化后才进入评分。首轮发现方向与幅度同问会产生正向／`not_applicable` 无效组合，现已按规范和代码改成先方向、仅对 5 个正向案例条件调用三档幅度；补测 5/5 一次成功，合计 106 次 scored requests、$0.038851596。原始输入契约下 Jev 方向 F1=0.588、precision=1.0、recall=0.417；该方向对比因 instruction boundary 缺陷不再用于模型质量结论。条件幅度 5 案全部选 2–3x、仅 1 案正确且 confidence 0.90–0.98，不接受。Signal 路由 88.5% 卡片判为可用、77/80 轮触顶 4 张，未证明替代价值；反事实 Signals 未执行，二级排序价值仍待独立实验。生产默认路径与 fitness 均未切换。

2026-09-23（阶段记录）：完成 Jev 平行决策路径的首个离线版本。Signal 选择与 Blind Predictor 的 `candidate_judgment`／幅度类别由 OpenRouter Decisions API 的 `typesafe/jev-1.13` 适配器负责，原有 LLM 只生成标签揭示前的理由与不确定性，并在标签揭示后继续反思。每个选择均持久化 provider、解析后的模型快照、response/question id、全量概率与 confidence；预测反馈计算真实方向和真实幅度所获概率，路由反馈保留所有卡片（含 `no_match` 和上限裁剪项），进入紧凑 Plan 反思上下文但不改变现有 fitness。零网络录制重放验证选择、预测、持久化顺序和反思接线，报告见 [Jev parallel offline replay](../reports/jev-parallel-offline-replay-20260923.json)。该阶段未执行真实 OpenRouter 调用，后续冻结案例 shadow 的结果见上一条状态。

2026-09-23：完成 [V139 零调用实机重放与 Slow 双轴生产修复](../reports/v139-live-replay-and-slow-axis-repair-20260923.md)。V139 指针为 round/cycle `1/1`，两条 Fast Plan 有真实在途重叠；最佳 Plan F1=`0.740741`，相对同 24 案 V130 的 `0.800000` 差 `-0.059259`，配对 bootstrap 95% 区间 `[-0.269231, 0.131868]`、McNemar p=`1.0`，未检出统计显著下降但样本不足以证明等价。审计确认历史 Slow 只跑 `surge_direction`，2–3x 与 >=3x 未被独立对比，且两次 narrative 探索声明没有 raw span read。生产现于 cycle 启动构建 ge3 分组/发行人隔离平衡样本，并列运行方向与 magnitude 轨道；axis/标签贯穿 prompt、候选、验证、缓存、审计与结果，magnitude 候选仅 target-supported provisional，等待 Fast absent/present 与 F1 保护；raw narrative read 成为探索硬条件。暂停事件传入 worker case 边界，恢复会把遗留 `in_progress` 原子结算为保守计费的 `interrupted`。零调用重放还验证 ge3 dev 16/16、check 8/8 且 issuer-disjoint；新 revision 实机 Slow 与候选消费实验仍是剩余效果门。

2026-09-22：完成 [V130／V138 prompt／context／response 与 F1 回退审计](../reports/v130-v138-prompt-flow-audit-20260922.md)。三个 committed record 指标离线重算一致；V138 r1 同 24 案的主要退化是三个原 TP 技术弃权为 FN。生产入口未传 evaluator_factory／max_parallel_plans，实际未启用并行。Ciena／Wynn 实际 correction 引用索引编辑与 claim-only 授权冲突，生产 projection 函数重放确认退回原 invalid_output；r2 critic 将部分技术弃权误归因为研究信息不足。全部正向预测仍为 2–3x，r2 Random 换样，macro-F1 上升不证明高幅度辨别能力改善。已为旧运行报告追加更正说明；本次仅审计文档，无运行代码修改、外部调用或恢复。

2026-09-21（方案评审修订）：[Signal magnitude／Fast 并行行动方案](../reports/signal-magnitude-and-fast-parallel-action-plan-20260921.md) 已加入目标数据准入硬门（ge3 待门控，ge10／extremes 延后且不铺专属代码）、Discovery 与 validation 支持量区分、signal_library 及实际调用点的目标统计／去重改动面。缺陷 #11 必须先于 in-flight 去重验收，#12 必须先于并发度 2 验收；补齐采集 JSONL ledger、slot 升序、单进程有界线程及主线程取消协议。允许 A0 与 B0/B1 盘点交错推进。仅修订文档，数值研究门槛、规范性契约变更和实机授权仍按方案逐项确认。

2026-09-21：新增 [Signal 幅度进化与 Fast Plan 并行执行行动方案](../reports/signal-magnitude-and-fast-parallel-action-plan-20260921.md)，基于 `9f85f46` 核查，承接已实现的幅度反馈／F1 同分幅度次序／Slow 诊断接线。方案分开规划幅度分层挖掘与目标适配晋升、Plan 级有界并发与预算／缓存／恢复协调，附 C0–C8 实施顺序、故障矩阵、实机效果判据及回滚。仅文档提案，未修改运行代码、现行规格或启动外部调用；研究和接口决策须确认后更新 owning specs，实机另行冻结授权预算。

2026-09-20：新增 [Fast／Slow magnitude 双目标进化行动计划](../reports/fast-slow-magnitude-evolution-action-plan-20260920.md)。只读核验 V130 round 1 已提交、cycle 0／active slow_loop；24 案 F1=0.8、magnitude accuracy=5/14、macro-F1≈0.17544，七案方向正确但幅度低估。计划涵盖确定性反馈、反思与 proposer 跨轮任务、待确认的 F1 主序／幅度次序、Slow 信息供给与纯幅度晋升限制、恢复回归和配对实机验收。当前为非规范性提案，尚未修改上层单一 F1 契约、运行代码或执行新调用；研究规则须确认后自上而下更新规格。此次文档 checkpoint 会改变 HEAD，恢复 V130 仍须使用其原契约匹配 revision。

2026-09-20（round-29/30）**fast round 收尾：meta 单调性修复 + 摩擦优化（不弱化守卫）**：
V129 完成整条 fast 链路（c02 全部 24/24 finalized、F1=0.733、round1 持久提交、
stats 修复实机验证通过）后死于 `PlanMetaMemory.append`——导入 slow-history 的
meta 条目（round_id=1）与本地首轮冲突；结构性缺陷：任何带导入历史的 successor
首次提交必撞（V117 是唯一无导入的已提交 fast run）。round-29（20d7f73）：导入条目
在两个构建点重定基到保留负数区间（仅内存、永不清真持久化、严格低于本地轮号），
合并逻辑改为"导入前缀+本地条目"（empty-pointer 守卫仅属 slow_bootstrap）；
RoundMetaEntry 允许保留负区间；在 V129 真实持久状态上离线验证（[-1,1] 构造、
append 2 通过）。round-30（2e1b7c3）摩擦优化：V129 wire 分类显示 signal 数量义务
39 例中 31 例为模型自算派生值（比率/月均/阈值）、8 例漏引、裸年份已有 prompt 规则；
反事实排除 interpretation-grounding 方案（interpretation 中本无这些数字）后：
H_reflect prompt 增加"claim 数字只可复制、禁止引用计算值"规则；漏引类 correction
反馈新增 `quantity_location_hints`（指名同 signal 内包含该数字的 evidence item），
接受语义零变化。953 tests/lint PASS。闭环状态：stats 修复已实机验证、drift 重试
修复已实机触发、meta 修复完成跨轮离线重放验证（真实 PlanEvolutionEngine 驱动
3 轮提交-重启循环：重定基导入前缀 [-1] 与本地轮 1/2/3 无冲突、每轮 proposer
可见全部前轮反思（-1 → (-1,1) → (-1,1,2)）、stats 懒初始化与学习事件跨轮累积、
FIFO 淘汰先逐出导入前缀、真实 LLM proposer 的 proposal_context.meta_info 正确
序列化保留负 id）；实机走通仍受预算限制（re-freeze 不重写合约，全新运行需
~720 attempts，仅余 53）。

2026-09-20（round-28）**drift 重试缓存重放死端修复（V127/V128 三例共同死因）**：V127
恢复后以纯缓存重放续跑（已完成 case 全部免外部调用），c02 至 case 17 时死于
correction 死端；V128（种子仍为 V126 获胜方案的变异）c01/c02 分别死于 case 4/case 3
的 H_init correction 死端。三例 wire 证据收敛到同一机制：模型 correction 大改未授权
路径（hypotheses、多个 needs、resolved_questions 等）→ `_project_scoped_correction`
无安全投影 → 旧代码"保留原 invalid 对象与义务重试"重构出**字节级相同**的
correction 请求 → 确定性响应缓存重放同一被拒答案 → "2 次 correction"预算中的第二次
形同虚设 → `CandidateExecutionRejected`。守卫本身的定性经逐条核验均为真阳性
（V127：改 need 未采纳对应 signal 证据、claim 引用 evidence_index 0 却声称 index 1
的数值与派生比率；V128 c01：need 缺显式截断子句而同 case 其余 5 条均合规；
budget_exhausted 为 token 边界设计行为）。泛化修复：no-projection drift 分支的重试
请求在 `validation_error` 中附加 drift 诊断（未授权改动路径+保持原文指令），使重试
请求与首次 correction 字节不同——模型获得真实的第二次机会，而义务与授权路径完全
不变（反洗钱语义保持，重试仍漂移即拒）。新增回归测试断言重试差异化+义务不变，
同步修订既有 byte-identity 断言；spec（evolution_output_validation.md）补记该
stall-defect 修复。另确认种子池为动态发现（V126 提交后其获胜方案自动成为热启动
种子）、committed-fast bootstrap 无生产 CLI 路径、SIGINT 阻塞调用中不被响应——
均记录为后续项。951 tests/lint PASS。

2026-09-20（round-27）**V126 post-commit 崩溃修复（stats.json 懒初始化）与 routing
prompt 守卫教育**：V126 live run 首次跑通 c01 全部 24/24 case finalized 并持久提交
round 1（`state.json.last_completed_round=1`），c02 因单 case `budget_exhausted` 被
设计内质量门拒绝；随后在 `round_commit_started` 之后的 `_record_signal_statistics`
→`record_observation`→`load_stats` 以 `required JSON artifact is missing:
signals/financial/cash_reserves/stats.json` 崩溃（exit validation_error）。根因是
successor 工作区物化（`apply_slow_history_manifest`）按定义只复制 manifest/spec/
tests/skill（有意排除 stats.json/learning/.transitions），而 `load_stats` 是该类读取
中唯一严格读文件者——自 V117 以来没有任何 run 走到过 post-commit，属从未被执行的
路径。泛化修复：`load_stats` 在 stats.json 缺失时返回空 `SignalStats`（与
`register_stable`/`install_catalog` 初始化语义一致），任一物化/克隆路径产生的
definition-files-only 注册表都能安全记录首条观测；`PlanEvolutionEngine.__init__`
的归档幂等补录保证崩溃后恢复不丢 round 统计（离线用 V126 真实归档复现：218 观测/
205 学习事件落盘，二次重放 0 新增）。spec（signal_library.md）补记 stats.json 为
可变运行时聚合、缺失即空、不入身份哈希。附带修复（V126 实测 34/34 首答被拒的主因）：
routing system prompt 此前对 `selection_reason` 只有长度约束，从不告知
"只描述已答 facet、不得与 residual_need 共享特征短语/多个 residual-only 词"
守卫规则，导致 signal_retrieval_cards 每次首答必违规、全部走一轮 correction；
现按 spec 边界精确补入该一句规则（共享研究主题仍允许），scheme_evolution.md 同步
修订 "normal routing prompts do not pay for it" 为"一阶规则入正常 prompt、诊断
机制仍 correction-only"。回归测试新增 definition-only 注册表记录观测用例；
950 tests / lint PASS。

2026-09-20（round-26）**V125 Fast proposal 否定式归属说明误拒修复（局部否定感知）**：
`_validate_proposed_request_scope` 原先对 B.requests 的 description/query 与
H_init/H_reflect/H_analyse 技能字段做裸词形命中，把明确否定第一方归属的
target-company-scoped third-party news 请求（"not as / never as the issuer's
own disclosure"、"do not treat ... as"、"must not be described as"）误判为
`source_ownership_not_guaranteed`，V125 三对 proposal/correction（attempts
1/2、3/4、5/6）全烧在假拒绝上。现改为共享的 occurrence-aware 规则
（`_scope_match_is_locally_negated`/`_has_affirmative_scope_match`）：仅当
not/never cue 与短语同子句、在有界窗口内、且经 "as ..."（或裸限定词）连接时
才豁免该次出现；not only/just/merely/simply 不作 cue；同字段混合否定+肯定、
早子句无关否定、not only...but also 对比、任何肯定出现仍拒。相邻 cross-issuer
授权同样改为肯定出现制——被否定的第一方短语不再给无界 competitor 请求假授权，
肯定式 target-company-scoped news mentioning competitors 照常通过；
first-party-capable source 豁免、market backbone、PIT、角色边界不变。另修复
首跑发现的既有缺陷：工作区 `_FIRST_PARTY_OWNERSHIP_REQUEST_SCOPE` 缺外层右括号
（模块无法 import，re.error），按相邻 `_TARGET_ISSUER_REQUEST_SCOPE` 的平衡
结构修复。spec 增补守卫不变量；新增 6 条聚焦回归。round-26/replay.py 载入
v125 wire attempts 1-6，从 runs/cold_start/.../v125/requests/<hash>.json 找到
原始请求，按解码对象验证 messages[-1].content 与审计 payload 等值，用原始
available_source_types 复放 `_validate_proposed_request_scope` +
`_validate_plan_for_proposer_context`：六次尝试全部通过 request scope 与完整
proposer 上下文校验（无其他真实问题残留；change-focus 因 wire 无 parents 未
复放、未驱动 LLMInformationPlanProposer 的 prompt/adapter 外壳——已注明局限）。
949 测试（943+6）+ lint + replay 全过 exit 0（仅本地验证；按本轮 brief 不
commit、无生产调用；生产待 Codex 独立评审）。V125 该三对假拒绝不可计为正常
质量拒绝；Fast+Slow 主目标仍待完成。

2026-09-20（round-24）**等价有界预测语言修复：V124 c01 两处时间词法误拒**：
`_EXPLICIT_AS_OF_BOUND`/`_SYMBOLIC_AS_OF_BOUND` 增加等价且更严格的 before/prior to
介词（符号与显式日期两形态）；显式截止仍须不晚于 prediction（晚于预测的
before/prior-to 不授界），after/since 开放窗照拒。`_FUTURE_EXPECTATION_OR_SCHEDULE`
增加 anticipated/projected/projections? 有界期望词，`_INHERITABLE_EXPECTATION_CONTEXT`
同步加名词 projections?；realized results/actuals/how-much 仍压过 projected 措辞，
无界 projection 照拒。spec 同步两条不变量；新增 7 条正/反回归。round-24/replay.py
以原 wire/basic_info/skill/context 复放 V124 c01 attempts 3/4/5：raw3 仅剩 need[3]
无界 projection 时间拒（need[1] 2026 指引误拒消失），raw4 对 need[1] 删 2026 的改写
按未标记漂移被投影丢弃，raw5 有界 projected reserve 需求进入最终态；最终 6 needs/
8 beliefs/8 证据行，need[1] 含 2026 逐字保留，未标记兄弟逐字保留，数值类 issue 独立
执行。943 测试（936+7）+ lint + replay 全过（仅本地验证；按本轮 brief 不 commit、
无生产调用；生产待 Codex 独立评审后 commit）。

2026-09-20（round-23）**为 H1 路由注入真实预测日期，完成 V123 residual 修复**：
删除不可靠的 dateless 年份推断 `_residual_refs_beyond_symbolic_bound`（date.min 与
父句年份两种代理都在 2025-09-30 误拒合法 2024 历史 actuals）及其错误测试/spec 表述，
保留 round-22 父句守卫（无效显式/符号父句不借出任何许可）。`LLMSignalRetrievalAgent`
新增与 controller 兼容的可选 `set_evaluation_context`（时区校验、UTC 归一、逐 case
重置），routing payload 暴露 evaluation_context；evolution_core 经既有 optional-setter
helper 注入真实逐 case prediction_time。路由 partial-residual 生产者检查对显式与符号
父句统一用真实日期走共享 `_bounded_residual_need`：可表示字面量被接受并由消费端
（selection intents + need-transition contract）一次性归一，真正不可表示的 residual
（已实现未来事实、无效父句、无界父句）在 Signal 执行前获得含实际边界+继承截止子句+
框架标记的可执行 H1 纠正；无日期路由仅保留可靠的显式截止检查，绝不捏造日期/年份/
当天。`_INHERITABLE_EXPECTATION_CONTEXT` 与时间守卫同大小写处理（大写 Guidance 已
测试）。重写错误的 dateless 符号测试为 7 条真实日期测试（上下文 payload+可表示接受+
intents/contract/下一轮路由一致性、已实现未来纠正、2024 历史 actuals 接受、大写标记、
逐 case 重置、naive 日期拒绝、无关 residual grounding-fallback 对齐）。
round-23/replay.py 用真实日期复放 V123 原始 attempts 7/8 wire：路由仅经原非时间纠正
即接受，共享有界表示（"..., by the prediction time, within the parent need's
guidance."）贯通 pre-reflection 准入（V123 原失败点）、intents、need-transition
contract 与下一轮路由；路由后产物均标注为合成续接（原始 raw reflection 不存在）。
936 测试 + lint + replay 全过（仅本地验证；按本轮 brief 不 commit、无生产调用；
replay registry 无 financing_listing_action:v2 故该 wire 选择被纠正掉——已注明局限）。

2026-09-20（round-19）**V121 Bumble 需多重性复原 + Kinross 时间/数量聚合反馈 + 漂移不吞语义失败**：
V121 两处拒绝根因修复（spec 先行，两份 owning spec 同步）。（A）Bumble raw102 保留重复
need 的一份并漏掉 need5，纠正 103 恢复 need5 但仍缺一份重复且重排序——
`_targeted_answer_need_transition_errors` 的 restore/replace 义务现携带
`required_need_occurrences`（按义务出现次数统计），`_research_need_transition_fallback`
按计数追加复原（不删除、不去重、不重排既有返回行）；`replace_with_exact_residual`
仅在义务实际指名的返回坐标原位改写，目标行缺失时追加精确 residual、绝不吞噬受保护
重复。投影层对 restore_exactly 整成员路径不做坐标写入（prior 坐标不是返回写目标，
绝不覆盖无关有效行、不因越界整体失败），复原交由成员权限门与确定性 fallback。
（C）scoped correction 漂移拒绝在预算耗尽时不再用泛化漂移消息覆盖 Structured 语义
失败：失败对象/语义失败配对保持，漂移诊断单独保留并在拒绝消息中并列报告（round-10
投影进度保留不回归）。（B）`_normalize_research_state_output` 在 evidence 形状可判定时
把 future-information 拒绝与 Basic 数量/断言链接/字面身份 issue 聚合为同一初始反馈
（时间类在前、契约次序不变；不放宽任何接受语义）。新增 7 条聚焦回归（重复多重性
复原、漂移纠正不换行、语义失败+漂移并列、缺 residual 追加不噬重复、聚合初始反馈、
合规预算内全修、清空证据仍拒绝）；917 测试（910+7）+ lint + round-19/replay.py
原始 wire 复放全过（Bumble 102/103 精确计数 2/1；Kinross 104 聚合反馈、合规 fixture
两步全修、raw106 诚实判仍无效；按本轮 brief 不 commit）。

2026-09-20（round-18）**身份反馈边界收尾：仅复原型进度、无 prior Basic 映射的新 ref、移除授权**：
round-17 通过独立评审后，Codex 指出两个具体边界遗漏与一处权限缺口，本轮仅修复这三点。
（1）`_research_state_evidence_grounding_fallback` 中仅含 basic_literal_identity_mismatch
的义务集（有 literal_restorations、无 removal_paths）被 `if not removal_paths: return None`
整体拒绝——现允许仅复原型进度，复原前对索引越界与目标行类型（basic_info Mapping）做
安全校验，结果仍经生产 parser 全量再验证后接受，混合复原+移除路径不变。
（2）`_raw_basic_literal_identity_issues` 的 `if not prior_literals: return []` 在
prior 非空但只有 signal 证据（证据生命周期后可能）时压制一切新 Basic ref——现对真正
新 ref 照常输出 remove-only 类型化义务；previous_state=None（initialize）仍豁免。
（3）两个 remove-only 身份码（basic_ref_not_in_prior_state / basic_literal_identity_ambiguous）
的 fallback 分支原先运行在通用 `remove in allowed_repairs` 守卫之前——现显式要求 remove
授权才驱逐行，replace-only/add-only 义务不移除；既有复原分支保持 replace-only。
规格先行同步两份 owning spec。新增 4 条回归（先运行记录修复前失败：仅复原被拒、
signal-only prior 返回 []、无 remove 授权仍驱逐）。round-18/replay.py 原样导入并重放
round-17 原始 wire 复放（A/B1-B3 全过）并追加 R1-R3 fixture 检查。910 测试（906+4）
+ lint + replay exit 0（按本轮 brief 不 commit；batch 重建局限保持明示）。

2026-09-20（round-17）**V120 LifeTime 反射链 Basic 字面身份缺陷：初始反馈聚合 + 确定性复原**：
V120 c01 case5 raw95 把 prior 1718 字符的 8-K Basic 字面删改为 1704（纠正后进一步
1697），该独立缺陷在 raw 校验层不可见，仅在断言类 structured issue 全部消化、预算
耗尽、fallback 移除 unsupported 断言后才以深层 plain ValidationError（"reflect
cannot introduce a new Basic Info ref"）暴露——纠正反馈从未提及，模型无从修复。
修复（spec 先行，evolution_research_validation.md / evolution_output_validation.md）：
新增 `_raw_basic_literal_identity_issues` 在 raw 聚合层与数量/断言 issue 同批输出——
同 projection_id 在 prior 仅有唯一字面时发 replace-only 的
basic_literal_identity_mismatch（repair_context 携带精确 prior 字面为复原候选），
多义字面或 prior 不存在的 pid 只给 remove-only 行级义务（不授权发明或歧义替换）；
深层 tagged-ref 守卫语义不变。确定性 fallback 新增两类分支：唯一锚定身份义务按
prior_exact_text 逐字节复原（以 normalized_paths 上报），显式 remove 义务行按既有
链接清理逻辑移除；其余无确定性修复的情形仍整体拒绝。断言类指令删除超出
replace/remove 实际权限的 "split the assertion" 表述（一拆多属追加、需独立 add
授权，round-16 已禁止隐式一拆多）。新增 7 条回归：双义务同批初始反馈、合规纠正经
生产 parser 接受且未提及兄弟逐字保留、改 claim/全新 Basic ref/歧义 prior 替换
fail-closed（拒绝或投影丢弃/确定性驱逐，绝不进入最终态）、signal 行不进入身份检查、
fallback 复原+授权移除。round-17/replay.py 以原始 wire（requests/ 与 cache/responses/
按 request_hash 关联 attempts.json）精确复放 raw95/96：初始反馈同时含
assertion_without_support 与 basic_literal_identity_mismatch（1718 字面候选），
原始 96→96 缓存重放链 3 次调用后 fallback 将字面复原为 1718 且仅做义务授权的移除；
合规两步纠正链被完整接受（8 证据/7 beliefs、字面逐字节、其余字段与 output95 一致）。
906 测试 + lint + replay exit 0（按本轮 brief 不 commit；主目标仍需独立验收后冻结
新联跑）。

2026-09-20（round-16）**列表路径统一“按成员、按操作”权限 + V119 原始全量复放**：
round-15 独立评审的原序纯删除反例（replace-only `rows[0]`，纠正返回原序去掉该
成员、兄弟全保留）在 RAW drift 检查层即被放行——三处并行且不一致的成员检查
（raw drift 内联算法、`_authorized_membership_edit` 快速路径、reconciler 缺省）
都把整成员（covered）槽位隐式当作可删除，且 `len(old)+covered+budget` 基数
上界隐式允许拆分/追加。修复：`_authorized_membership_edit` 成为唯一共享检查
（raw drift 与投影共同调用）——整成员路径仅授权“以恰好一行替换该成员”，删除
另需该槽显式移除授权（`authorized_member_removals`、整成员路径 + remove
repairs、或 compaction 的 `required_compaction_remove_paths`，后者已接入
`_complete_parsed_role`，合法 compaction 驱逐不受影响）；超出替换的行需显式
有界 add 授权；仅有移除授权而无整成员路径的成员可保留或消失但内容不可变；
空/缺失 allowance 映射保守为零删除（reconciler 缺省同步收紧）。运行时评估
输入守卫的 issue 转为类型化（渲染文本不变、`allowed_repairs=("remove",)`），
其明示要求的删除由此携带显式授权而非依赖旧的 covered 默认。规格先行同步
evolution_output_validation.md。新增生产回归：纯删除/拆分/无授权追加三负例，
显式删除与有界追加正例（既有 mixed-drift 恢复反例保留；一个直连投影正例改为
显式声明移除授权）。round-16/replay.py 以生产 reflect/initialize 角色完整重建
原始工件：c02 raw202 恰好因真实 signal 数值缺陷（supporting_evidence[8] 缺
"2025"）被拒且零 need-transition 误报，raw203 通过完整 parser/scoped correction
且重复 catalyst need 逐字保留（旧运行因误报多打一轮 204 仍被拒）；c01
initialize177→178→179 返回安全状态——179 整列表漂移被投影丢弃，仅显式删除
2/4 加一条 fallback 关联断言被移除，无发明内容，无关字段逐字保留。899 测试 +
lint + replay exit 0（仅本地验证，无生产调用、按本轮 brief 不提交 commit）。

2026-09-20（round-15）**V119 重复 need 误报纠正为出现级校验 + 列表回收安全收口**：
round-14 独立评审依据真实载荷更正诊断——V119 request202 的
research_state.next_information_needs[2] 与 [3] 字节相同，仅 [2] 被靶向；
response202 正确地把 [2] 换成精确残余并保留未靶向的 [3]，原校验用全局文本
成员判断（need in current / .index）把保留的未靶向重复误判为靶向失败。
修复（机制级，非索引重映射）：`_targeted_answer_need_transition_errors` 改为
出现/多重性感知——每个未靶向出现必须逐字保留、每个靶向出现须产出有界残余
（partial）或被移除（full）、selection 绑定 target_need_indices 全部下标、
一个返回出现不得满足两个先前出现；诊断 returned_path 由算法给出盈余出现
位置，不再全局 .index()（保留副本不再被指为目标）。确定性 need 回退每次
指令只转换一个出现（remove_exact_target 不再删除全部同文副本）。
配套 B 项安全收口：member_removal_allowances 提供但缺根键 ⇒ 该集合无任何
移除授权（原 .get→None→covered 全可删的反例已封堵）；锚点间授权槽数多于
返回行数的短 run 属歧义映射，直接拒绝（原 zip 猜首槽）；c01 Newmont
actual179 授权删除 2/4、恢复 valid5 与 6/7 顺序的行为保持。round-14 错误
期望的重复先行测试改写为断言 V119 原样转换接受，另用互异先行 need 测试
移位索引诊断。规格先行同步两个模块 spec；复放见 round-15/replay.py。

2026-09-20（round-13）**关闭运行时锚点守卫两个已证实漏洞：裸 with 与首现枚举**：
round-12 独立评审给出两条具体反例（`Please provide me with the baseline date
and price.` 与 `Using the supplied baseline price, what is the baseline
price?` 均错误返回 False）。机制诊断与修复（spec 先行，通用机制而非字串例外）：
其一，`_RUNTIME_ANCHOR_REFERENCE_PREPOSITIONS` 含裸 "with"，而双宾请求
（provide/supply me WITH …）里 with 引出的是被请求对象，不构成参照证据——
将裸 with 移出封闭介词集（扫描随即撞上请求动词而 fail-closed），参照性 with
仅由显式参照短语（compared with、with respect to）许可；逐一检查集内其余
介词（from/against/versus/vs/using/above/below/beyond/near/than），均无
引出直接宾语的歧义。其二，近邻模式为贪婪 `.{0,48}` 且提名只用 `search`
取首个锚点词，一个匹配可吞掉跨从句的重复提及，使前段参照提及掩盖后段同锚点
直接检索——提名改为对每个近邻 span 内的全部锚点词出现（finditer）穷举
（scalar 价格名词回退同样处理），独立从句全部受检、无首现豁免。V118 真实
request74 六条 needs、既有参照正例（from/relative to/measured from/outcome-of、
contiguous compared with）、五条普通查询负例与全部 PIT 检查均保持不变。
新增配对回归：provide-with 三负例 vs compared-with 正例；同锚点重复三负例
（前参照后检索）vs 重复同锚点双参照正例。round-13/replay.py 复用 round-12
复放框架并新增负/正例：修复前诊断运行 exit 1（恰好六条新负例误通过，证明
漏洞在真实守卫上）；修复后全部通过。888 测试+lint 通过（仅本地验证，无生产
调用、按本轮 brief 不提交 commit；残余限制见 round-13 报告，未宣称完整语义
正确）。

2026-09-20（round-12）**运行时锚点守卫改回默认拒绝：删除 round-11 fail-open 语义分类**：
round-11 独立评审证明锚点分类器把陌生左侧治理词当作许可（"What is the value
of the baseline price?"、"Please obtain…"、"Can we look up…" 全部返回 False），
被动/倒装句（"The baseline price is what?"、"must be identified"）同样漏过。
修复（通用机制，非动词表追加、非公司/字串例外）：分类默认失败关闭——锚点
提及只有命中封闭参照结构才视为"既定参照使用"：向左跨名词短语填充词后先遇到
参照介词/短语（from、relative to、compared with、above、using 等），或 "of"
的头部为固定结局名词（"a doubling of the adjusted share price"）；其余一切
（请求词、陌生治理词、倒装/被动改写、无治理词）一律拒绝。约 60 词的
_RUNTIME_ANCHOR_REQUEST_OPERATORS 动词表整体删除：未知措辞不再是普遍许可，
也不存在需不断追加的动词清单。current-price 触发改为在 "current/
prediction-time" 词本身处分类，故 "move the adjusted share price above the
current market level" 仍是参照使用而 "what is the current adjusted share
price" 仍拒绝；逐锚点、逐配对关键词分类保持混合/重复从句仍拒绝真实检索。
spec 先行更新 evolution_research_validation.md；tests 将 round-11 的
outcome-terms 正例修正为保守拒绝（陌生治理词 fail-closed 的文档化），新增
brief 五条普通直接负例与常见构造负例、多从句（参照+真实检索、不同锚点双参照）
配对回归；round-12/replay.py 只读复放不可变 V118 工件：六条真实 request74
needs 全部判非请求、生产解析器对该真实响应仅余真实数值证据错误（无
runtime-owned 错误）、全部普通直接/真实/混合查询拒绝、参照式使用通过。
886 测试+lint 通过（仅本地验证，无生产调用、按本轮 brief 不提交 commit；
真实后继联跑未宣称完成）。

2026-09-20（round-11）**V118 真实 request74 语义误报修复：区分"使用"运行时锚点与"检索"运行时输入**：
c01（Life Time，case5）attempt74 的 next_information_needs[0] 是发行人指引问句，
仅以 supplied baseline 作参照锚（"…quantify a bridge to a doubling of the
adjusted share price from the supplied baseline?"），却被
_RUNTIME_EVALUATION_BASELINE_INPUT 的近邻匹配判为 runtime-owned 查询。修复（通用
意图区分，非字符串/公司例外）：四个近邻模式只负责提名候选锚点；新增逐锚点治理词
分类（下划线归一后）：参照介词/短语（from、relative to、compared with、above 等
+ the supplied/fixed …）或嵌入其他内容词之下 → 视为问句"使用"的既定锚点；
疑问词/系动词/查找动词直接管辖锚点（"What is the exact baseline date"）→ 仍判
runtime-owned 拒绝。逐锚点、逐配对关键词分类使混合问句（引用一个锚点同时请求另一
运行时事实）仍被拒绝，无 supplied/using 词表旁路；真实的
baseline/date/current-price/definition/scalar 查询拒绝与全部 PIT 未来事实拒绝保持
不变（含 v109 标量收盘价负例与既有 exact baseline date and price 负例）。spec 先行
更新 evolution_research_validation.md；tests/test_evolution_execution_roles.py 新增
七条配对回归（request74 六条逐字 needs 全通过、真实查询负例、混合负例、参照式
current-price/outcome-terms/scalar-doubling 正例、参照锚不豁免未来事实拒绝）；
round-11/replay.py 只读复放不可变 V118 工件断言真实问句不再产生 runtime-owned
错误（其余真实数值证据错误可保留）。round-10 投影反馈修复原样保留。本轮 shell
权限钩子拒绝一切命令：测试/lint/复放未能执行，仅以对守卫、提示词与既有测试的
逐例推演验证；后继须先跑全套测试、lint 与 replay 再谈线上验收。

2026-09-20（round-10）**V118 真实"投影复检失败→旧反馈重发"缓存死锁修复**：
以不可变 V118 工件确定性复放两对真实 H_init 纠错对（c01 Life Time 74→75、
c02 Kinross 76→77），定位 `_complete_parsed_role` 宽松投影分支：安全投影存在
但复检暴露新的真实缺陷时，代码丢弃投影并保留原始 failed_output/义务重发，
correction-2 请求与 correction-1 逐字节相同（反馈哈希 eff859a9…/dbf8515b…
各自相等），精确响应缓存永远重放同一被拒响应直至 CandidateExecutionRejected。
c01：模型把被点名的 runtime-owned 需求重排而非删除（兄弟漂移 1..5），投影
移除违禁需求后复检暴露被首错掩盖的 claim-quantity/assertion 缺陷；c02：模型
修好了 9 条授权路径中的 claim 却未同步链接断言，投影复检暴露
assertion_without_support(current_beliefs[0])。修复：投影复检失败时保留该
安全投影对象（无关漂移已丢弃）及其真实新类型化诊断作为下一次纠错的
invalid_output/validation_error——新反馈哈希、指向新缺陷、同一两次纠错预算内
收敛；无安全投影时仍原样保留原始对象/义务（基线不变，不洗白整对象漂移、
不恢复整对象回退/blanket 信念权限/推断父删除）。spec 先行更新
evolution_output_validation.md；新增两条聚焦回归（投影保留馈送 + 无投影基线
不变）；round-10/replay.py 复现修复前同哈希死锁机制并验证修复后两对均在
缓存响应场景（经投影保留+确定性回退）与脚本化有效纠错场景直接通过生产
校验。877 测试+lint 通过（仅本地验证，无生产调用、按本轮 brief 不提交
commit；真实后继运行是 Codex 下一步）。

2026-09-20（round-09）**成员删除权限改为验证器显式元数据签发 + 比较器精确路径短路**：
round-08 附加验收用独立生产复放证明：removal_allowances 构建器把任何带下标的
叶子义务路径无条件升级为父行删除授权——反例：issue 仅授权 `rows[0].fix`
（allowed_repairs=("replace",)），纠错纯删除 rows[0] 后整个对象被接受，replace
叶子权限被升级成父行删除。修复（删除通用推断，而非叠加例外）：整成员删除权限
只能来自 (a) 所属验证器 issue 的 repair_context `authorized_member_removals`
显式点名精确成员路径，或 (b) 义务自身以整成员路径 `root[i]` 命名且
allowed_repairs 含 remove；叶子路径与整对象有效性永不授予父行删除。合法 H1
仅历史未知别名台账行删除改由其 h1_unknown_need_refs 验证器显式签发该元数据
（诊断路径 ["need_dispositions[0].need_refs","no_hypothesis"] 原样保留），
纠错对象仍须通过完整 H1 解析；不做 H1 全局豁免。另修 `_authorized_equivalent`
精确路径处理：节点自身路径被显式授权时先放行其整个子树再递归——此前同长
list 值叶子（root[i].tags）在邻行被授权删除时因递归进未列出的 tags[0] 而被
误拒。负例解析器只拒绝无效 fix（不再镜像 scope 保全），"否则有效仍被拒/被
丢弃"成为守卫真实性的证据：纯删除、替换+新增被拒（生产 reflect 旗标，2 调
用后 CandidateExecutionRejected），同长兄弟改写被投影丢弃并逐字节保留原值；
整成员 remove 义务与 authorized_member_removals 元数据正例通过；组合正例
（rows[0].tags 同长替换 + rows[1] 显式删除 + rows[0].keep 保留）通过。
round-08 成果（A 叶子扩步拒绝、B compaction 精确删除、无 blanket 信念权限、
有界追加、routing 组合链）全部保留。spec 先行更新（signal_roles H1 段 +
output_validation 权限段）。875 测试+lint 通过（仅本地验证，无生产调用、按
本轮 brief 不提交 commit；真实 Fast+Slow 复跑待办）。

2026-09-20（round-08）**全路径扩步保持字段/成员粒度 + 移除信念 blanket 依赖**：
round-07 独立验收否决两个越权反例：(A) issue 仅授权叶子 `rows[0].fix` 时，
变长成员检查把叶子算作授权槽位，纠错得以改写兄弟字段并插入任意记录；
(B) 投影复检发现 research_state_item_over_limit 时，`_structured_revalidation_
paths` 把容器根 `rows` 平铺成整表复制授权，无视 repair_context 的精确删除
元数据（rows[1]），rows[0] 漂移被接受。修复机制（非补字符串）：只有精确
成员路径 `root[i]` 授予整成员替换/受限拆分；叶子路径永不改写兄弟字段或
插入记录；被义务点名的成员可删除（对齐纠错契约"或在不允许省略时删除"），
未点名成员必须按原序幸存（允许其自身授权叶子编辑，新增 `_authorized_
equivalent` 递归等价）；插入/追加仅由验证器显式 allowed_repairs 含 add 的
义务按缺失字面量数授予有界预算；复检扩展只应用 compaction issue 的精确
删除路径（容器根不授权、无元数据则 fail closed，投影新增确定性整成员删除）；
压缩首轮 scope 中精确删除路径已枚举的容器根路径不再授予成员级权限。
移除 visible_answer_need_retained 与 research_need_transition_invalid 上
无条件 dependent_paths=("current_beliefs",)——信念改动须由真实同 claim
链接断言或真实压缩义务授权；新增生产路径负例（need 纠错期间无关有效信念
逐字节不变）。删除漂移 visit 内不可达的 `_authorized_membership_edit` 分支
与因此冗余的 `preserve_descendant_list_shape` 旗标。反例 A（插入+删除两
变体）、B、有界追加正/负例回归；873 测试+lint 通过（仅本地验证，无生产
调用、按本轮 brief 不提交 commit；真实 Fast+Slow 复跑待办）。

2026-09-20（round-07）**消除列表形态的越权逃逸（整对象 stand-in 删除）**：
round-06 附加验收确认了独立反例：issue 只授权 `fix` 时，纠错把无关列表
`keep` 从 ["original"] 改写为 ["drift","extra"] 也被整体接受——
`_lenient_list_membership_edits_only` 对任何裸列表根漂移放行整对象，且
"仅限变更长度"的声明不成立（无授权路径到达时同长改写同样以裸根形态出现）。
修复：删除该整对象回退与死变量 `projected_failure`；模型完整对象不再替代
投影——未获路径授权的集合一律 fail closed；成员变更仅当义务路径授权该集合
的具体下标槽位、未授权成员按原序逐字节幸存、新增量受（原长度+授权槽位）
约束时才被接受，漂移检测与投影执行同一规则（投影同时跳过被整根复制涵盖的
下标子路径）。合法跨字段修复改为验证器签发的结构化依赖：initialize 可见
答案 issue 增加 dependent_paths=('current_beliefs',)，research_need_
transition_invalid 声明信念聚合依赖，stale-resolved 与 open-question 重复
检查由 prose 转为携带精确路径的结构化 issue。新增列表反例回归（变长+同长）
与标量反例并列；原"删除旁漂移拒绝"测试改为断言投影保留无关需求。spec 先行
更新。869 测试+lint 通过（仅本地验证，无生产调用、按本轮 brief 不提交
commit；真实 Fast+Slow 复跑待办）。

2026-09-19（round-06）**拒绝不可表示的 partial 残差（fail-closed）+ 组合链回归**：
round-05 独立验收否决了"不可有界表示的残差降级为 remove-or-narrow"——真实
反例（残差改为 "What were the realized revenue results for Q1 2026?"，评估
截止 2025-09-30）下一次 reflect 调用即可删除未答需求并 finalize，或用无关
continue 需求掩盖删除。修复：共享准入校验 `_reject_unrepresentable_partial_
selections`——运行时评估边界存在且 partial 残差无法有界表示时，reflect 在
构造任何提示前同步拒绝（ValidationError，零模型调用）；契约构造器同样
fail closed，不再向 available_answer_actions 塞入不安全字面残差、不再输出
remove-or-narrow 降级指令；`_targeted_answer_need_transition_errors` 改为
删除必须 restore_exactly、原样保留合规，且不为已实现未来事实伪造截止子句。
新增组合式生产路径测试（真实 select→reflect→下一轮 select，断言下一轮实际
传输的 routing prompt 精确消费已接受的有界更窄残差）与两条验收反例；V117
有界修复与 round-03/05 漂移防护不变。867 测试+lint 通过。本地验证，真实
Fast+Slow 复跑待办。

2026-09-19（round-05）**修复 V117 真实矛盾残差契约 + 收紧 round-03 整对象回退**：
原始证据（v117-required-residual.json，请求 12 义务原文）证明路由自身产出并
授权了一个越界残差（"…remainder of 2025 and 2026…" 无 as-of 截止子句），
下游 transition 守卫强制要求该字面量而时间守卫必然拒绝它——模型陷入矛盾
指令环，非单纯 sibling 保全问题。修复：新增共享规则 `_bounded_residual_need`
（残差丢失父需求截止子句时原样恢复继承子句，产出有界且真正更窄的必需表示；
不可修复时降级为 remove-or-narrow 而非强求不可用字面量）；路由 select 校验
拒绝日历范围超出目标需求显式 as-of 界的 partial 残差（以父需求自身界为锚，
生产者接受的残差必被消费侧守卫接受）；契约/intents/transition 校验/
`_restore_inherited_need_cutoffs` 一致使用同一规则，恢复目标由"整条父需求"
改为"残差+截止子句"。round-03 整对象回退删除：lenient 模式下投影仅可经
投影对象自身的结构化复检 issue 扩展复制路径，整对象仅在"全部漂移都是列表
成员增删且全量复检通过"时可替代投影，标量/嵌套/同长条目漂移一律 fail
closed。回归测试覆盖真实矛盾链（生产 role/validator 路径）、生产者拒绝+纠正、
漂移反例与 prose-only fail-closed；862 测试+lint 通过。详见
reports/fast-slow-joint-correctness-20260919.md；本地验证，真实 Fast+Slow
复跑待办。

2026-09-19（午后）**round-03 修复 H_reflect 普通纠错漂移失控（V117 Fast 死亡根因）**：
`exact_compaction_scope=True` 且失败无真实压缩义务、issue 又未声明
`write_scope_complete` 时，`_authorized_correction_paths` 恒返回空授权，未点名
字段漂移完全不设防——纠错可整段重写并悄悄回退仅存在于最新被拒输出中的修复
（V117 c01 attempt 10→12 链）。现该场景改走义务路径并集做漂移检测+投影
（基线=最新无效输出）：投影结果须整体复检通过才采纳，否则复检模型完整对象
（合法联动编辑不再被误杀）；真实压缩义务的 closed scope 与
write_scope_complete/普通控制器的严格 scope-failure 行为保持不变。spec 补写
基线与回退语义；回归测试经真实 `_complete_parsed_role`（两连纠错反悔链、
permitted_dependency_paths 放行、压缩/列表删除保留）；856 测试+lint 通过。

2026-09-19（午）**残留清单清零（a6dd393）**：四项记录在案的 slow-round
残留全部修复并验证（850 测试+lint）：(1) 晋升后周期续跑——resume 改为
接受"已提交周期 input→output 链末端"解释的 live Registry（V114 真实盘
状态旧检查必败、新检查通过；单测覆盖四分支）；(2) 周期墙钟看门狗
（SIGALRM 4h 默认，超时走 exit 75 自动续跑通道，治 V113 型静默挂死）；
(3) 零文档+无适配器语料从 adapter_missing/PERMANENT_FAILED 改判
no_matching_documents/诚实弃权（统计口径不变）+counter 引用内部句指引
（V115 周期 1 叙事 cohort execution_failed=0）；(4) slow-history 命名空间
按字节校验多跳传递（V115 实测双 ns）。V115 生产验证：基线 v6（叙事因子
在稳定目录），周期 1 干净提交且新叙事候选一次入册，周期 2 正常启动、
中途触及 400 尝试合约上限暂停（冻结上限按设计）。code_revision 绑定为
可复现性设计属性，保持不变。详见审计报告"残留清单清零"节。


2026-09-19（晨）**叙事因子晋升入库达成（V114 cycle 1）**：
`order_confirmation_disclosed:v1`（LLM 技能叙事谓词，检索族 filing/news/
transcript 等）在 16 个全新 check 上 tp=3/fn=2（recall 60%）、fp=0、
decisive 3/3 全对，直接配对门晋升进稳定 Registry（v5→v6），skill/
spec 持久化，signal_goal_status=met——项目史上首个非结构化因子入库。
第二轮冲刺（V109–V114）新增五项泛化修复：跨 category 同名候选二义
拒绝（e801ed8）；pooled 累积跨工作区转移（ff25023——居留者与其评估
历史此前每次 freeze 清零）；**pooled 计数读嵌套记录形状（eeaf8a4——
三区规则自落地即结构性死亡：pooled decisive 恒 0，任何居留者永不可能
达 12 晋升、满 5 周期必被误淘汰；旧测试恰用不存在的平铺键构造故不可
见）**；复访居留者枚举读 validation candidate_effectiveness（3d52175
——复访者不进 attempts，首周期后/第二跳继任即掉出名单）；边缘纠错
永远给合规修复+反思输入携带 staged 候选 check 结果（5020aa8）。
根因复盘：正类 tp≈0 主因是谓词-标签错配（正类窗口多为封面/样板文本，
judge 判读原文确认"文本充分但无合格事件"），反思输入现已携带
tp/fn/fp/tn 真实结果引导谓词设计。V114 cycle 2 撞 V98 已知"周期内
晋升后历史链校验"边界停止（独立遗留项）。累计 14 个生产工作区、
约 $9、1500+ 真实调用。审计详见 reports/slow_round_prompt_audit_
20260913.md 末三节。

2026-09-19（凌晨）V100–V108 叙事因子入库冲刺完成：9 轮生产 slow round
（755 真实调用/$4.59，全部单周期 immutable 工作区迭代）定位并泛化修复
**六个代码级阻塞**：(1) 生产 modality_metrics 四项硬编码恒 0 且 eligible/
explored 同表达式——跨周期反思一直被谎报"叙事零产出"（c2adf1c，
ControllerResult 携带真实覆盖/读取计数，物化/验证计数来自真实入册循环）；
(2) 200-空响应（reasoning 耗尽无 message chunk）抛不可重试错误直接杀死
整周期——归类 Retryable 进入既有传输重试+自动续跑，refusal 保持不可
重试（ee6b877，V102/V104/V106 三次瞬断被自动恢复）；(3) 检索族词汇
不一致：谓词/目录说归一化族而物化校验用裸 source_type 交集——统一复用
执行侧 source_types_compatible 族等价，fixture 预检同步（ee6b877）；
(4) 物化收敛：fixture 失败反馈携带执行器 interpretation 原文、技能分类
法逐 fixture 类赋 canonical 值、谓词候选纠正上限按执行类型分档、失败按
候选分键（35110e5）；(5) 执行器把"无满足肯定条件 span"读作证据不足将
neutral 坍缩为 unavailable——三处提示/校验统一为 neutral/negative 引
用已检查非合格 span 作反证（86b65b8）；(6) 物化输入证据摘录携带逐字
span 导致身份泄漏（FORM/DFIN）——进入 payload 前统一身份掩码+工件
剥离，账本保留 verbatim 供回放（84c7d04），另 a4428b0 结构化摘录补
文档源类型。效果：7/9 轮提出叙事候选（共 10 颗），修复后 V105/V107/
V108 的 4 颗全部一次穿过物化+契约校验+标准验证并成为 provisional
居留者（pooled 三区规则累积）；V104/V108 另有结构化晋升
（cash_burn_rate_elevated:v1、gross_margin_change:v2，Registry v3→v5）。
**严格晋升（入库）未达**：订单确认类谓词 recall≈0 属研究质量而非代码
阻塞，按 spec 不为模态放宽 promotion 门，交给 pooled 累积与反思搜索。
审计详见 reports/slow_round_prompt_audit_20260913.md 末两节。

2026-09-18（深夜）V99 后续修复与三轮 shadow 迭代完成：四处"最后一公里"
修复（digest narrative_summary、fetch 目录提示+标题样本、属性词表接入
生产、prior_modality_footprints 跨周期压力）+ 两轮身份泄漏修复（标题
回退改可见文本投影；strip_document_artifacts 剥离 SEC 文件名 token）。
第三轮 shadow 不变量全过，narrative_summary 与标题样本真实进入每个
决策视图、模型 rationale 显式引用；仍无叙事提案——新定位短板：filing
"标题"为可见文本首句（财务句子，信息量低）、属性投影在单 fetch 子集
内低于 min_support 几乎不出现（需真实标题优先 + min_support 按 seed
文档数缩放）。全部测试/lint 通过，checkpoint 1ea3142→ee38241→cfde400。

2026-09-18（晚）V99 叙事接口生产首验完成：两周期 clean exit（134
attempts/$1.42），探索义务 100% 履行（modality_metrics 入 audit：两周期
eligible 全 explored、零静默跳过），10 个步骤 rationale 显式考虑叙事模态、
4 次 fetch 全部纳入叙事族、discovery-only 证据目录被两 seed 主动使用；
cycle 1 新候选 operating_profitability_margin:v1 成为 provisional 居留者
（配对门两底线诚实失败）、cycle 2 复访运行。未竟：叙事候选提案为零
（read_count=0、无 predicate——模型 fetch 后未深读事件正文），反思未
消费 modality 足迹；两个下一杠杆已定位（浏览深度激励 + 反思输入扩展）。
Shadow 轨同步验证义务 wire 级生效。审计详见 prompt 审计报告 V99 节。

2026-09-18（下午）叙事因子挖掘行动方案 v2 的离线阶段（Phase 0–5 + Phase 6
离线半）已实施：Phase 0 spec 契约（NarrativeSpan、read 语义与 browse 预算
维度、discovery_only 边界、模态探索义务、叙事谓词、投影仅索引、迁移边界、
case briefs 显式延后）；Phase 1 叙事证据可读（NarrativeEvent 增
title/source_family/published_at/exact_span；read_span 支持
fact|event|document 三目标 + offset/length + browse 预算（fact→heavy、
event/document→browse），账本存 verbatim 窗口哈希；inspect_catalog 增
scope=evidence 目录）；Phase 2 模态义务（modality_coverage 进视图、
domain 终态在叙事可用未探索时不可入、control-plane 终态豁免、
modality_metrics 七计数入 mining audit）；Phase 3 叙事谓词契约
（measurement.predicate + 族相交/原始叙事引用/阈值算子机检）；
Phase 4 属性投影最小索引层（零调用语料派生词表、确定性投影、
discovery_only 标注、"miss≠不存在"）；Phase 5 物化输入扩展（谓词+叙事
摘录+八类叙事 fixture 提示）与离线八类 fixture 测试。全套 841 测试 +
lint 通过；V98 语料零调用 replay：40/40 叙事事件 content-hash 可回溯、
目录 discovery_only、投影仅索引。Phase 7（shadow，真实 DeepSeek）与
Phase 8（生产观察）按用户指示留待后续。审计记录见
reports/slow_round_prompt_audit_20260913.md。

2026-09-18：已整理叙事/非结构化因子挖掘行动方案 v2，定位为 V98 之后的新
contract/workspace 设计。方案要求先更新 spec/contract，再打通原始 narrative
读取和模态探索机会义务；AttributeProjection 仅作为可选索引层，尚未实施，
也未发起新的 live 外部调用。详见
`reports/narrative-factor-mining-action-plan-2026-09-18.md`。

2026-09-17（夜）**V98 首次达成新信号挖掘入库**：cash_to_current_
liabilities_ratio:v1 由生产 LabelAwareMiningController（Seed A）挖掘、
物化（检索族约束）、契约校验通过，16 个全新 check 上 TP=5/FP=0/TN=6/FN=3
（precision 100%、recall 62.5%、11 对 2 错）双底线通过立即晋升，Registry
v2→v3，signal_goal_status 首次 met（48 attempts/$0.55）。四代生产运行
（V94 控制器切换观察、V96 物化 slug 修复、V97 分级准入/居留/复访全链
live、V98 入库）+ V93/V95 两个不可变诊断工作区（重放幂等、传递导入
去重两个阻断根因修复）。V98 cycle 2 因周期内晋升后的历史链校验边界
暂停（下一修复项；周期 1 权威完整）。旧 H/E 生产路径的角色模型兼容、
只读回放保留；归档待后续。Fast 轮 Predictor 信号路由审计为后续独立项。

2026-09-17（晚）Phase 6 生产切换 + 三次运行诊断与修复 + V96 执行中。控制器
已按能力分发接入生产挖掘入口（bcd8c2d：v8 清单+JSON caller → Seed A/B +
物化调用 → 不变的契约校验/分级配对门；H/E 保留 role-tracks 供只读回放），
V94 完成两周期 clean exit：控制器双 seed 大多终态 candidate、Update 轮换
生效（3 个新面孔目标，模型诚实 no_change），但两周期候选均死于物化
signal_id 非法——运行时 slugify 修复（619a17d）。V95 诊断传递性导入平方
膨胀（feedback rows 跨代 ≈2×：1,399→12,092，首个请求 1.18M tokens 超限）：
修复为仅从最新周期 input 投影 feedback 行（超集去重 12,092→6,075）+
source-read 选择目录有界化（最近 1024 条+省略计数，79020b7）。信号选择
坍缩审计入报告：5 周期仅 4/14 信号被选（预选无轮换+H1 建议跳队自增强），
呈现本身充分（cards 带完整 learned profile），修复为近期轮换惩罚
（-600/次，穿透 +1000 建议）。V96 入册 3 个控制器新候选（均死于契约校验→物化纠正回环修复 da0103f）；
V97 全链 live 验证分级准入：4 个新候选入册、2 名 provisional 居留者、
复访+居留上限显式拒绝均按设计运转；入库最后缺口=物化检索契约与真实
check 语料不匹配（availability 0/4），修复 f9ddf8c（检索族相交校验），
V98 验证中。V93/V95 为不可变诊断工作区。行动方案 v2.1
已附执行收尾记录（Phase 6 完成、Phase 7 部分前置、晋升协议修订取代
§0.3）。

2026-09-17（傍晚，第三次修订）配对门两道底线（用户决策）：有效性记录新增
TP/FP/FN/TN 混淆矩阵（按正类键控、仅计 available）；新增正类 recall 底线
（TP/(TP+FN)≥0.5，治"只在易对的控制股出手刷准确率"的怯懦画像——旧门下
该画像 decisive/correct 全满分可直接晋升）；与方向底线（correct>wrong）
并列，新信号仅因二者失败→provisional，更新类均硬门；pooled 三区制转正
需显著性∧recall 达标、满 5 期 recall 仍低（TN-farming）则淘汰。F1 完整门
因出手率漂移基线暂不采用（分析存审计报告）。827 测试+lint 通过。

2026-09-17（傍晚，第二次修订）采样/评估卫生改为按候选模型（用户澄清
permute 语义后的重设计）：每周期对全 population 完全重新 permute 并划分
dev/check（case 角色跨轮自由轮换——上轮 check 本轮可进挖掘集；周内仍
issuer-disjoint 且标签均衡）；评估卫生在 effectiveness gate 按候选执行——
候选永不评估于其提案轮 dev 集（`generation_case_ids` 随首个评估记录固化
并跨记录透传）∪ 自己已评估过的 case（防止 pooled 二项统计伪重复）；全局
单向暴露排除已回退（会单向耗尽 565 正例池且与"每轮全新开始"冲突）。
经掩码 reflection 文本的残余标签扩散为已接受残余风险，由 provisional
淘汰规则兜底。826 测试 + lint 通过；分级准入/check 扩容（见下条）不变，
行为自 V93+ 生效。

2026-09-17（傍晚）晋升门协议修订（用户决策）：分级准入 + check 扩容 +
评估卫生。统计依据：单周期多数门 n=16 时噪声通过率 0.40 / 60% 信号 0.72，
一次性认证 55% 需 n≈616——区分度只能来自跨周期累计。实施（825 测试 +
lint 通过，spec 同步 signal_evolution/signal_mining_agent）：(A) 新信号
方向平局→provisional 居留者，每周期在当期全新 check 复评并按 pooled
三区制裁决（转正 decisive≥12 且二项 p≤0.10 / 累计 5 期仍≤随机则淘汰 /
继续），居留上限 2，更新类保持硬门；(B) validation_cases_per_class 2→8、
effectiveness case_limit 8→16（dev:check=2:1；后继冻结建议 data caps
400/cycle、800/run）。修订依据与计算存 prompt 审计报告"晋升门协议修订"
节。行为变化自下一个冻结的工作区（V93+）生效；V91/V92 及其合约不可变。

2026-09-17（下午）新 slow round 影子语义审计 + 六项泛化修复 + V92 两周期生产
完成。对 shadow6（Seed A）与 shadow7（Seed B 首次 discovery live）逐请求审计
发现六个泛化缺陷并全部修复（450e05e→347379c→d35bdd9，spec 同步，821 测试
+ lint 通过）：视图无工具结果反馈（模型连发 10–12 次宽泛 fetch，新增
evidence_digest/last_action_result 后 3–4 次调用即终态 candidate）；heavy
预算耗尽被当模型违约致 technical_failure（改为保留一次切换机会后确定性
deferred_budget）；候选 observable 直接复用 catalog 基名（propose 拒绝）；
处置纠正文案反向把 142 条处置压成全量 not_testable（r3 已分化为 8 行 5 类）；
候选证据引用账本合法但与测量概念无关（compare 附带 fact_ref + 点名概念
必须被同概念引用覆盖；r3 两候选引用 100% 匹配测量概念）；raw info 层把
historical_price JSON/供应商信封投影成叙事事件且 filing excerpt 是 SGML
样板（叙事事件仅从 filing/transcript/news 族投影并复用生产可见文本锚点）。
r2/r3 影子四轮全部终态 candidate、四项不变量通过（$0.023–0.104/轮）。
生产阻断根因为 ExternalAttemptLedger 按 reserved 而非 settled 累计（V91
cycle 2 在 reserved $4.94 vs actual $1.36 时 fail-closed 不可恢复）；修复为
finalized 按 actual、in-flight 按全量预留。V92（合约 0f5bc8e6...a961be，
代码 450e05e，slow-history 导入 V91 提交前缀）两周期全部提交：cycle 1
Mining=1（operating_income_sign:v1）+ Update=2，cycle 2 Mining=1
（operating_loss_presence:v1）+ Update=1；配对门显式诚实拒绝（可用性
1/4 低于配对最小值；方向 2 正 2 误无正向证据）；153 attempts/$1.27，
中途传输瞬断按同合约自动恢复且恢复命中响应缓存。cycle 2 因周期间 HEAD
前进被 code-revision 检查拒绝后，从 /tmp/v92-frozen worktree（450e05e）
补跑完成——后续会话若在周期间提交代码，需用同法或重冻结后继。信息流动
wire 级验证：V91 c1→c2、V92 c1（消费 V91 提交的挖掘/更新/验证单元）、
V92 c1→c2 反思均真实包含前序结果。Phase 6 切换条件中的影子轮数要求
（"不只一轮 shadow"）现已满足（shadow8–13 共六轮 + 生产 V92 两周期），
生产切换仍待用户按方案 Phase 6 纪律确认。

2026-09-17 v2.1 执行推进：Phase 0 规格已提交（signal_mining_agent.md 新建，
H/E 标注为受门控的 legacy/对照路径，architecture.md 增加受门控替换段）。
Phase 0b 的 V90（合约 3eb83e50...74fe）live 验证完成核心问题后停在 Alpha
Vantage 配额：H1 wire 内含 measurable_evidence_manifest，三个假设全部锚定
结构化来源（现金跑道/项目桥特异性/营业利润-营收增长差），不再出现窗口外
observable——manifest 因果链在 live 上成立。57 次尝试/$0.4964、指针 0/0、
零提交；AV Information 信封配额致 case-005 证据获取暂停，24 次自动恢复未
清后按计划停止，V90 为不可变诊断工作区（代码绑定 10e57d5，HEAD 前进后
不可 resume，重开需从 V89 重冻结 V91）。Phase 1 最小 Evidence Graph 工具
已实现（mining_agent_tools.py：Fact/Relation 惰性投影、同概念记录对、
冻结规则 compute_statistic、同案例跨文档共现、带 omitted-coverage 的
fetch；6 项新测试）。Phase 2 受控 controller 已实现并按验收标准通过：
mining_controller.py 提供固定 action enum、单调状态机
（ready→exploring→evidence_ready→candidate_proposed→locally_validated→terminal
与四类非领域终态）、双维度预算（重动作 12/轻动作 4，耗尽→deferred_budget）、
有界结构化纠正（2 次后 technical_failure）、runtime 拥有的 append-only
mining ledger（input/output 哈希、coverage、omitted coverage）、Seed A
终局 need-disposition ledger（全覆盖/处置枚举/signal_refs 基数校验）、
Seed B runtime-owned label map（模型自撰 label 字段直接拒绝）、候选证据
必须 ⊆ 账本且至少一次 fetch 后才能提出、no_pattern 必须引用账本内
explored families。7 项 fixture-caller 测试驱动完整
seed→action→tool→ledger→terminal→validation 链。Phase 3 零调用历史回放
已完成：mining_replay.py + scripts/run_mining_replay.py 在 V87/V89/V90
冻结历史上确定性测量信息到达率（V87 0.21–0.43、V89 0.22–0.26、
V90 manifest 锚定后 0.25–0.46，最佳假设 +0.20），四项不变量（证据
逐字回溯、PIT、账本 append-only、视图零身份泄漏）在真实别名下全部
通过；报告见 reports/cold_start/mining-replay-*.json 与 prompt 审计
Phase 3 节。同时修复 Alpha Vantage 信封原文（脱敏截断）随 reason
持久化。Phase 4 受控候选闭环已完成：mining_closure.py 以八类固定场景
（单事实/多期间/分子分母/跨文档/叙事事件/证据不足/技术失败/no-pattern）
在合成 issuer 不相交 dev/check cohort 上零调用驱动控制器，四个场景
（单事实、比率、跨文档、叙事事件）完成 discovery→candidate→fixture→
holdout 模拟→晋升决定的完整闭环并 promote，多期间场景的 check 集故意
与 dev 模式矛盾后诚实 reject（绝对底线：最低可用数 + 方向正确严格
大于错误）；控制器视图补充 known_event_refs。全套 811 测试与 lint 通过。
下一步 Phase 5 live shadow cycle。已知泛化缺口：alpha_vantage Information 信封原文未入账本、
quota 标记表需复核。

2026-09-17 Phase 5 完成：V91 生产 cycle 1 提交 Mining=1（operating_cash_flow_sign:v1，
配对门诚实拒绝）、Update=1（guidance_acceleration:v2 provisional）——用户三层
目标的第 3 层（挖掘/更新均非零）首次在生产达成；影子轨（控制器+Evidence
Graph）17 调用/$0.35 终态 candidate、142 条 need-dispositions 合规、四项
不变量通过，八项切换条件全部满足（见 prompt 审计 Phase 5 节）。生产
cycle 2 因 SSL 重放推高预留于配对门阶段 fail-closed 暂停（恢复需
/tmp/v91-frozen worktree 的 5c70b79）。按 Phase 6 纪律切换需再加一轮
shadow。影子调试修复七个泛化缺陷（族词汇表强制、relation 入账本、
聚合纠正前沿等），全套测试与 lint 通过。

2026-09-17 形成 Slow Mining 重构行动方案 v2，并经评审修补为 v2.1（当前权威）：
以共享 PIT Evidence Graph（惰性构造、Relation 基数有界）为基座，用受控的
LabelAwareMiningController 合并 hypothesis validation（终局附带 need-disposition
ledger）与 open-ended label-aware discovery（标签仅经 runtime-owned 结构化
label map 呈现），H2/E1/E2 不再作为生产挖掘硬链路；保留 Update、fixture、
issuer-disjoint holdout、paired effectiveness 和 promotion 门。候选非零拆分为
硬验收（管线正确 + 受控闭环结构可达）与程序目标（live 非零，Phase 7 前不下
结论）；先完成 spec、可选的 V90 manifest legacy 验证、零调用回放和受控候选
闭环，再进行 live shadow。详见
`reports/slow-round-mining-agent-action-plan-2026-09-17-v2.1.md`。

V89 executed both authorized slow cycles to clean commit (exit 0): 166 attempts,
`$1.1365`, one transient H1 provider error auto-recovered and one retryable
exploration pause auto-resumed; no stage failures. Cross-cycle information flow
is verified live: cycle-2 reflection consumed cycle-1 result/validation/
effectiveness/mining-decision units, H1 emitted explicit retrieval plans with
reordered hypotheses, and Update added a new customer_concentration:v2 target.
Update is nonzero both cycles (3+3 candidates, all honestly rejected by paired
gates). Mining remains zero for a now-clear reason: E2's per-case contrast shows
the PIT evidence windows are qualitative 8-K/10-Q disclosures while H1
hypotheses demand quantified numerators/denominators (analyst targets, backlog
values, runway outflows); E2 honestly returns inconclusive. Next lever is
constraining H1 observables to evidence actually available in-window or
extending analyst-expectations/news coverage before induction, not more prompt
patches. External-call failure messages are now persisted (ledger + trajectory,
500-char cap) so transient-versus-permanent failures are diagnosable from
artifacts; 782 tests pass. See the V89 section of
`reports/slow_round_prompt_audit_20260913.md`.

V88 completed Fast/Slow 0/1 with Mining 0, Update 0 and promotions 0. Isolated
DeepSeek replay of V87 four financial executions succeeded with correct latest
facts and exact citations. H1 still repeated prior incomplete retrieval plans;
E1 forced financial slots displaced business facts. E2 honestly found no repeated
contrast. Update did move to guidance_acceleration, but an unnormalized SSL read
failure escaped provider handling and the failed stage was committed.
V89 preparation removes forced E1 slots/recovery substitution per the user's
explicit decision, requires H1 to act on prior failures and untested work, and
normalizes low-level transport errors. All 781 tests pass; original E1 response
replay retains valid observations (3/4 batches need no correction; one actual
nonliteral quote is isolated). Fresh live successor remains to be run.

V87 completed cycle 1 (Fast/Slow 0/1, exit 0): 1 executable Mining candidate,
0 Updates and 0 promotions. Reflection/H1/E2 actual requests carry complete
Mining history and directional/retrieval contracts. The candidate
operating_cash_flow_deficit_state:v1 passes four live fixtures but was rejected
on holdout (available 3/4, correct 0, wrong 3, execution_failed 1). Raw-source
audit proves this is not clean efficacy evidence: soft execution confused an
investing-cash-flow record with operating cash flow in one case, chose an old
annual value instead of a latest opposite-sign value in another, and failed
citation validation at a chopped record edge in another. Fix structured
financial projection with concept/unit/period/whole-record lineage; also repair
market numeric evidence that currently cites only the first 240 characters.
Preserve V87 results; do not manually rescore or promote. See prompt audit report.

V86 was deliberately interrupted after reflection (exit 130, no cycle commit):
actual history selection deferred entire 86 KB H and 70 KB E Mining tracks
under the 64 KB reflection budget, hiding E2 candidate semantics. Local/imported
history now exposes complete H1 hypotheses and H3/E2 decisions with exact
locators; whole tracks remain available. V84 raw-history replay fits complete
E2/H3/H1 decisions into unchanged 64 KB/12-item limits. 109 focused tests pass.
Freeze V87 from committed V84 after full verification; preserve V86 evidence.

V85 paused before cycle commit on Alpha Vantage news quota (exit 75); its
completed H1 has analyst revisions, liquidity runway and scheduled catalysts.
Finnhub and Massive same-window probes both returned successful empty lists,
not evidence. The existing catalogued Finnhub news fallback is now connected
through managed resolver transport; title projection and strict historical
window/issuer checks are covered by 80 passing focused tests. V85 stays intact;
a fresh successor must use this code and the last committed V84 history.

V85 preparation: generation now receives explicit existing directional and
retrieval/fixture semantics; unavailable cannot hide technical fixture failure.
H1 source-request checks respect falsifier field ownership, and narrative windows
do not cut a final word/amount. Unmodified V84 H1 output parses three hypotheses;
776 tests and lint pass. Evidence component selection remains an open quality
limitation. Freeze the successor from committed V84 to carry its actual failures.

V84 (5264747) completed Fast/Slow 0/1 with 0 valid Mining, 3 Update
candidates, and 0 validated/promoted Signals. Two Updates regressed; one is
provisional for availability 2/4. The E2 candidate failed fixture retrieval
coverage before LLM execution (minimum_observations on a standalone financial
fact). Actual target/prior/reflection wiring is verified, but candidate polarity,
H1 falsifier false positives, evidence component selection, and reflection prose
remain unresolved. See reports/slow_round_prompt_audit_20260913.md. Preserve V84
and freeze a successor only after coherent contract repairs and verification.

V83 was frozen at 2837334 but never executed externally. Pre-launch review
found the remaining H1 alternate-outcome regex also rejected historical market
confirmation language. Restrict it to explicit forward outcome horizons and
collect temporal violations with the whole need-ledger correction frontier.
All 83 adapter tests pass, including mixed routing/temporal correction and
historical-price acceptance with future-outcome rejection. Freeze a fresh
successor from this checkpoint; do not execute the stale V83 contract.

V82 committed Fast/Slow 0/1 with zero valid Mining, Update and Promotion.
The exact-wire audit found missing explicit target semantics, E1 financial
comparability bias, weak E2 research relevance, and a stale Update tool-workflow
prior. E2 confused evidence-period alignment with a company feature and chose
the wrong deterministic formula. Source inventory also confirms no local news
or transcript evidence in the 16 E1 case windows; this remains a data limitation.

The successor now passes one canonical research objective through Slow roles,
aligns and connects fixed priors, preserves E1 comparability without preferring
a second financial pair over narrative, and supplies actual function semantics
to H3/E2/Update. A separate research thinking alias has explicit frozen output
headroom; Judge stays plain. Exact high-reasoning H1 output plus one correction
parses into three hypotheses after fixing Predictor-regex misuse on historical
windows and performance obligations. This is diagnostic evidence, not a live
Signal result. See reports/slow_round_prompt_audit_20260913.md. All 773 tests
passed before final target-flow assertions, which also pass (105 engine tests).
Full three-layer live acceptance remains incomplete.

V81 genuinely transmitted the complete H1 request (323503 wire bytes, one Fast
meta entry and all 30 reflection actions), so the independent reservation worked.
It remains Fast/Slow 0/0 after controlled interruption: seven completed calls
cost $0.10560228; attempt 8 was interrupted in progress with a $0.0132384
reservation and no settled usage. Do not use V81 as committed history.

The real H1 response deferred all 142 unresolved needs for portfolio capacity
while selecting no hypotheses. Two older tests incorrectly accepted that same
cross-field combination. Capacity deferral now requires the frozen portfolio to
be full; legitimate empty results still require concrete non-capacity reasons.
Prompt guidance distinguishes exact measurement overlap from broad factor-family
overlap and permits source-grounded LLM factors beyond registered deterministic
functions.

Live H1 collapsed all 142 need-source rows to one anonymous source because the
source identity was masked before hashing. Exact replay now retains 24 distinct
source refs and matching opaque source-case refs, without changing local evidence.
Typed retrospective case ids preserve pairing in meta, reflection and method
views. Reflection v4 and downstream method views also receive the owning runtime
counter definitions, including available NEUTRAL versus decisive POSITIVE/NEGATIVE
and the shared paired case pool. This addresses repeated false lessons about
unexplained decisive-subset exclusion; live semantic verification remains pending.
All 771 tests pass. Next: freeze from the committed V77 prefix using this checkpoint
and verify H1 reasoning, reflection interpretation, Mining/Update and promotion.
The three-layer acceptance goal is still incomplete.

V80 was stopped safely at Fast/Slow 0/0 after two completed DeepSeek calls and
an exact-contract diagnostic resume with cached responses. It is not a committed
history source. Restoring original Fast context exposed a second boundary: H1
borrowed the 256000 single-case reservation, while an offline reconstructed H1
view already needs at least 313821 bytes plus reserved output accounting before
all runtime wrappers. Freeze now gives H1 its own configurable, contract-bound
reservation (default 512000); global attempts/cost and semantic gates remain.
Mining track failures are emitted immediately before a sibling continues.

Live stack sampling also exposed repeated whole-oracle parsing during every
append. The 7151-document / 4.2 GB oracle now reuses parsed files only while
complete local file revision metadata is unchanged; new/changed files still
undergo full validation and cross-path replay checks. Measured initial load is
15.73 seconds and unchanged refresh 0.21 seconds. Exact-literal identity scan
uses an equivalent substring precheck and invocation-local string cache; actual
26937-alias H1 replay scans in 3.84 seconds. Full context projection is 47.68
seconds versus 69.45 previously. Identity inventory and evidence are unchanged.
All 769 tests pass, including same-size/mtime-restored tamper detection, scanner
cache boundaries, independent H1 budget identity and immediate H-track failure.
Reflection still contains a known semantic contradiction in V80 (calling 4 vs 4
a difference); prompt guidance alone did not prove correctness. Next live run
must verify restored H1 transmission, meaningful Mining/Update, and reflection
logic. The three-layer acceptance goal remains incomplete.

V79 received explicit payload-level DeepSeek authorization and completed four
real calls before a controlled interruption at Fast/Slow 0/0. It is uncommitted
diagnostic evidence, not an import source. Cross-version payload review found
that V66 and later slow-only imports dropped the original Fast meta/backlog,
while V65 retained them. The new v2 Slow history snapshot recovers Fast context
through the hash-bound legacy chain, preserves it transitively, restores it only
in memory, and seeds repeat backlog refresh without fabricating Fast checkpoints.
Exact V77 source replay now projects one meta entry, all 30 reflection actions
and 145 open needs; the local Fast pointer and persisted Fast meta remain zero.
Reflection now uses the curated aggregate identity inventory without deriving
ambiguous brands that corrupt protocol refs or metric words. Its prompt leaves
aggregate recounting to runtime artifacts; semantic review remains required.
All 766 tests pass, including transitive import, repeated backlog refresh,
source-drift rejection and first-call identity/reference preservation. Next:
freeze a successor from this checkpoint, execute authorized Slow and inspect
actual H1, reflection, Mining/Update measurements and committed results. The
three-layer acceptance goal remains incomplete.

Post-V78 local boundary review found an obsolete 240-character ceiling in the
E1-to-E2 companion-record projection, despite directly cited E1 literals already
allowing longer source records. A failing regression reproduced silent loss of
the other period; the repaired projection preserves it under the existing
packet/view bounds. Integration coverage follows two financial pairs and a
narrative literal through both role parsing and terminal recovery into E2, with
no clipping or duplicate records. Exact V77 inspection found 127 structured
records, maximum 161 characters, so this latent defect did not cause V77's zero
Mining. External payload authorization is still pending; local verification
does not establish live yield or complete the goal. All 766 tests and repository
lint pass. V78 remains zero attempts / zero cost and Fast/Slow 0/0.

V78 is frozen at contract `b85f64b6...e2798` on code checkpoint `e9293b8`,
importing V77's committed prefix in `slow_only` mode (zero Fast rounds, at most
two Slow cycles, 200 model attempts / $5 and 400 acquisition reservations).
The first source-read request `717075e1...39cf2` is scoped to reflection;
its 332,400-byte Responses body has matching stored/recomputed hashes, byte
length and normalized logical/wire messages. The provider input contains opaque
source refs and hashes with no checked workspace paths. No transition journals
were imported. Execution was rejected by automatic approval review before launch
because it requires explicit payload-level authorization for project history,
reflection/prompts and source evidence sent to `https://api.deepseek.com/responses`.
The ledger has zero attempts / zero cost and authoritative Fast/Slow pointers
remain 0/0. Do not bypass the rejection. Saving this audit advances HEAD, which
the runtime checks exactly, so preserve V78 as zero-call evidence and freeze a
successor from the final checkpoint after payload authorization. All 765 tests
and lint passed before freezing.

V77 committed Fast 0 / Slow 1 with 19 completed model attempts, `$0.1497454`,
74 acquisition reservations and 123 lower-level data requests. All sixteen E1
cases survived, E2 compared its frozen 4+4 group, and Update produced three
candidates with complete paired measurements; all three were rejected. Registry
v2 stayed unchanged and Mining remained zero, so this is not goal acceptance.

The post-run whole-chain audit reproduced a source-projection defect: repeated
generic business/risk wording outranks actual operating figures in queryless
filing windows. The recurring concept inventory also counted raw records rather
than distinct comparable cases, while the prior two-structured-observation cap
prevented E2 from receiving a second financial comparison. The repaired view
ranks distinct substantive terms across the shared filing alias family, counts
distinct paired cases with existing concept-priority tie breaks, and permits up
to four structured observations plus required narrative within the existing
six-slot budget. Terminal recovery preserves independently grounded additional
records. Exact V77 inventory replay shows ranking alone does not change its
dominant share-count pair; the second-comparison capacity is therefore necessary
to test live rather than claiming the ordering fix solves mining yield.
Local regressions cover repetition, foreign/current filing aliases, duplicate
documents, late paired records, and second-pair preservation through role parsing
and terminal recovery. All 765 tests and repository lint pass; a fresh V78
successor remains pending for real Mining/Update and content acceptance.

V76 remained uncommitted at authoritative Fast 0 / Slow 0 after 21 completed
model attempts, `$0.17405584000000002`, 119 acquisition reservations, and 200
lower-level requests. Reflection and H1 completed, E1's new source-mix rule
produced grounded structured+narrative signatures for eleven cases, and Update
produced two candidates with real paired measurements. But five E1 cases lost
their otherwise-visible comparison pair after correction exhaustion, leaving too
few grounded members in one fixed group, so E2 was correctly not called. The
cycle then reached a candidate transition and stopped fail-closed with `Signal
transition replay identity mismatch`: V75's workspace-local `.transitions`
journals had been copied into V76 as if they were stable Signal definitions.
Locked Test stayed sealed and no cycle/result pointer advanced.

Both defects are repaired generically. The E1 terminal catch now reconstructs
only the exact runtime-selected two-record source pair plus an existing valid
narrative observation, or one complete already-masked bounded source excerpt when
the model supplied none. It emits an explicit projection summary and never clips,
paraphrases, or invents a fact, so an isolated extraction failure cannot erase a
fixed cohort member. Slow-history export excludes `.transitions`; immutable Signal
versions and their learning streams remain imported, while each successor owns
its cycle-numbered control journals. Three focused regressions and the 232-test
Slow suite pass. V76 must not be resumed or imported; full tests/lint and a fresh
successor remain pending.

The first V76 freeze stopped locally with zero external calls because V75's first
real promotion made its current Registry v2 while its contract-bound Fast learning
events correctly remain attached to immutable v1 Signal refs. Slow-history export
had enumerated only current manifest versions, so it could not find those v1 event
files and falsely reported history drift. Export now enumerates and validates every
immutable version directory, compares imported events against their exact historical
refs, and still requires the current Registry snapshot to equal the committed cycle
pointer. A promotion-shaped transitive-history regression passes; V76 must be
refrozen from the new checkpoint.

V75 committed two real `slow_only` cycles at authoritative Fast 0 / Slow 2
under contract `5b0f0682...12a92`. All 129 model attempts completed for
`$0.6126526`; the run reserved 207 acquisition units (361 lower-level requests),
kept Locked Test sealed, and advanced Registry v1 to v2. Cycle 1 reflection
processed 12/575 units into 12 episodes/one lesson. Cycle 2 processed 12/573
available units into 12 episodes/four lessons; its selected input begins with the
committed cycle-1 terminal result, validation, both effectiveness records, H1
audit, Update summary, and lessons. This proves the rejection/effectiveness
feedback crossed the commit boundary into the next reflection and downstream H1.

Update was nonzero in both cycles. Cycle 1 produced and correctly rejected
`max_drawdown_1y:v2` and `cash_reserves:v2`. Cycle 2 produced two candidates;
`max_drawdown_1y:v2` regressed, while `financing_listing_action:v2` improved
availability without worsening the measured 2/3 directional quality, passed the
paired gate, and was promoted. The final persisted result binds Registry v1→v2
and hash `3626e59e...606ec0`. Mining nevertheless remained zero in both cycles,
so the new-Signal goal is still `unmet` and V75 is not final acceptance.

Exact E1 inspection identifies a general search-allocation defect: although each
packet carried structured and narrative evidence, the six observation slots were
filled by three already-catalogued XBRL pairs because the prompt globally
prioritized recurring concepts. E2 consequently saw only old primitives and its
no-candidate rationale also restated an incorrect model-authored group count.
E1 now requires the first two-record comparable pair but, whenever narrative text
is visible, caps structured observations at those two and requires at least one
literal narrative observation. Bounded correction enforces the mix; final
recovery can only remove excess structured observations and record a technical
gap, never invent source content. E2 may no longer restate aggregate group counts,
whose exact refs remain runtime-owned. The staged Slow progress event now carries
the actual validated/promoted fields instead of rendering fabricated empty
results. The Slow-focused regression suite passes; full-suite/lint and a fresh
V76 live successor remain pending.

V74 was safely interrupted at authoritative Fast 0 / Slow 0 after its entry
reflection exposed a contradictory anonymity boundary. The corrected feedback
ordering worked: its selected provider payload began with the V73 terminal result,
validation summary, both candidate-effectiveness records, role audits, and lessons.
Those effectiveness records still contained real `case_id`/CIK values, however,
while the reflection adapter rejected the same cycle-wide aliases in structured
output. DeepSeek consequently copied two supplied CIK values into otherwise useful
reflections and exhausted both bounded corrections. The failed memory delta
processed zero of 575 feedback units and retained all 575 pending. Independent
siblings continued through an evidence-based E2 `no_measurable_pattern` conclusion
and three Update targets; once the reflection failure made semantic acceptance
impossible, the old-code run was interrupted pointer-safely after 63 attempts
(61 completed, two failed), `$0.23902228`, 130 acquisition reservations, and 232
lower-level requests. It remains resumable but must not be resumed or imported as
committed history.

Reflection v3 now keeps the committed local catalog immutable while deep-masking
the provider projection with the exact same frozen alias inventory used by output
validation. Opaque refs, hashes, metrics, gate reasons, ordering, and local
processed/pending ownership remain unchanged. This removes the impossible
copy-evidence-versus-leak-validation choice without weakening fail-closed output
checks or adding case-specific exceptions. The protocol/work identity was bumped
to prevent stale response reuse. Four focused reflection regressions, all 759
tests, and repository lint pass. A fresh V75 must live-verify the masked request,
successful reflection and downstream action, nonzero Mining and Update, and a
validated/promoted Registry transition.

V73 committed one real `slow_only` cycle at authoritative Fast 0 / Slow 1 under
contract `0017202e...c6c25`. All 73 model attempts completed for
`$0.28816927999999997`; the run reserved 149 acquisition units (315 lower-level
requests), kept Locked Test sealed, and left Registry v1 unchanged. Reflection
processed twelve of 537 units into twelve episodes/four lessons. All four E1
microbatches completed without quarantine, and exact E2 wire inspection confirms
the known dated month, bare press-release, and Exhibit-only 6-K administration is
absent. E2 honestly compared 4+4 fixed cases and returned insufficient evidence.
Update produced `cash_reserves:v2` and `financing_listing_action:v2`; real paired
evaluation rejected both for no strict gain or measured regression. Mining,
validation, and promotion remain zero, so the goal is still `unmet`.

V73 is nevertheless not full information-flow acceptance evidence. Its entry
reflection cap selected the imported cycle's first eleven experiment outcome units
plus one nested input row before later validation/effectiveness units. The resulting
H1 request falsely said the rejected updates had no recorded criteria, although the
committed validation artifact contains exact rejection reasons and paired metrics.
Reflection selection now orders complete units first by newest cycle and then by an
outcome-independent provenance/stage priority: terminal result, validation summary,
effectiveness/fixture evidence, and role audits precede redundant experiment/input
projections. It never ranks by favorable or unfavorable content; whole-entry,
64-KB/12-unit, pending, and typed-read limits remain intact. A zero-call replay over
V73's exact frozen catalog includes the result, validation summary, both candidate
effectiveness units, and relevant audits in 63,945 bytes. Four focused regressions,
all 758 tests, and repository lint pass. V73 will not run cycle 2; a fresh successor
must live-verify gate-reason reflection into H1/E/Update, nonzero Mining, and a
validated/promoted Registry transition.

V72 committed one real `slow_only` cycle at authoritative Fast 0 / Slow 1 under
contract `9f63d507...9a591`. All 61 model attempts completed for `$0.27598144`;
the run reserved 169 acquisition units (340 lower-level data requests), kept
Locked Test sealed, and left Registry v1 unchanged. Reflection processed twelve
of 499 units into twelve episodes/four lessons and preserved 487 pending. E1 ran
all sixteen candidate cases: the first three microbatches satisfied the recurring
pair requirement after one correction, while the fourth exhausted correction and
the deterministic fallback removed one nonliteral observation without losing its
valid siblings. E2 then compared a fixed 4+4 cohort. Update produced
`max_drawdown_1y:v2` and `cash_reserves:v2`; both received real paired evaluation
and were rejected for no strict gain. A third financing target remained invalid
after bounded correction and was isolated. Update is nonzero, but Mining,
validation, and promotion remain zero, so the goal is still `unmet`.

V72 is not semantic acceptance evidence. Exact E2 inspection shows positive
case-005 still contributed two generic 6-K statements that merely say a press
release was issued and attached as Exhibit 99.1. E2 explicitly counted those
press-release references in its no-pattern rationale. The existing filter covered
the bare dated sentence but not the standard exhibit-attachment suffix. The same
generic template family now covers that suffix while retaining literals that state
a substantive event such as a merger. This is form-level, not issuer/case-specific,
and still operates before labels are revealed. Three focused regressions, all 757
tests, and repository lint pass. V72 will not run cycle 2; a fresh code-bound
successor must live-verify clean E2 inputs and produce nonzero Mining plus a
validated/promoted Registry transition before acceptance.

V71 committed one real `slow_only` cycle at authoritative Fast 0 / Slow 1 under
contract `ca368445...e39aa`. It made 78 Slow attempts (77 completed, one failed)
for `$0.29732332000000017`, reserved 141 acquisition work units, kept Locked Test
sealed, and left Registry v1 unchanged. Its entry reflection successfully bounded
459 available feedback units to twelve complete processed units, twelve episodes,
and four lessons while preserving 447 pending. E1 ran four microbatches over all
sixteen candidate cases, and E2 compared a fixed four-positive/four-control cohort.
Update generated three candidates and evaluated every one on real paired inputs;
all three were correctly rejected for no measured net gain. Thus Update is nonzero,
but Mining, validation, and promotion remain zero and the goal is still `unmet`.

Exact V71 E1/E2 inspection found one remaining semantic defect: case-013 was marked
grounded only by generic 6-K month/press-release administration even though its same
packet exposed two-period Company Facts for recurring inventory concepts. This let
boilerplate occupy a fixed induction slot and weakened the cross-case comparison.
The repaired E1 contract now deterministically identifies the first recurring
inventory concept with two visible records and requires both exact records. The
ordinary bounded correction receives the complete obligation. If it is still
violated, a controller-only terminal catch empties only that case, records a
technical extraction gap, preserves valid siblings, and permits only the previously
frozen same-group fallback; model-authored gap text cannot bypass the requirement.
Generic 6-K month and bare press-release templates are also filtered before label
reveal while substantive continuations remain. Six focused regressions, all 757
tests, and repository lint pass. V70 remains zero-call invalid preflight evidence;
V71 remains immutable and will not run cycle 2. A fresh code-bound successor must
live-verify this repair and produce nonzero Mining plus a validated/promoted Registry
transition before acceptance.

V69 committed one real `slow_only` cycle at authoritative Fast 0 / Slow 1. It
made 57 Slow-side attempts (53 completed, four failed) for
`$0.21920948000000007`, reserved 134 acquisition work units, kept Locked Test
sealed, and left Registry v1 unchanged. Its exact E1 payloads live-verify the
Company Facts repair: duration records are now paired only year-over-year or
across comparable quarter/YTD lengths, never quarter-to-full-year. E1 grounded
all eight selected cases with no quarantine. E2 then honestly found no recurring
measurable contrast in its fixed two-positive/two-control cohort. Update produced
`max_drawdown_1y:v2`, which the paired gate rejected for worse measured directional
quality. Mining, validation and promotion remained zero, so the goal stayed
`unmet`.

V69's entry reflection failed safely after its initial response and two bounded
corrections reached the fixed 5k output ceiling. The input selected 34 complete
feedback units and assigned up to 34 episode slots, so this was a predictable
input/output budget mismatch rather than an exotic malformed response. No
feedback was consumed, all 441 units stayed pending, and independent H1/E/Update
continued. Reflection selection is now output-aware: it takes at most twelve
complete units, prioritizes the immediately preceding committed cycle, keeps the
remainder pending, and applies the same cap to a typed source replacement. The
ordinary failed-delta catch remains fail closed. Production exploration now uses
four grounded induction cases per class, with two issuer-disjoint validation
cases per class, so E2 has room for recurrence and counterexamples instead of
making a cross-case judgment from two members per group. Four focused regressions,
all 754 tests, and repository lint pass. V69 remains immutable; V70 must live-
verify bounded reflection, a 4+4 E2 cohort, nonzero Mining, and a validated/
promoted Registry transition.

V67 cycle 1 committed at authoritative Fast 0 / Slow 1 under the new paired-input
and source-diverse E1 implementation. It made 47 completed Slow-side attempts for
`$0.19898368000000002`, reserved 144 acquisition work units, never entered Fast,
kept Locked Test sealed, and produced three Update candidates. The paired gate
now resolves and executes all eight check cases in both arms with zero execution
failures; `max_drawdown_1y:v2` and `cash_reserves:v2` were rejected for measured
non-improvement rather than infrastructure failure, while
`financing_listing_action:v2` failed its unchanged fixture. This live evidence
verifies the common-corpus materialization and per-case diagnostics.

Mining was still zero because both E1 microbatches failed before transmission:
the neutral comparison inventory field `source_label` was conservatively caught
by the outcome-key scanner as an evaluation label. The source packets themselves
were correctly materialized with both required families and two to four documents
per case. The inventory now uses the typed neutral name `source_display_name`, so
the strict outcome scanner remains unchanged and no path-specific exception is
added. The exact scanner and inventory regressions, all 752 tests, and lint pass.
V67 remains immutable; a code-bound successor must live-verify E1/E2 and produce
nonzero Mining plus a conclusive Update before acceptance.

V66 is the first two-cycle `slow_only` successor that preserves the replayed
Fast learning profiles and commits both cycles at authoritative `round=0/cycle=2`.
It made 101 Slow-side DeepSeek attempts (99 completed, two failed) for
`$0.44161012000000005`, reserved 281 bounded acquisition requests, never entered
a Fast stage, kept Locked Test sealed, and left Registry v1 unchanged. Cycle 2
reflection consumed nine cycle-1 result units into nine episodes/four lessons,
and its H1 request explicitly used the prior no-pattern/provisional/update-failure
facts, proving the reflection-to-action handoff. Both cycles still produced zero
Mining candidates. Update produced two candidates in cycle 1 and one in cycle 2,
but paired validation reported both arms as unexplained execution failures; the
second cycle also tried to create a conflicting `max_drawdown_1y:v2` instead of
re-evaluating the existing provisional candidate. Exact E1 requests show why
independent Mining was starved semantically: queryless resolution declared one
arbitrary filing sufficient, so seven of eight cases lacked structured comparable
facts and E2 received isolated issuer narratives.

The three general defects are repaired locally and reflected in the owning specs.
Paired effectiveness now materializes both current/candidate input contracts via
the authorized resolver before freezing their common PIT corpus, binds the acquired
documents into the evaluation identity, and persists per-case arm diagnostics.
Queryless E1 requires financial and filing source families when both are available
and receives a value/identity/outcome-free inventory of recurring source concepts.
A later cycle reuses an immutable provisional vNext on a new check identity rather
than asking for a conflicting same-version definition. Six targeted regressions,
173 focused tests, all 752 tests, and repository lint pass. V66 remains immutable;
a fresh code-bound `slow_only` successor is required for nonzero Mining and a
conclusive Update evaluation/promotion.

V65 replayed one immutable committed Fast range into a real zero-Fast
`slow_bootstrap` cycle under contract `69aa0952...eb2a` and committed at
authoritative `round=0/cycle=1`. Ten DeepSeek attempts completed for
`$0.046635680000000006`, with 183 acquisition records; Locked Test stayed
sealed, H1 and independent E both ran, and Update produced the nonzero
`max_drawdown_1y:v2` candidate. The candidate stayed provisional because only
one of eight fixed check cases had available market data, so Registry v1 did
not change; Mining still produced zero candidates and goal remained `unmet`.
Exact response audit found H1 semantically over-grouped 142 different unmatched
needs into one deferred row and E2 then honestly found no recurring literal
pattern. It also exposed two general continuation defects now repaired locally:
`slow_only` history filtered out bootstrap-imported learning events solely
because the target Fast pointer is zero, and an otherwise-valid Update correction
could be rejected for surplus declarative `changed_paths`. History export now
propagates only contract-bound imported events plus pointer-committed local
events, verifies them byte-for-byte against the source Registry, and excludes
unbound ledger rows. After bounded model correction, Update may normalize only
the exact deterministic diff metadata and must rerun the complete candidate and
fixture parser. The two new regressions, 204 focused tests, all 748 tests and
repository lint pass. V65 remains immutable; a fresh `slow_only` successor is
required for live cross-cycle reflection and nonzero Mining/promotion evidence.

V62 committed two real successor cycles under contract
`76616835...5006` at authoritative `round=0/cycle=2`. It used 23 model
attempts (22 completed, one failed), 99 data requests and `$0.19435864`, kept
Locked Test sealed and Registry v1 unchanged, and again reported zero
candidate/validated/promoted/updated Signals with goal `unmet`. Cycle 1 memory
successfully processed 28 refs into six episodes and four lessons. Cycle 2
selected all five required local cycle-1 refs, and the adapter correctly sent
the complete coverage correction, but DeepSeek used a fourteenth episode id
after all 13 runtime slots were occupied; bounded correction therefore ended in
an otherwise-grounded overflow row and the memory delta failed without consuming
any refs. Both E1 batches in both cycles also retained grounded sibling
observations but quarantined several byte-exact source records solely because
their complete literal exceeded the arbitrary 240-character ceiling, materially
weakening E2 before its no-pattern result. Reflection correction now states the
remaining-slot authority and deterministically merges only an otherwise-valid
overflow episode after bounded retries, preserving authored text/questions/refs
and rerunning the complete parser. E1 now accepts any complete contained literal
with at least two visible tokens under the existing request/output budgets. The
new exact regressions and both focused modules pass (168 tests); V62 remains
immutable and a fresh successor with a learned-profile-bearing source Registry
is required to exercise nonzero Update as well as repaired Mining.

V61 committed two real cycles under contract `59bb2450...c908c0` at
authoritative `round=0/cycle=2`, using 20 attempts (17 completed, three failed),
93 SEC requests, and `$0.11558708000000001`. Both cycles ran H and independent
E, kept Locked Test sealed and Registry v1 unchanged, and reported zero
candidate/validated/promoted/updated Signals with goal `unmet`. The bounded
method-memory repair succeeded live: both H1 requests fit and were transmitted;
cycle 2 used two bounded H1 calls instead of pausing at preflight. However V61
is not accepted as a complete cross-cycle learning proof. Cycle 2 correctly
reserved 13 complete entries including all five local cycle-1 refs, but its
reflection output covered only eight owners after deterministic nested-ref
canonicalization and omitted five selected historical owners. Because complete
coverage was checked only after the role adapter had declared success, no
correction call was available; the final engine guard sealed memory as failed,
consumed no refs, and H/E continued safely. Coverage validation now runs inside
the adapter and emits one correction obligation containing every omitted ref;
the engine equality check remains the final catch. All 744 tests and lint pass;
V61 remains immutable and a fresh successor is required.

V59 froze under contract `e4f76cb2...9d5bd` and committed a content-audited
cycle 1 at authoritative `round=0/cycle=1`. Cycle 1 used eight attempts
(seven completed, one failed) for `$0.05596668`, processed all 28 selected
feedback refs into six covering episodes and four lessons, persisted 23 nested
canonicalizations, and produced zero candidate/validated/promoted/updated
Signals with Registry v1 unchanged and goal `unmet`. H stopped honestly at
14/16 ready profiles; both E1 microbatches retained quarantined technical
failures; E2's runtime-owned two-positive/two-control map and no-pattern prose
were consistent. Cycle 2 then proved the recent-frontier repair before pausing:
all five `slow:1:*` required refs were among 11 actually processed refs. It did
not commit because the complete H1 request reserved 285,081 bytes against the
frozen 256,000-byte request ceiling; the engine misclassified that isolated
role-size failure as run-wide budget exhaustion and canceled E. Derived method
memory is now projected as complete newest-first, episode/lesson-interleaved
entries under a separate 64 KB ceiling instead of embedding unbounded memory
deltas. Any remaining H1 oversize is a zero-call local failure that preserves
independent E, while true run budgets and transport failures still propagate.
The exact V59 memories shrink from more than 218 KB of stored deltas to a
28,467-byte complete-entry view with all 25 entries retained. All 743 tests and
lint pass; V59 remains immutable and a fresh successor contract is required.

The first successor freeze attempt, V60, made zero external calls and stopped
before contract creation because V59 retains a staged active cycle after its
committed cycle 1. History construction incorrectly required `active_cycle` to
be null instead of following the committed pointer. It now ignores only a
strictly higher active cycle, requires all five artifacts for every committed
cycle, and verifies that the live Registry exactly matches the version/hash at
the committed cycle pointer. This permits a pointer-reachable committed prefix
without importing staged files, while still rejecting a post-promotion,
pre-pointer Registry or inconsistent active id. All 743 tests and lint pass;
V60's partial zero-call directory is diagnostic only.

V57 executed and committed two real `slow_only` cycles under contract
`3b7f85ca...587af` at authoritative `round=0/cycle=2`. All 18 model attempts
settled successfully for `$0.14368368000000004`; Locked Test stayed sealed,
Registry v1 remained unchanged, and both cycles reported zero
candidate/validated/promoted/updated Signals with goal `unmet`. Cycle 1
processed 28 feedback units and persisted 23 nested-ref canonicalizations;
cycle 2 processed nine units and persisted nine mappings. H1 remained grounded,
both E1 batches in each cycle retained explicit partial technical failures, and
Update made no unsupported candidate. V57 is execution-complete but not
content-accepted: cycle-2 E2 prose assigned `case-006` to both labels despite
the runtime-owned disjoint label map, and cycle-2 reflection received five
cycle-1 feedback units but processed only older imported backlog. E2 now forbids
free-text case/label assignment and persists runtime-derived positive/control
refs separately. Reflection now reserves the immediately prior locally committed
cycle's complete units ahead of old backlog and prevents the optional source
selector from evicting those that fit. All 742 tests and lint pass; V57 remains
immutable and a fresh successor contract is required.

P6 follow-up audit narrows the earlier “confirmation infrastructure” claim.
`SlowMemoryAblationManifest` and `ConfirmationCohortLedger` can validate a
precomputed three-condition group and reserve issuer-isolated confirmation
cases, but no production path currently generates the `no_memory`,
`episodes_only`, and `episodes_and_lessons` conditions or freezes their
candidate/validation/promotion/unavailability/cost outcomes. The existing unit
tests instantiate placeholder hashes directly. Therefore P6 is a local schema
and reservation scaffold, not an executable ablation or evidence of method
benefit. Thresholds and confirmation cases remain deliberately unfrozen pending
the explicit research-protocol decision required by the plan.

V56 committed one real cycle under contract `2f6f1af7...44bbe` at
authoritative `round=0/cycle=1`. It used 11 reserved attempts, including one
retryable SSL failure and one truncated structured response, with settled cost
`$0.06805092`; 28 feedback units were processed into 28 episodes and four
lessons while 62 remain pending. H1 returned a grounded one-call
`no_testable_hypothesis`; both E1 microbatches ended in explicit partial
technical failure; E2 corrected its initial unsupported gap claims to exact
case-scoped canonical citations. Locked Test stayed sealed, Registry v1 was
unchanged, and all candidate/validated/promoted/updated counts remained zero.
The cycle is not accepted as the first of the required two-cycle proof because
the adapter's unique nested-ref canonicalization map was present only in the
runtime `AgentStep` and missing from the persisted memory audit. The engine now
stores it under `slow_memory.model_view_manifest.canonicalized_nested_refs` and
rejects mappings whose owner was not processed. All 740 tests and lint pass;
V56 remains immutable and a fresh successor contract is required.

V55 committed one real cycle under contract `55a4f0f6...42f90e` at
authoritative `round=0/cycle=1`. It used seven settled model attempts, 31 SEC
acquisitions, kept Locked Test sealed and Registry v1 unchanged, and reported
zero candidates/validated/promoted/updated Signals with goal `unmet`. H1, both
E1 microbatches, and E2 each completed in one request; E1 had no quarantine and
E2's two-positive/two-control no-pattern rationale is supported by the literal
signatures. Content acceptance still stops before cycle 2 because reflection
failed: aggregate validation exposed six invalid episodes and four invalid
lessons at once, but the correction repeated nested historical locators. Exact
ownership inspection found 44 out-of-scope refs, 43 occurring under exactly one
selected top-level wrapper and one absent from the current view. Reflection now
canonicalizes only those uniquely owned nested Slow refs to their wrapper,
deduplicates them, records the mapping, and still rejects absent or ambiguous
refs. The raw provider response remains unchanged. H1 also now rejects V55's
new wording that the candidate roster/source excerpts are absent. All 739 tests
and lint pass before another fresh contract.

V54 committed one real cycle under contract `42a97f65...e97c` at authoritative
`round=0/cycle=1`, with nine settled model attempts, 30 SEC acquisitions,
Locked Test sealed, Registry v1 unchanged, and all Signal counts zero/goal
`unmet`. Reflection v2 succeeded on its first final request: 18 selected feedback
units became 18 episode reflections plus four lessons, while 28 deferred units
remain pending. E2 also completed in one request; its exact no-pattern rationale
matches the four supplied literal signatures and uses only canonical case-scoped
gap citations. V54 is nevertheless stopped before cycle 2 because H1's initial
response treated history locators as runtime need aliases. Aggregate validation
correctly listed all eight contaminated disposition rows but omitted the same
invalid refs in `no_hypothesis`; the model's otherwise-correct empty-ledger
repair changed that linked terminal object and was rejected by scoped recovery.
H1 now includes unknown/duplicate terminal refs in the same correction frontier
and permits the complete linked `no_hypothesis` repair. The exact pattern is
covered by regression; all 737 tests and lint pass before a fresh successor.

V53 committed one real successor cycle under contract `3f485d0b...a6fa` at
authoritative `round=0/cycle=1`, after same-contract recovery from a retryable
SEC provider error at `case-031`. It used 13 model attempts, preserved five
granular H1/E1/E2/Update experiments, kept Locked Test sealed and Registry v1
unchanged, and again reported all four Signal counts as zero with goal `unmet`.
It is not content-accepted and did not proceed to cycle 2. Exact response audit
found two new general defects: the first gap matcher treated an observed theme
being absent from one label group as missing source input and forced two needless
E2 corrections; entry reflection exposed nested historical locators in unit
content, then reported only the first invalid episode per correction and failed
after exhausting the bounded retries. The matcher now requires a source-input
noun near the absence marker, while observed cross-group absence is explicitly
allowed. Reflection v2 permits only top-level `feedback_ref` citations and emits
all invalid episode/lesson rows as one indexed correction frontier. Focused
replays, all 736 tests, and repository lint pass; a fresh successor contract is
required.

V52 is the first committed real v8 `slow_only` cycle. Under contract
`4a144686...56b0`, an initial transient SEC SSL EOF was recovered by resuming
the same frozen cohort; cycle 1 then committed at authoritative
`round=0/cycle=1` with Locked Test sealed and Registry v1 unchanged. The live
source-read/reflection path, granular request traces, 60 data-request ledger
rows, H1, two E1 microbatches, E2, and zero-call Update were inspected. Its five
sealed experiment attempts preserve every initial/correction request ref. The
result reports zero new candidates, zero validated or promoted Signals, zero
updates, and `signal_goal_status=unmet`.

V52 is execution evidence but fails content acceptance. Its final E2 rationale
claimed that supplied gaps explicitly named missing full-year cash-flow/revenue
figures and partial contexts. The selected signatures actually named one
cash-flow-statement gap and several unrelated truncation gaps; none named a
revenue-figure gap. The run stopped before cycle 2. E2 now accepts a concrete
source-absence statement only as `[case_ref] ` plus one verbatim supplied
`evidence_gaps` item; generic insufficiency conclusions remain valid. The exact
V52 response is covered by a correction replay, alongside a canonical-citation
acceptance test. All 734 repository tests and lint pass. V51 remains an immutable
incomplete predecessor: its reflection
completed, then its data-disabled contract paused before the Slow profile.

V50 froze the first post-unitization v8 `slow_only` request under code checkpoint
`17c734a`. Its cycle-1 input contains all 11 imported V45 work units; the exact
reflection view includes 9 complete units in 52,951 bytes and defers two complete
Update targets. The persisted logical request and 57,006-byte DeepSeek wire body
recompute to their recorded hashes, retain original source artifact hashes and
JSON locators, expose no Locked Test data, and contain no API credential. A first
execution attempt was blocked by the local network sandbox and durably recorded
as one failed attempt at zero settled cost; the elevated transmission was then
rejected before sending because the internal historical research payload needs
DeepSeek-specific informed consent. Pointers remain authoritatively
`round=0/cycle=0`. The [completion audit](slow-round-self-evolution-completion-audit-2026-09-12.md)
also identified two local spec/code gaps before a successor run. Both are now
repaired after V50: typed one-round `read_source_refs` selection is limited to
role-scoped opaque refs and whole-entry replacement, with unselected refs kept
pending and no access for E1/executor/predictor; transport request traces now
survive success and bounded structured failure, and the sealed index has distinct
H1/H3 jobs, E1 microbatches, E2 comparisons, Update targets and candidate
validations. V50 is
immutable diagnostic evidence, not a completed cycle. The new source-read and
granular-attempt implementation passes all 732 tests and repository lint before
freezing a successor.

V49 then verified the repaired history projection at zero calls: its first
`slow_input.json` carried source Slow cutoff 1 and both V45 committed artifacts.
The preflight also proved those legacy monolithic files (about 139 KB each) were
too large to enter the 64 KB whole-entry reflection window, so they remained
pending and no reflection call occurred. Runtime now projects validation/result
history at complete H, E, Update target, candidate-evaluation and transition
boundaries, each with the original artifact SHA-256 and JSON locator; it applies
the same unitization to newly committed target cycles. Against the exact V45
files, 9 of 11 units fit the first view (52,951 bytes) and the two deferred Update
targets fit the next view, leaving room for new-cycle summaries. All 728 tests
and lint pass. V49 remains immutable zero-call evidence and must not resume under
the changed code revision.

V48 froze the first v8 `slow_only` contract from V45 and stopped locally with
zero external calls at `round=0/cycle=0`. Its preflight exposed that the
validated history manifest copied committed V45 validation/result artifacts,
but the target cycle projected only its own zero pointer and therefore produced
`feedback_count=0`. Runtime now verifies and projects every namespaced imported
artifact from its local immutable copy, includes the source committed Slow
cutoff, and rejects missing, path-escaping, hash-mismatched, duplicate, or
incompletely manifested feedback. The exact regression plus 727 full tests and
repository lint pass. V48 remains immutable diagnostic evidence; a fresh v8
contract is required before authorized external execution.

The [Slow self-evolution implementation plan](slow-round-self-evolution-implementation-plan-2026-09-12.md)
is now local-ready. Runtime v8 freezes `slow_input.json`, append-only
`slow_memory.json`, and `slow_experiments.json` in an exact lineage before
validation/result and advances only the committed cycle pointer. Neutral,
issuer-disjoint dev/check samples are frozen before research; H and independent E
run every cycle; H1 v7 routes explicit updates; H1/H3/E2/Update receive bounded
whole-entry method-memory evidence views; and `slow_only` imports only validated
committed history while preserving a zero Fast pointer and cumulative cycle cap.
Candidate validation now rejects known definition/implementation mismatches and
rename-only execution duplicates. Results and CLI diagnostics separately expose
new candidate, validated, promoted and updated counts plus the consecutive unmet
Signal goal. A frozen three-condition memory ablation manifest and issuer-isolated,
group-bound confirmation reservation are available for later independent review.

Scripted two-cycle `slow_only` coverage confirms cycle 2 reads cycle 1 committed
feedback without moving the Fast pointer. Focused and full local verification are
recorded in the 2026-09-12 changelog entry. No new workspace was frozen and no
external model/data request was transmitted: exact wire review, real consecutive
Slow execution, per-cycle Signal-output acceptance, and independent method-benefit
confirmation remain pending explicit external authorization and a confirmed
research protocol. V47 and every older frozen workspace remain immutable.

V45 completed one real DeepSeek Slow cycle at authoritative `round=0/cycle=1`
after 42 completed external attempts and `$0.20322316`; Locked Test remained
sealed and Registry v1 stayed unchanged at 14 stable Signals. Exact E1/E2 content
inspection supports E2's `insufficient_evidence` result: its two positive and two
control cases retained literal source spans and explicit labels, but only one
positive had comparable revenue growth while the other exposed non-comparable
periods, so no repeated positive/control factor was established. This supersedes
the earlier uninspected V30/V31 no-candidate assertion: a domain-empty result is
accepted only after inspecting its actual comparison content.

V45 still fails semantic Slow acceptance because H1 did not produce a trustworthy
ledger. Its first response pooled 142 heterogeneous `unmatched_signal_need` refs
under `guidance_acceleration:v1`; the first correction fixed the plural field but
retained that false coverage claim, and the second correction reintroduced the
singular field. The runtime correctly recorded structured-recovery exhaustion and
continued independent E1/E2 and Update, but the old validator checked only that
the cited Signal existed. Update itself was fail-closed: the new absolute quality
floor rejected `max_drawdown_1y:v2` at 0 correct/5 wrong, `cash_reserves:v2` was
rejected at 1 correct/4 wrong with no gain, and `financing_listing_action:v2`
remained provisional at 0 decisive with three technical citation failures. Its
request and correction payloads contained the full source observations and exact
validation feedback; the model's ignored citation repairs remained technical
failures rather than being laundered into semantic unavailable results.

The V47 boundary used `signal-mining-hypothesis-v6`. It has an honest
`deferred_measurement` state for measurable needs outside the bounded portfolio;
explicitly unmatched Fast needs cannot be marked already covered, and an
existing-Signal update must have a per-need exact basis from either the backlog's
own `signal_ref` or that Signal version's `routing_answer_need_phrases`. The H1
card projection now supplies only those bounded phrases. Grouped rows are checked
per need, row-shape failures are indexed, and the terminal fallback may remove
only a redundant singular `signal_ref` identical to the sole plural value before
rerunning the complete parser. Exact replay of all three V45 H1 responses remains
rejected for the semantic coverage error after the mechanical duplicate is
removed. Exact pre-transmission inspection then rejected V46 at zero calls: its
system instruction was v6 while the runtime payload, fingerprint namespace, and
durable H1 audit still declared v5. Those runtime surfaces now advance together
to v6 and the engine regression asserts the outgoing payload version. All 716
tests and repository lint pass. V47 is now frozen from the same V21 boundary at
contract `b70f2728...23c0b` and paused at zero calls on exact request
`f4768214...210c`. Its system/payload contract is consistently v6; all 175 unique
need refs, 30 reflection actions, 24 masked meta cases, and 14 stable Signal
cards survive in the 246,190-byte wire body. Logical messages equal the actual
wire input, stored and recomputed body hashes match, no truncation marker or
checked company/ticker/CIK/local-path leak is present, and Locked Test remains
sealed. External execution requires V47-specific authorization.

V42 reached the audited H1 approval boundary at `round=0/cycle=0`. The exact
225,829-character H1 context contains 172 unique needs, all 30 reflection actions,
24-case meta-memory, and 14 stable Signal cards; it contains no Kinross/Wynn
brand, ticker, CIK, or local path, and Locked Test remains sealed. The first
sandboxed transmission failed before reaching DeepSeek with `[Errno 1] Operation
not permitted` and was durably classified as retryable rather than semantic
no-candidate. Elevated network execution was then denied because the request
contains meta-memory and development context and later E2 will contain labeled
positive/control samples; specific user authorization for sending that content
to DeepSeek is required before the same frozen request can resume.

V41 reached a genuine zero-call H1 approval boundary, but exact wire inspection
still found `Kinross` and `Wynn` in Fast needs. The row-scoped resolver was
correct; its identity index was incomplete because the Signal engine sampled
Discovery cases while those needs originated from the fixed Anchor cohort.
Signal sampling remains Discovery-only, but the engine now receives a separate
identity-only union of the approved Discovery, Anchor, and Evolution Validation
splits. It contains no outcomes or evidence and still never loads Locked Test.
The regression deliberately puts the source owner outside the sampling cohort
and proves its brand is masked. All 705 tests and repository lint pass; V41
remains immutable at zero calls and requires a freshly frozen successor.

V40 remains a zero-call preflight at `round=0/cycle=0`. Its mining-only probe
showed why a global single-brand inventory cannot be generalized across the full
8,755-case Discovery pool: a target brand `Capital` collided with the stable
Signal context tag `capital_intensive`, and many other ordinary research words
have listed-company namesakes. Aggregate guards therefore return to ids, tickers,
and multi-token names. Before each Fast-derived backlog source ref becomes opaque,
the controller now resolves its exact source case and applies a case-scoped safe
brand inventory to that row, with an immediate row-level assertion. This masks
`Kinross` and `Wynn` in their owning needs without treating `Capital`, `Ready`, or
other protocol vocabulary as identity everywhere. All 705 tests and repository
lint pass; a fresh successor must verify the exact H1 wire body.

V39 also remains at zero external calls and `round=0/cycle=0`. A mining-only
diagnostic exposed the swallowed local H1 failure before the normal pipeline
continued to its first Update approval boundary: the derived target brand
`Ready` collided with the controller-owned canonical applicability token
`all_ready_issuers`. Single-token brand guards now exclude the complete ordinary
query vocabulary and explicit Slow protocol tokens while full names, ids, and
tickers remain guarded. The exact protocol-collision case is regression-tested;
all 705 tests and repository lint pass. A new frozen contract is required.

V38 stopped locally before constructing or transmitting any model request. One
valid Discovery identity consisted only of a legal-suffix token, so stripping the
suffix produced an empty natural name and the new aggregate brand derivation
raised `IndexError`. Brand extraction now handles an empty derived name without
weakening the identity scan. The exact suffix-only case is regression-tested;
all 705 tests and repository lint pass. V38 remains zero-call failure evidence.

V37 stopped at the first exact H1 approval boundary with zero external calls and
authoritative pointers `round=0/cycle=0`. Its 224,234-character user context was
complete and carried all 172 Signal needs, including all 30 reflection actions,
but manual wire inspection found single-token target brands such as `Kinross` and
`Wynn` inside persisted Fast unmet needs. Existing aggregate masking covered
formal names, tickers, ids, and relation aliases but omitted distinctive leading
brands. Aggregate identity inventory now includes such brands while explicitly
preserving ordinary protocol words such as `Future`, `Business`, `Match`, `News`,
`Alpha`, and `Open`; the existing final assembled-payload scan enforces that same
inventory. All 705 tests and repository lint pass; V37 remains immutable zero-call
preflight evidence and a new successor is required.

V36 completed a real DeepSeek Slow cycle at authoritative `round=0/cycle=1`,
but it is rejected as semantic acceptance. Exact H1 input contained all 30
reflection actions and the response did use several of them, yet all three
hypotheses explicitly depended on post-series or after-prediction facts. Its
corrections repeatedly failed because the new-measurement ledger contained refs
not attached to any hypothesis and feedback exposed only the aggregate mismatch,
not the exact set difference. Independent E1/E2 transported exact source spans,
explicit positive/control labels, and source-owned SEC concept metadata without
truncation or model-summary contamination; nevertheless E2 incorrectly claimed
that its visible labels remained outcome-hidden. Update exposed a controller
contradiction: stable executable fixtures legally omit `document_id` and
`published_at`, the clone schema required both, and the validator simultaneously
required those fixtures to remain byte-for-byte unchanged. The repaired contract
now rejects explicit post-cutoff measurements, reports exact H1 ref differences,
adds a bounded source-owned same-concept companion period before E2, rejects
visible-label denial, and makes the clone schema accept the immutable stable
fixtures it supplies. All 704 tests and repository lint pass; a fresh V37 real
Slow acceptance remains pending.

V34 is authoritatively complete at `round=0/cycle=1` but is not semantic Slow
acceptance. Its exact H1 payload carried all 30 projected reflection actions;
the initial answer falsely mapped 142 unrelated Fast needs to every stable
Signal, and its correction then formed three reflection-driven measurements but
used an undocumented `count` value kind, cited existing Signals from
`new_measurement` rows, and pooled semantically unrelated need refs. Because the
validation issue did not authorize the contract-coupled `no_hypothesis` change,
scoped correction rejected that otherwise substantive response and replayed an
identical cached request, so H2/H3 never ran. Independent E1 did surface materially
better filing and Company Facts literals, but E2's deterministic handoff removed
the source-owned concept/label/unit and reduced structured records to anonymous
numbers; its `insufficient_evidence` result is locally correct for that damaged
view, not evidence that no factor exists. Update separately staged
`cash_reserves:v2` and correctly rejected its incompatible fixture while two other
drafts failed executable-fixture preservation. The current repair explicitly
states H1 enums/ref rules and semantic grouping, grants outcome-coupled correction
paths, preserves only unambiguous source-owned Company Facts semantics in E2,
prefers same-concept period pairs, and relation-masks named target affiliates.
V35 then stopped at the zero-call H1 approval boundary when exact-payload audit
found one remaining self-contradiction: the leading system instruction still
forbade `not_testable` for reflection while the output contract and validator
allowed it for an intrinsic measurement-level reason. The correction instruction
also overgeneralized hypothesis-sibling preservation to non-hypothesis ledger
repairs. Both prompt clauses are now aligned; V35 remains immutable at 0 calls and
a freshly frozen successor is pending.

V31 is authoritatively complete at `round=0/cycle=1`, but a content-level audit
withdraws its earlier semantic acceptance. Its E2 wire body matched the persisted
request and was not transport-truncated; however, queryless filing projections
were dominated by SEC cover text, Company Facts projections were too small and
could prefer stale concepts, one JSON window began inside a record, local natural
brands were incompletely masked, and E2 received overclaiming E1 summaries.
Separately, H1 carried outcome-aware reflection but had no contract requiring that
reflection to change downstream action, and it made semantically false
already-covered mappings. Therefore V31's `no_measurable_pattern` is only locally
defensible for a damaged packet, not evidence that the cohort contains no reusable
factor. A v4 repair now makes reflection action refs accountable, improves bounded
queryless projections, applies local-plus-aggregate identity masking, quarantines
filing boilerplate, removes model summaries before E2, and prevents limited
evidence from claiming `no_measurable_pattern`. Fresh live acceptance is pending.
See the [V30/V31 Slow audit](information-evolution-v30-v31-slow-acceptance-2026-09-11.md).

V30 provides the first productive real Slow acceptance from the replayed
committed-Fast boundary. The frozen DeepSeek contract completed at authoritative
`round=0/cycle=1`, kept Locked Test sealed, and atomically advanced the stable
Signal Registry from v1 to v2 by promoting `max_drawdown_1y:v2`. Update staged
both `max_drawdown_1y:v2` and `cash_reserves:v2`; paired issuer-disjoint holdout
validation promoted the former and correctly rejected the latter for no strict
effectiveness gain. Independent Exploration also completed eight label-hidden E1
extractions and the label-revealed E2 comparison, which returned an evidence-
grounded `no_measurable_pattern` rather than fabricating a candidate.

The same run exposed one remaining H1 false rejection: its cash-runway hypothesis
used the source-owned balance-sheet term `short-term investments`, which the
alternative-outcome guard confused with short-term stock performance. The guard
now requires horizon vocabulary to co-occur with an actual outcome concept.
Exact saved V30 H1 output replays to three valid hypotheses after one correction,
while short-term stock returns remain rejected. V31 verified control-flow
continuation into independent Exploration, but not the newly required semantic
information-flow acceptance described above.

Semantic follow-up audit found remaining behavior gaps despite V18 completion:
ordinary Fast unmet needs never enter the Signal backlog; meta inputs sample
4 of 24 cases; Alpha Vantage quota payloads were cached as successful data;
SEC historical/form coverage and structured financial context remain incomplete.
Update also omitted retrieval settings while claiming a skill change that did
not occur. See the [proposed repair execution plan](information-evolution-semantic-repair-plan-2026-09-11.md)
for evidence and semantic acceptance gates, plus the
[function-level MVP actions](information-evolution-mvp-code-actions-2026-09-11.md)
for exact edit sites and regression tests. Full meta is sent directly within
existing budgets; automatic pagination and new platforms are deferred. This follow-up
changed documentation only; no runtime repair or additional live run is claimed.

V18 completed the ordinary real Fast/Slow path at 1/1: one eligible 24-case Plan,
complete reflection persistence, an audited compact H1 view, and 232 reconciled
learning events. E1 retained
valid observations after quarantine and E2 ran. One Update candidate staged but
was falsely blocked by lowercasing `five` into ticker `FIVE`; no promotion occurred.
Post-run repairs reuse strict identity matchers, recognize conditional as-of intent,
and show recent dated records in queryless JSON previews. All 649 tests pass.
Targeted real validation completed under `fed00ec`: all four candidate fixtures
executed (three passed, one legitimate state mismatch); eight E1 cases produced
22 validated observations with repaired previews. Next-Fast meta/profile visibility
and V17 idempotent learning recovery are verified. No Signal promotion is claimed.
See [V18 audit](information-evolution-v18-chain-audit-2026-09-11.md).

V17 completed and committed both 24-case Fast candidates, including exact original,
vertical and horizontal reflection persistence. It then stopped before Slow because
seven repeated same-input Signal observations disagreed across Plans and crashed
profile aggregation. The repair preserves all 529 raw learning events, quarantines
disputed effectiveness observations and rebuilds profiles on idempotent replay.
All 647 tests pass. The original V17 remains at Fast/Slow 1/0; immutable pre-Slow
recovery awaits the architecture clarification required by AGENTS.md. See
[V17 chain audit](information-evolution-v17-chain-audit-2026-09-11.md).

V16 completed real Fast/Slow 1/1 with one eligible 24-case Plan, exact original
reflection-to-meta-to-H1 handoff, and 256 exactly reconciled learning events.
Candidate 2 was rejected after 12 cases; horizontal reflection was not exercised.
Slow produced no validated candidates: E1 citation failures and Update's optional
skill/staging mismatch blocked it. Post-run repairs preserve valid E1 observations,
share Update validation across correction/staging, and normalize temporal tokens.
All 646 tests and lint pass. Fresh Slow acceptance is pending confirmation of the
architecture's bootstrap boundary; completed pointers are not proof of a working
candidate promotion path. See [V16 chain audit](information-evolution-v16-chain-audit-2026-09-11.md).

V15 verified the repaired financing source in an actual DeepSeek request,
accepted SignalResult, final ResearchState and Predictor citation. It was paused
at 0/0 after candidate 1 and 2 stopped at cases 12 and 10: ordinary reflection
reservation failed before the terminal-reserve threshold and exited without
using the reserved terminal envelope. The runtime now retries that reflectable
batch once with mandatory-finalize context, preserving paid usage, state and
evidence. Exhausted or non-finalizing recovery remains ineligible. V16 will use
two candidates on the existing 24-case evaluation contract for bounded MVP
acceptance and cross-Plan reflection coverage.

V14 was safely paused at Fast/Slow 0/0 after 13 complete cases and $0.575365
recorded model cost. The requested false-unavailable audit found a real soft
Signal projection loss: already-resolved financing disclosures were excluded by
instruction-prose chunk ranking and shared-budget competition. Query/evidence-word
ranking with per-Signal turns and document diversity restores the exact issuance
source under the same 32K budget. All 643 tests pass. Across 216 deterministic
case/Signal comparisons, none of the 28 unavailable results recovered with all
local PIT documents; this does not establish that all parsers or soft projections
are complete. V15 will freeze the repaired implementation for live acceptance.
See [V14 projection audit](information-evolution-v14-projection-audit-2026-09-10.md).

The Slow H1 unchanged-work fingerprint now includes its actual masked Fast
meta-memory view. Previously, new reflections alone could leave H1 incorrectly
suppressed after an older no-hypothesis result. Regression covers unchanged
reuse and renewed mining after a new reflection. V13 stopped before any model
transmission; V14 freezes this chain fix for live acceptance.

V12 terminated at Fast/Slow 0/0 after 19 completed case trajectories, 321
external attempts, and $0.76797112. Its remaining blockers were Controller
correction scope, exact need transitions, and misclassification of cutoff-bounded
future-period guidance. Generic typed recovery and scope repairs replay the paid
failures successfully without rewriting evidence. A fresh V13 will verify Fast
and Slow completion plus the actual reflection-to-mining handoff.

V11 terminated at Fast/Slow 0/0 (6/8/3 completed cases): two Predictor display
ceiling failures and one inherited-need cutoff loss. Predictor/post-hoc now
retain complete state and citations under exact transport budgets; meta views
retain whole items with omission counts. Paid V11 cutoff and V8 reflection
replays pass; all 639 tests and repository lint pass. A frozen V12 DeepSeek successor is prepared after verification.

The global Slow alias expansion defect is repaired: all Slow views now consume
the strict inventory without deriving first-word brands. Real 18,929-alias replay
preserves ordinary research prose; bounded compiled-pattern reuse removes repeated
compilation. V10 was interrupted by user request with its artifacts preserved;
a fresh DeepSeek Fast/Slow test follows the verified checkpoint.

V8 completed Fast round 1 / Slow cycle 1 on 2026-09-10, with one complete
24-case candidate (F1 .25), two rejected candidates, and no Signal promotion.
The Slow outcome exposed a Gen Z / ticker Z identity false positive, unmasked
cross-case meta, inconsistent Update document refs, and a hidden 240-character
fact cap. Generic boundary repairs pass 634 tests and exact paid-response replay;
productive live Slow validation is still pending. Short ticker URL masking also
remains intact; V9 preparation stopped before model transmission. V8 is immutable. Subsequent
external research/prediction should return to DeepSeek as requested. See the
[V8 audit](information-evolution-mvp-live-audit-2026-09-09.md).

The V7 live run rejected all three candidates on the remaining evidence-claim
length cap. That cap is now removed; claims remain nonempty and evidence-checked.
New contracts allow 8,000 Controller output tokens, while historical contracts
remain readable. Expanded input repairs cover IFRS facts/aliases, same-currency
dimensionless ratios, and complete compatible market series independent of tuple
order. Full regression: 631 tests and lint pass. The 216-combination deterministic
replay recovered 19 false-unavailable results (47 to 28), with none regressing
to unavailable. Fresh live validation is pending.

The V6 MVP run terminated at Fast/Slow 0/0: candidates completed 3, 0, and 6
cases before model-output rejection. Summary capacities are now advisory under
existing hard transport budgets; terminal all-unavailable batches finalize the
previous state without a model call. The exact 338/342-character paid responses
replay unchanged through all remaining validators. Prior incomplete execution is
not classified as an implementation failure. A fresh live successor is pending.

The 2026-09-09 authorized MVP audit corrected the Predictor baseline's
computation/display boundary (commit `4b149db`). V4 then completed five cases
but rejected at case six when repeated partial-answer routing prose remained
invalid. The shared fallback now uses typed answer-ownership issues to retain
the exact selected Signal as context only, with full revalidation and the
original need preserved. The exact final paid response replays successfully
without another call. Other routing failures retain quarantine/rejection.
The fresh successor uses the existing three-candidate portfolio for one Fast
round, then one Slow cycle, so one invalid Plan need not end the entire pilot.
Live Fast/Slow completion remains pending.

Executed and audited the approved first T7 Fast/Slow pilot (2026-09-08).
`self-evolution-t7-20260908-v1` safely paused at its 250-attempt ceiling after
248 completed model responses and `$0.37523724`; authoritative pointers remain
round 0/cycle 0, Registry version 1, and Locked Test sealed. The run completed
17/24 cases for candidate 1, rejected candidate 2 on its first case, and staged
11/24 case checkpoints for candidate 3. No partial cohort received metrics or
entered Archive/learning. Exact prompt/context/response inspection found an
overlong Basic literal, two sign-inconsistent quantitative claims, one ambiguous
projection ref, high H_init/routing correction rates, and one schema-valid but
logically weak positive prediction. A generic post-correction recovery now removes
only mechanically invalid evidence rows and beliefs that lose their last identical
support, then repeats the unchanged full validation to expose layered failures;
it never rewrites raw JSON into a belief or guesses a projection. Both real final
H_init responses now replay successfully while retaining their 2 and 5 valid
sibling evidence rows. [`self-evolution-t7-live-audit-2026-09-08.md`](self-evolution-t7-live-audit-2026-09-08.md)
contains the wire-level evidence, current agent-runtime comparison, and the revised
2,500-attempt successor proposal. T7 remains open: no Fast round, Slow promotion,
next-Fast Signal use, reliability pilot, or benefit confirmation has completed.
The 2026-09-09 MVP implementation checkpoint migrated the high-frequency
ResearchState evidence failures to typed issue codes, makes deterministic
fallback independent of diagnostic wording, and reduces fixed H_init/routing
prompt bytes while preserving their contracts. Existing persistence/recovery
tests show no need for a new attempt schema. Its first approved successor,
`information-evolution-mvp-20260909-v1`, executed but committed neither Fast nor
Slow: candidate 1 reached two of 24 cases with only one finalized result and was
rejected as diagnostic-only. Exact wire inspection found that future realized
information expressed as a date range, a future period ending, or an open-ended
`after` clause bypassed an example-shaped PIT detector; it also found a false
issuer-ownership description for third-party-capable news. Temporal validation
is now cutoff-derived, typed, path-scoped, and tested across equivalent and legal
neighboring phrasings in both H_init and H_reflect. News ownership is validated
against source capability. The per-case token ceiling is 256,000 after the real
trace showed 68,594 tokens before a required correction, while terminal and
run-level ceilings remain independent. See
[`information-evolution-mvp-implementation-2026-09-09.md`](information-evolution-mvp-implementation-2026-09-09.md).
Fast/Slow completion, Signal promotion/use, reliability measurement, and benefit
confirmation remain open. A fresh post-repair contract must be frozen and
approved before another external call. Pre-execution inspection of the locally
frozen v2 proposer context then found one historical parent that called
third-party-capable `company_news` issuer-owned in both B and H_init. v2 sent
zero external requests and will not execute. Historical seed discovery now
applies the complete current Plan contract before ranking, and staged pools fail
closed if a copied Plan becomes incompatible. The real history scan retains one
of two seeds and excludes the false-ownership parent. All 623 tests and
repository lint pass; a new code-bound contract is required.

Completed the offline portion of T6's generalized reliability matrix
(2026-09-08): [`self-evolution-reliability-matrix-2026-09-08.md`](self-evolution-reliability-matrix-2026-09-08.md)
maps format/API, evidence, recovery, persistence, generalization, injected error
distributions, and no-learning controls to deterministic acceptance tests and
the remaining live evidence. New cross-cutting tests exercise 0%, 10%,
distributed 20%, and issuer-clustered 20% technical failures without dropping
system or capability cases; valid siblings can still satisfy explicit
tolerances, while failures on supporting positive cases now reduce Binary F1.
The audit found and fixed the prior successful-row-only F1 calculation: known
positive technical failures are false negatives, and negative technical
failures stay explicit instead of becoming true negatives. Transport coverage
now includes retryable 429/5xx/timeout/URL failures, permanent HTTP errors,
refusal/no-text envelopes, unrelated provider fields, and missing usage
metadata. T1-T5 and offline T6 are complete; the real two-provider pilot,
approved statistical/reliability thresholds, and T7 live closure remain open.
All 613 tests, compileall, diff checks, and repository lint pass; no external
request was sent.

Completed T5 offline evolution-benefit confirmation tooling (2026-09-08): a
frozen, explicit protocol now compares baseline/candidate Plan and Registry in
all four combinations on the same cases, issuer groups, source corpus, model,
budget, and output projection. It records case-level predictions, failures,
coverage, usage, response identities, and executed/cited Signal refs; identical
inputs reuse one response within a replicate, while independent replicates may
not reuse an invocation. The immutable report separates contract validity,
independent Signal measurement accuracy, outcome-association diagnostics,
promotion/use lifecycle evidence, and paired system benefit. Missing system or
candidate-capability cases remain in the frozen cohort and produce
`incomplete`; a complete result below any approved threshold produces
`no_gain`. Changed Registries require an explicitly frozen independent
capability cohort and measurement thresholds. A crash-safe reservation ledger
prevents post-result cohort replacement. Existing production promotion gates
and historical Plan Archive ranking are unchanged. T1-T5 are locally complete;
T6-T7 remain open, and actual benefit is not yet established because no
confirmation protocol thresholds or external run were authorized. All 602
tests pass; no external request was sent.

Completed T2 Raw Info and Signal retrieval contracts (2026-09-08):
`RawInfoRequest` and versioned Signal retrieval policies now declare bounded
query terms plus structured required-source groups, minimum distinct periods,
period span, and observation count. The resolver selects over the complete
point-in-time eligible pool, reserves required source families and comparison
period coverage before the document limit, and continues authorized acquisition
when local evidence exists but is contract-incomplete. Coverage records expose
the exact missing requirements; unresolved partial documents and literal Basic
Info spans remain visible without being reported as answered. Signal execution
fingerprints partial inputs but gates execution until the contract is complete,
isolates that Signal from valid siblings, and maps provider, budget,
authorization, and materialization failures to technical execution statuses
instead of domain observations. The v1 seed catalog now contains explicit,
measurement-oriented queries and existing deterministic comparison/observation
requirements; no new scoring threshold was introduced. Real-shape tests cover
multi-source limiting, old comparison-period preservation, bounded acquisition
after a partial local hit, partial Basic Info visibility, Signal execution
gating, technical failure classification, round-trip compatibility, and shared
readiness. T1-T5 are complete; T6-T7 remain open. No external request was sent.

Completed T4 Slow candidate-generation hardening (2026-09-08): production H1 now
uses a versioned structured contract. The runtime owns stable proposal refs, the
fixed Discovery comparison, and evidence lookback, while the model supplies a
measurement object, canonical applicability rule, expected direction, retrieval
intent, structured falsifiers, and demand refs. Validation no longer requires
lexical overlap among model prose, query, and identifier. A non-empty capability
backlog may end in a structured `no_testable_hypothesis` result rather than a
forced candidate; its reason and H1 input fingerprint are committed and exposed
to later cycles. Signal Update now separates label-free evidence observations
from the runtime-computed outcome relation and requires each source fact to cite
a supplied document ref and literal span before association is considered.
Exploration E1 executes stable-ref microbatches; malformed batches are isolated
as technical failures, valid siblings remain, the frozen validation cohort is
unchanged, and E2 stops when either group lacks the configured grounded evidence
floor. Stable-item correction can append an explicitly missing runtime-owned
item without accepting rewrites to valid siblings. Superseded online H1 and
Update protocols and their prose-regex tests have been removed; legacy persisted
records remain readable at the compatibility boundary. An independent
fixture-driven blind set now rejects five schema-valid
Update errors (cross-case citation, fabricated literal, label-as-fact ordering,
unsupported source verdict, and missing evidence gap) while scoped correction
preserves valid sibling diagnostics. Label-revealed Mining decisions persist the
engine-derived positive/control sample basis regardless of model adapter. H3 terminal work is fingerprinted
without cycle-owned proposal ids, so exact committed refinement, rejection,
inconclusive evidence, missing evidence, and invalid-candidate work is suppressed
while changed evidence/strategy and unaffected siblings continue. Every Slow
result also stores a global search-input fingerprint, and `run-loop` stops after
three consecutive committed candidate-free cycles by default with cycle ids,
terminal categories, and changed-input diagnosis; restart checks the committed
streak before another cycle. A fresh read of V118's persisted E1 request/responses
and Slow result reproduces the original cross-domain identity rejection and the
Update claim that a positive label suggested a missing financing event, while
the new blind set targets that semantic class without rewriting history. T4's
local implementation and synthetic acceptance are complete; real closed-loop
usefulness remains a T7 question. All 589 tests and repository lint pass; no
external request was sent.

Current code organization audit (2026-09-08): the 15,507-line evolution runtime
and 12,071-line scheme engine are now stable 51-line and 17-line import facades.
Their implementation is separated into dataset, settings, transport, structured
validation, research validation, role-adapter, control, core-record, Fast Plan,
and Slow Signal modules with one-way documented dependencies; the two oversized
test modules are split by the same responsibilities. No Python file now exceeds
10,000 lines (largest production module: 6,106; largest split test: 3,330).
Canonical JSON hashing and crash-safe writes are shared by one standard-library
artifact module, and four identical backfill progress writers are one generic
implementation. The prior audit's dead-code and captured-response deletions remain
in place. Public imports, persistence schemas, external-call behavior, committed
pointer semantics, and point-in-time rules are unchanged. All 598 tests pass.

Current reliability implementation (2026-09-06): the T1 execution-isolation
foundation and the first T2 retrieval/input-representation slice from
[`self-evolution-action-plan-2026-09-06.md`](self-evolution-action-plan-2026-09-06.md)
are implemented. Runtime validation now has machine-readable issues, explicit
all/any path policy, stable item identity, and scoped projection that survives
provider list reordering while retaining valid siblings. H1 emits this contract
directly instead of granting write scope through diagnostic prose. Signal execution
now distinguishes successful/domain-unavailable observations from validation,
transport, permanent, budget, and authorization failures. Valid batch siblings
survive another row's failed correction; technical failures keep diagnostics but
are excluded from observations, learning events, and directional statistics, and
do not consume the idempotent observation key. Candidate effectiveness audits
report failures while retaining the frozen case list. Signal retrieval intent is
version-owned; the resolver ranks the complete PIT-eligible pool before limiting,
deduplicates same-source byte-identical copies, and reports query, selection, and
visible-context coverage separately. Update sees the exact evidence used by the
current Signal before supplemental windows. Aggregate Slow inputs and outputs use
one anonymity domain, and E1 refs are assigned after a cycle-bound outcome-free
ordering. Routing, Exploration E1, Signal Update, and baseline-sensitive Predictor
checks now emit the same structured issue contract; their scoped recovery preserves
valid siblings, explicitly rejects duplicate ids, and refuses to reinterpret an
all-invalid quarantined routing portfolio as domain `no_match`. The first T3
persistence slice separates immutable candidate definitions from keyed immutable
evaluations, binds promotion to one successful evaluation, deep-freezes Signal
snapshots, separates Update problem/work identity, and gives file-backed Raw Info
stores explicit snapshot/refresh plus oracle-root concurrent append semantics.
T3 promotion recovery now fails closed while a prepared transition exists and
reconciles the same batch across preparation, every stable-file class, Registry
version, output snapshot, promotion-record, and cycle-pointer fault boundaries.
T2-T5 are complete. T6-T7 remain open; no external request was sent. All 602
tests and repository lint pass.

Current V117 recovery verification (2026-09-05): inspected the real H1 request
and correction response. Validation prose incorrectly introduced `e.g` as a JSON
write path, preventing scoped correction projection. Pending recovery changes now
resolve inferred paths against the rejected object and preserve bounded Exploration
fallback after hypothesis structured-output exhaustion. All 578 tests and repository
lint pass. Exact V117 replay clears the bogus-path failure but still detects an
independent candidate-construct mismatch; it is not a successful live Mining result.
V117 used 46 model calls for $0.13163836 and committed cycle 1 with no candidates
or Registry transition. A fresh code-bound Slow run and dependent Fast verification
remain required.

Current exploration-grounding repair (2026-09-05): the post-V114 audit found
that E1's old schema forced at least one free-form observation even when a case
packet had no support, so a different model could fabricate a schema-valid
signature and let E2 discover a false pattern. E1 now accepts only either an
explicit empty observation list with a specific evidence gap or structured
observations carrying a supplied document ref and byte-exact non-trivial span.
The common local validator runs after every adapter, rejects malformed evidence,
duplicate cases, fabricated refs, and non-literal spans, and keeps the literal
authoritative over the model summary.

Exploration now reserves validation issuers first and gives each required
induction slot at most one label-hidden, same-group evidence fallback. E2 runs
only after the controller can freeze the configured grounded count in both
groups; it receives only those selected signatures, while validation cases remain
unseen. This avoids both endless deterministic retry on one empty case and
outcome-aware resampling. All 577 repository tests pass. V116 remains a zero-call
pre-change contract and must be superseded after this checkpoint; the next real
Slow run and dependent Fast verification still await explicit approval of the
named external destinations and payload classes.

Current V114 systemic Slow repair (2026-09-05): H1 produced three hypotheses and
H2 screened 32 ready profiles, but the old post-limit relevance filter erased all
36 H3 case packets before contrast. Replay against the exact Discovery and Raw Info
inputs found exact-source context for 11/12, 12/12, and 12/12 cases respectively,
but zero model-visible query matches for every hypothesis. This is a systemic
H1/data-alignment failure, not 36 independent source outages and not successful
Signal evolution. V114 remains immutable evidence: cycle pointer 1, Fast pointer 0,
Registry v1 unchanged, 48 model calls for `$0.13591368`, and 40 provider-ledger
requests including 16 acquisition reservations.

The resolver now permits a pure consumer selector over the complete eligible pool
before document truncation and reruns it after bounded acquisition; invalid selector
output fails locally, and failed-acquisition reuse binds the literal query. Mining
selects complementary bounded excerpts, keeps exact-source nonmatches as explicitly
unmatched comparator context instead of data gaps, and requires direct query-matched
packets in both fixed groups before H3 may produce any substantive decision. Thus
nonmatch can never be treated as feature absence across providers or model styles.

If H1 has no work, H3 has no usable proposal/evidence, or all H3 decisions are
inconclusive, the production adapter now invokes the existing outcome-hidden
exploration track once in the same cycle. Its candidates retain the identical
fixture, holdout, effectiveness, and promotion gates; a substantive H3 refinement
or rejection is never overridden. Update now reuses each Signal execution's exact
resolution and records all input hashes plus the bounded-excerpt limitation instead
of performing a different second retrieval. Slow output contracts remain
schema-only and Update rationale remains case-ref complete.

The next successor has 252 remaining model attempts, `$16.25695168`, and 545
provider requests. A real successor Slow run, actual prompt/context/response audit,
candidate validation/promotion, and next-Fast visibility remain required before the
MVP goal is complete. All 569 repository tests, repository lint, and whitespace
checks pass for this repair checkpoint.

Current V113 Slow audit and recovery (2026-09-04): V112's committed Fast result
was consumed through the exact committed-Fast bootstrap. V113 completed 48 model
calls for `$0.13247836` and 30 provider-ledger requests, committing cycle 1 while
keeping its Fast pointer at 0. This is not a successful Mining run: H1 used three
calls, then failed structured correction, so H2/H3 never ran; Update completed three
targets with conservative deferrals and Registry v1 remained unchanged.

Reading the actual H1 prompt/context and all three responses exposed two generic
errors: valid `positive Discovery cases` wording was rejected by an overly narrow
group-mention check, and a repaired field was discarded alongside an unrelated
rewrite. Fixed-group qualifiers now use the same grammar as the membership guard;
closed structured corrections can project only authorized model-authored paths,
restore unrelated values, and pass the complete unchanged parser. Ambiguous list
index shifts fail closed, and later corrections cannot inherit unrelated drift.
The exact V113 initial response now passes H1 in one replayed call. All 558 tests
pass. Actual H2/H3, candidate validation/promotion, and next-Fast visibility remain
unverified and required for the active MVP goal.

V111 ready state (2026-09-04): fresh contract `da7b040e...98be` is frozen
against code `fb601c7`, Python 3.12.14, and the approved development dataset.
It will run one 24-case Fast round with one candidate and then the dependent Slow
cycle, with a 64,000-token terminal reserve and V110's fully unspent ceilings of
246 model attempts, `$16.77035548`, and 618 data requests. Both freeze attempts
made zero external calls; the first failed closed until provider, capability, and
source-type wildcard allowlists were explicit. `state.json:last_completed_round=0`,
`cycle_state.json` is absent, Registry v1 is unchanged, and Locked Test has not been
accessed. Real execution remains pending explicit approval of the described external
payloads and destinations.

Current V110 semantic-consistency repair (2026-09-04): after the CLI reserve
correction, V110 froze contract `d86c1b8...55c` against code `576d02d` with one
Fast round before Slow, one candidate, a 64,000-token terminal reserve, 246 model
attempts, `$16.77035548`, and 618 data requests. Its launch was rejected before
transmission because the execution boundary requires explicit approval to send the
anonymous historical-company prompt/context to DeepSeek and bounded identifier/date
queries to the configured data providers. V110 therefore has no request, response,
attempt, or cycle artifacts; authoritative pointers remain `round=0/cycle=0` and its
full budget is unspent.

The complete V109 request/response audit found one schema-valid but semantically
contradictory Predictor result: `candidate_judgment=possible` and `magnitude=2-3x`
were accepted even though all three key reasons explicitly said the cited target was
not 2x, there was no evidence of doubling, and the divestiture was not a catalyst for
2x repricing. The Predictor prompt now requires one affirmative source-backed reason
for a positive judgment. A conservative local gate intervenes only when every reason
explicitly rejects the defined price outcome; ambiguous language, uncertainty such as
"not guaranteed", operating-metric doubling, and mixed positive/counter evidence are
left to the model. Generic alternative-path correction metadata lets any structured
role repair a sufficient subset: the Predictor may change the judgment plus dependent
magnitude or retain them and change its rationale, while unrelated fields remain
fixed and the full parser reruns. Exact V109-content regressions and both repair paths,
all 550 repository tests, and repository lint pass. Because the code changed after
V110 froze, it is immutable zero-call evidence; V111 is its fresh successor for the
explicitly approved external run.

V110 preflight correction (2026-09-04): the runtime/spec default and its unit
test required a 64,000-token terminal reserve, but the real `freeze-run` entry
still wrote the historical 36,000 value into every new contract. The CLI now
derives its frozen value from `RuntimeLimits`, and an entry-point regression plus
all 546 repository tests and repository lint pass. No V110 contract was frozen
before this correction.

Current V109 repair (2026-09-04): the first executor reached five completed Fast
cases and then stopped on a retryable TLS EOF; a mistakenly concurrent resume was
able to enter the same workspace, repeated the previously malformed initial proposer
request, received different valid content for the same `plan_r0001_c01`, and correctly
failed against the old case trajectory. Exact V109 H_init content also asked for the
issuer's adjusted close on the prediction date despite the system prompt reserving
that baseline to runtime; the missing local check accepted it and spent one useless
empty-routing call. Authoritative pointers remain `round=0/cycle=0`, Registry v1, and
V109 is immutable diagnostic evidence.

The runtime now takes a non-blocking OS lock before any cycle mutation or external
call, stages every accepted candidate Plan before its first case, and restores that
exact contract/round/slot/parent-bound Plan without another proposer call. H_init
validation now rejects scalar adjusted-close/share/stock-price lookups at the exact
prediction date or described as current/prediction-time price while preserving valid
price/volume-trend questions. Five focused regressions, both evolution modules (338
tests), all 545 repository tests, and repository lint pass. A fresh successor must be
frozen against this code revision before external execution resumes.

Current V108 repair (2026-09-04): contract `61a3324...a14a` first resumed one
retryable TLS EOF without repeating seven completed Fast cases, then made 110
completed calls plus one failed transport attempt for `$0.16910964` and five data
requests. Nine cases finalized; case ten persisted a Predictor and post-hoc result but
remained `stop_reason=budget_exhausted`, so the candidate stopped at 10/24 with
`incomplete_case_set` and `unfinalized_case`. Authoritative pointers remain
`round=0/cycle=0`, Registry v1, and Slow unstarted.

The exact case-ten H_reflect request had 7 prior evidence rows and explicitly capped
the result at 8, but the response appended three deterministic Signal claims and
returned 10. The correction correctly required compaction; its 24,041-byte wire body
plus 2,000-token output reservation needed 26,041 conservative units while only
16,822 remained outside the old reserve, so it was never transmitted. The old 36k
reserve also did not let a completed terminal batch spend its H_reflect portion, and a
correction preflight exception discarded already paid role usage before the Predictor.

New freezes use a 64k terminal reserve derived from the bounded terminal H_reflect
initial/correction and compact Predictor envelopes; historical 36k v7 contracts remain
readable but cannot execute across the code revision. A completed batch that reaches
the reserve receives `must_finalize=true` and may use it, while a pre-send correction
budget failure first tries the role's existing call-free fallback under the complete
unchanged parser and otherwise propagates with all paid usage. H_reflect now receives
an exact count/byte capacity map, and per-field overflow feedback states the removal
minimum without choosing evidence semantically. Focused reserve/fallback regressions,
all 541 tests, and repository lint pass. Remaining successor ceilings are 289 attempts,
`$16.83089036`, and 622 data requests.

V107 evidence (2026-09-04): contract `e7b0f90...14c7` made 61 completed calls plus
one failed TLS handshake attempt for `$0.10789268` and seven provider-ledger rows; six
case checkpoints were durable. Its same-contract retry was blocked before any request
because the bundled runtime auto-upgraded from frozen Python 3.12.13 to 3.12.14.
Exact runtime identity is a contract invariant, so V107 remains immutable evidence
rather than being modified or bypassed; V108 was frozen against the new runtime.

Current V106 repair (2026-09-04): post-`a423775` contract
`146d83f...3a8d` made 56 completed calls for `$0.07987476` and five data
requests. Five Fast cases finalized. The V105 Bumble case passed H_init after one
correction, confirming the numeric grounding repair; its routing then exhausted both
corrections on one partial guidance row. Authoritative pointers remain
`round=0/cycle=0`, Registry v1, and Slow unstarted.

The exact target asked for guidance about user growth, revenue, or cost savings. The
first correction correctly left only cost savings in `residual_need` and downgraded an
unrelated financing row to contextual. It retained a broad guidance selection reason;
the final correction changed that reason but again claimed cost savings, which the same
row declared unresolved. The validator was correct, but one stubborn invalid row erased
two valid contextual siblings and the whole case.

Routing correction feedback now explicitly permits whole-row contextual downgrade or
removal when an exact answered facet cannot be stated. After both corrections, a generic
call-free indexed-portfolio fallback may remove only rows named by every remaining
obligation, preserve siblings byte-for-byte/in order, and rerun the complete routing
parser. Mandatory nonempty matching and every applicability/cap validator remain
enforced. The exact V106 final response replays to the two valid contextual Signals with
an audited `selections[0]` removal; a sole mandatory invalid row still rejects. All 539
tests and repository lint pass. Successor ceilings are 141 attempts, `$17.04414696`,
and 632 data requests.

Current V105 repair (2026-09-04): post-`4b07838` contract
`541cbe5...7151` made 48 completed calls for `$0.07675780` and three data
requests. Five Fast cases finalized; case six reached H_init plus both bounded
corrections before repeating one unsupported numeric detail. Authoritative pointers
remain `round=0/cycle=0`, Registry v1, and Slow unstarted.

The exact initial and correction requests/responses show that the model fixed every
other evidence and assertion defect, but retained `August 7, 2025` when its same-claim
literal contained only `8.7%`, Q2 2025, and 15.94%. Feedback exposed only the missing
literal `"7"`; because those characters also occur inside `8.7`, the final correction
mistook substring presence for the separately authored numeric token. Quantity feedback
now reports every missing occurrence with its field path, half-open character span,
bounded verbatim context, normalized group, and complete-token boundary rule.

ResearchState roles also have a provider-independent, no-call grounding fallback after
both corrections are exhausted. It is limited to mechanically isolated unsupported
numeric evidence/assertions. A single Basic ref may copy its existing short exact source
literal into the claim and linked assertions; otherwise invalid whole items are removed
only when evidence remains. All unlisted state is preserved and the unchanged parser and
semantic validators rerun; mixed, identity, temporal, structural, and transition errors
still fail closed. The V105 final response replays by exact-source substitution while
retaining three evidence refs. All 537 tests and repository lint pass. Successor ceilings
are 197 attempts, `$17.12402172`, and 637 data requests.

Current V104 repair (2026-09-04): post-`1081e00` contract
`2ebf1856...52f6` made 41 completed calls for `$0.06882904` and three data
requests. Six Fast cases finalized, including the case that stopped V102, before case
seven exhausted routing recovery. Authoritative pointers remain `round=0/cycle=0`,
Registry v1, and Slow unstarted.

The real target asked for fiscal-2025 guidance plus Q1 revenue and active-client
figures. The first routing response correctly removed the one-word `guidance` facet
from its partial residual, but the generic 90% token-overlap heuristic called that
residual cosmetic because the long issuer/date frame remained. It also treated shared
`figures disclosed by SFIX as of 2025-05-30` wording as an answered facet. The first
correction correctly demoted the other two inexact direct answers to contextual and
preserved the valid guidance selection; the false diagnostic then forced an impossible
second change, which the provider repeated.

High-overlap residuals are now genuine partial answers when they remove a complete
version-owned direct-answer phrase and retain none; this works for one- or multiword
measured facets without company-specific rules. Residual/reason comparison separately
excludes reporting/request scaffolding and numeric/temporal framing from substantive
topic n-grams while retaining material product/project/operating-scope checks. The
exact saved V104 first correction now replays successfully with no second call, all 533
tests and repository lint pass, and normal validation still never chooses a Signal or
writes a residual. Successor ceilings are 245 attempts, `$17.20077952`, and 640 data
requests.

Current V103 successor repair (2026-09-03): immutable contract
`4f90c4b...6e8` froze code `8388651` with 286 attempts, `$17.26960856`, and
643 data requests, but its external launch was rejected by the execution platform
because the workspace had no credits. No provider or data request was transmitted;
`state.json:last_completed_round` remains 0, no `cycle_state.json` was created, and
the contract is now superseded by the changes below.

The complete V102 request/response audit found two provider-independent defects in
otherwise accepted paths. First, fixed-semantics scanning matched `adjust` inside the
market term `adjusted close`, causing a needless post-hoc correction; action verbs now
match whole words. Second, an H_init need requested contents of a November report from
a September prediction boundary; explicit future publication dates now fail at the
exact need path while as-of questions about already disclosed future schedules remain
valid, preventing an inevitable no-result routing call.

Most importantly, the accepted KGC soft Signal cited an unrelated operations sentence
after edge correction but inherited `guidance` from the rest of its 2,000-character
projection because raw mapping widened the short quote to the whole lineage run.
Projection lineage is now clipped to the exact quote, including safe handling of
markup/entities/collapsed whitespace, and the mapped raw slice must normalize back to
that exact quote. Edge candidates must be a unique complete sentence containing the
rejected source boundary; no unrelated sentence elsewhere in an overlap is suggested.
Consequently uncited window text cannot satisfy version-owned evidence phrases or enter
H_reflect. These repairs add no normal-path LLM calls; all 532 tests pass. A fresh
post-commit contract and live Fast+Slow run are still required after credits are
available; the unchanged successor ceilings are 286 attempts, `$17.26960856`, and 643
data requests.

Current V102 repair (2026-09-03): post-`835f358` contract
`ca35d2b...e93e` made 34 completed calls for `$0.04113732` and three data
rows. Five Fast cases finalized before case six exhausted H_init's bounded recovery,
so pointers remain `round=0/cycle=0`, Registry v1, and Slow unstarted.

The exact initial response used a 1,629-character market literal to support a price
range. The first correction fixed all other quantity/link defects but retained that
literal. Fresh second-correction feedback correctly required a shorter literal while
also requiring every unlisted field to remain byte-for-byte; shortening to one complete
row then necessarily invalidated the unchanged range claim and linked belief. This was
a general correction-contract dependency conflict, not a Bumble or price-range rule.
Overlong Basic-literal feedback now separates the mandatory literal path from bounded
`permitted_dependency_paths` containing only same-claim evidence claims and identical
beliefs/contradictions. Dependent paths change only when the mandatory repair would
otherwise invalidate them; all normal semantic, provenance, identity, and outcome
checks still rerun, and successful paths add no calls. Exact three-attempt recovery and
all 527 tests plus repository lint pass. Successor ceilings are 286 attempts,
`$17.26960856`, and 643
data requests.

Current V101 repair (2026-09-03): post-`10449a2` contract
`acd8908...99dc1` recorded 38 completed calls plus one failed transport attempt for
`$0.07840336` and three data rows. The generic second correction recovered two H_init
outputs and one H_reflect output that would previously have rejected the candidate;
four Fast cases finalized. Case five then stopped after both routing corrections, so
pointers remain `round=0/cycle=0`, Registry v1, and Slow unstarted.

The exact final routing context asked how operating cash flow and sale-leaseback
proceeds would fund expansion. The model correctly returned empty, but runtime treated
the three-word prefix `operating cash flow` from
`operating_cash_flow_margin` as a mandatory direct match. Both corrections therefore
invented a partial margin answer and failed scope validation. Automatic ref-derived
mandatory matching now uses only the complete normalized Signal id when it has at
least three words; it never derives sub-ngrams. Signal-owned synonyms remain explicit
version metadata, and `operating_cash_flow_margin:v1` declares only its full measured
object for direct answers. Exact V101 empty-route/full-metric regressions, all 526
tests, and lint pass. Successor ceilings are 202 attempts, `$17.31074588`, and 646
data requests.

Current V100 repair (2026-09-03): post-`e221d85` contract
`a2c3868...30ce0` made nine completed calls for `$0.01403164` and three data
rows. Plan proposal passed once; H_init, routing, and the soft Signal each passed
their correction. The first Fast case then stopped after H_reflect correction, so
pointers remain `round=0/cycle=0`, Registry v1, and Slow unstarted. The accepted
Signal evidence grounded 2025 production, cost of sales, and AISC guidance. Routing,
however, classified “latest production and cost guidance updates” as partial with a
residual that removed only `updates`; H_reflect correctly followed that persisted but
semantically cosmetic scope, and its correction restored the old need instead of the
required residual.

A partial residual that retains a version-owned direct-answer phrase while deleting
at most one content token is now cosmetic unless it is an explicit coordinated-period
split. Without a separable residual clause, correction names both scope and residual:
use full only for complete card coverage, otherwise contextualize or remove the
selection. More generally, new v7 contracts freeze two structured corrections. The
second occurs only if the primary correction remains invalid and receives the latest
output plus freshly recomputed obligations; every validator, identity/outcome
boundary, correction scope, and runtime budget remains unchanged. Historical contracts
without the limit retain one. Exact V100 scope and second-recovery tests, all 525
tests, and lint pass. Successor ceilings are 241 attempts, `$17.38914924`, and 649
data requests.

Current V99 repair (2026-09-03): post-`3230a5b` contract
`21fa5bf...ad8e7` made six completed calls for `$0.00588028` and four data
rows. Its first proposer attempt and correction were rejected before the second
proposal passed. The first Fast case then returned an empty Signal routing decision;
the exact-phrase gate forced a correction, which selected `guidance_acceleration:v1`
and failed scope validation. No case finalized, so pointers remain
`round=0/cycle=0`, Registry v1, and Slow unstarted.

The actual need requested quarterly production/cost actuals compared with already
known annual guidance. The soft Signal measures fresh guidance versus prior guidance,
so the empty initial decision was correct; the bare `guidance` mandatory-route phrase
created both a needless correction and an inapplicable selection. Mandatory empty-
route phrases must now contain at least two normalized words. The seed uses explicit
update/change/revision constructions, while ordinary guidance mentions remain
available for non-mandatory model routing. For a genuinely explicit update need, the
empty correction also receives the unambiguous partial scope and literal residual
clauses discovered in V98. Exact V99 no-call replay, explicit-update correction
coverage, all 523 tests, and lint pass. Successor ceilings are 250 attempts,
`$17.40318088`, and 652 data requests.

Current V98 repair (2026-09-03): post-`f41b5cb` contract
`7cc87b1...897c` made four completed calls for `$0.00446908` and four
fetched/cache-hit data rows. The first Fast case reached H_init and routing, then its
one routing correction changed only the missing `context_tags`; no case finalized,
so pointers remain `round=0/cycle=0`, Registry v1, and Slow unstarted. The exact
target asked for production/cost guidance plus a Tasiast restart update. The selector
copied the whole target as a partial residual and claimed both facets. Correction
feedback then incorrectly derived overlap from that already-invalid residual, labeling
the answered guidance topic and possessive `s` as terms to delete.

Cosmetic residuals now use only an unambiguous, version-phrase-matched top-level
target split for reason diagnostics. The other literal clauses are exposed as bounded
`residual_facet_candidates`; ambiguous splits abstain. Possessive punctuation is not
a topic token, and exact-key shape feedback identifies missing/unexpected leaf paths
instead of the whole selection object. Runtime still neither writes the residual nor
chooses a semantic repair. Exact V98-shape replay, all 522 tests, and lint pass.
Successor ceilings are 256 attempts, `$17.40906116`, and 656 data requests.

Current V97 repair (2026-09-02): post-`df0e379` contract
`2801fb6...1679b` made 47 completed calls plus one retryable TLS failure for
`$0.06922132` and five data requests. Five Fast cases finalized before TLS resume;
resume reused their artifacts and then case six reached a mixed deterministic/soft
Signal batch before H_reflect correction failed. Pointers remain `round=0/cycle=0`,
Registry v1, and Slow unstarted. The exact need contract showed a partial guidance
answer and contextual revenue result. H_reflect adopted only revenue evidence but
applied the guidance residual. Validation correctly classified the old need as
untargeted, then contradicted itself by appending a generic remove/narrow directive;
the correction returned unchanged.

Need-transition diagnostics now attach `required_action` and the exact required need
where applicable: restore, exact partial residual, full removal, or genuine narrowing.
The aggregate instruction applies each row instead of contradicting restore actions.
No transition semantics changed. Exact V97-shape regression, all 521 tests, and lint
pass. Successor ceilings are 122 attempts, `$17.41353024`, and 660 data requests.

Current V96 repair (2026-09-02): post-`d80910b` contract
`a3ebf7d...385a1` made 57 charged calls for `$0.08348900` and five data
requests. Seven Fast cases finalized; case eight reached H_init, routing correction,
two soft Signals, and H_reflect before its sole correction failed. Pointers remain
`round=0/cycle=0`, Registry v1, and Slow unstarted. The exact Signal and reflection
requests/responses show a composite revenue claim using quantities from evidence
indices 0 and 1 while citing only index 0. The correction removed its linked belief
but retained the invalid evidence claim because Signal quantity errors, unlike Basic
quantity errors, lacked the structured literal checklist.

Basic and Signal quantity validators now emit the same missing groups, exact authored
literals, same-claim evidence paths, and linked assertions. The existing correction
contract therefore checks every retained path; runtime still neither adds a reference
nor rewrites a claim. Exact V96 feedback replay, all 520 tests, and lint pass.
Successor ceilings are 170 attempts, `$17.48275156`, and 665 data requests.

Current V95 repair (2026-09-02): post-`04dfd80` contract
`4b17497...5b646` made 39 charged calls for `$0.07100884` and three data
requests. Five of 24 Fast cases finalized before case six failed its H_init
correction, leaving authoritative pointers `round=0/cycle=0`, Registry v1, and Slow
unstarted. All 39 raw responses, every reached stage prompt/context, the six Basic
contexts, Predictor/post-hoc outcome boundary, failure artifacts, and pointers were
inspected. The proposer twice crossed H_reflect's Predictor boundary; case-one routing
claimed a period-qualified guidance facet retained by its residual; its soft-Signal
correction moved from one truncated projection edge to another; and case six changed
a rejected claim while retaining the unsupported `2025` literal.

Plan semantics are now validated at their owning `H_*` field, so operating-event
probability in H_init remains legal while H_reflect price-direction decisions receive
an exact correction scope. Reordered partial-answer overlap now recognizes two topic
terms plus a shared temporal qualifier. Signal edge feedback supplies bounded
byte-exact interior candidates without choosing evidence. Quantity correction carries
a counted per-path literal checklist, so changed surrounding prose cannot masquerade
as repair. Exact V95 replay covers all four shapes; all 520 tests and repository lint
pass. Successor ceilings are 227 attempts, `$17.56624056`, and 670 data requests.

Current V94 repair (2026-09-02): post-`e0e7215` contract
`f0d505f...0634` made three charged calls for `$0.01281336` and three data
requests. Its first Fast case stopped after H_init and its one correction, leaving
authoritative pointers `round=0/cycle=0`, active cycle 1 in `fast_loop`, Registry v1,
and Slow unstarted. The proposer and both H_init requests, full Basic projection
context, raw responses, structured correction payload, rejection artifact, and
pointers were inspected.

The first H_init response contained 32 frontier items, including five actionable
questions copied byte-for-byte into both `open_questions` and
`next_information_needs`. Its correction received eight exact eviction paths: all
five duplicate open questions plus three resolved-question bookkeeping items. Those
paths alone met both the 24-item and 6000-byte limits. However, the prompt described
the six arrays as alternative removals before the exact paths, and runtime did not
enforce ResearchState correction scope. DeepSeek consequently removed or rewrote
valid hypotheses, beliefs, evidence, and next needs while retaining four duplicate
questions; normal validation correctly rejected the result.

Exact compaction removals now override alternative arrays in provider instructions.
ResearchState correction computes a closed structural write scope only when exact
paths fill the quota and every other obligation is provably contained or satisfied by
those removals; unbounded evidence/need linkage stays open to avoid false rejection.
The actual V94 pair now replays to an explicit unrelated-drift rejection, while a
generic fixture proves one exact removal cannot authorize deleting a valid belief.
All 516 tests pass; successor ceilings are 266 attempts, `$17.63724940`, and 673 data
requests.

Current V93 repair (2026-09-01): post-`bde2375` contract
`2690f63...74727d` made seven charged calls for `$0.01263052` and four data
requests. Its first Fast case completed with one H_init, one correct empty routing,
one Predictor, and one post-hoc call and no correction; case 2 then failed one H_init
correction, leaving authoritative pointers `round=0/cycle=0`, Registry v1, and Slow
unstarted. All seven raw responses and every actual stage prompt/context were opened.
The case-1 selector saw 11 unexecuted cards but its only actionable need was analyst
targets, which none measured; no-match was logically correct. Predictor context was
anonymous and outcome-free, and the outcome appeared only in post-hoc context.

The selector's first response now included the unambiguous required-tag contract and
needed no correction. H_init also avoided cross-field question duplication. The case-2
hypothesis said the market “may be pricing in” successful execution of a 2027 opening
within the current six-month stock outlook. This already named the permitted present
expectation channel, but the local future-event guard recognized `expectation`,
`progress`, and related terms without recognizing standard `priced in`/`pricing in`
language. It therefore issued a false correction, which DeepSeek returned unchanged.
The transmission detector now recognizes the general pricing-in construction while
the direct outside-horizon causality fixture remains rejected. The same validator uses
one sentence rather than a semicolon continuation, so its one path remains one
obligation. All 515 tests and lint pass; successor ceilings are 269 attempts,
`$17.65006276`, and 676 data requests.

Current V92 repair (2026-09-01): post-`0bfac04` contract
`1b9d6b8...f84491` made 18 charged calls for `$0.02564912` and three data
requests. Its first Fast case completed all three Signal rounds, prediction, and
post-hoc reflection; the second case's H_init failed its only correction, so
authoritative pointers remain `round=0/cycle=0`, Registry remains v1, and Slow did
not start. Every persisted request prompt, complete user context, raw response,
correction payload, accepted trajectory, and failure artifact was inspected.

The actual selector system prompt contradicted itself: the literal “contain exactly”
field list omitted `context_tags`, while a later clause described up to four tags.
DeepSeek consequently omitted the field in two initial routing outputs and both paid
corrections added otherwise useful applicability classifications. `context_tags` is
now one required, possibly empty, zero-to-four-value array inside the exact field
list; runtime still never defaults or infers it, so cost reduction does not discard
Signal applicability learning.

Case 2 H_init produced three independently pathful obligations. Its correction fixed
all three quantitative beliefs and the first unsupported evidence claim but retained
the second rejected claim byte-for-byte. The validator correctly failed closed; the
prompt already contained every source projection and obligation, so neither context
loss nor a false validator caused the failure. Correction-only feedback now flattens
all obligation paths into a deduplicated `required_change_paths` list with an exact
count and final old-value comparison check. This preserves the one-correction
boundary, adds nothing to normal calls, and neither deletes nor authors evidence
locally. The first case's LLM-Signal edge-fragment correction and H_init exact-claim
correction were substantively necessary. Although the raw financing correction tried
to classify a share disposal as positive, canonical execution correctly downgraded it
to `unavailable`, and H_reflect did not adopt it.

The accepted first-case state also repeated all three actionable retrieval questions
byte-for-byte in both `open_questions` and `next_information_needs`, then transmitted
those duplicates through every reflection, Predictor, and post-hoc context. The shared
contract now assigns an exact actionable question only to the next-needs field, and
the semantic validator aggregates each new duplicate `open_questions[index]` with all
other evidence/transition errors before the one correction. It performs exact-string
comparison only, preserves committed legacy duplicates, and never infers or deletes
semantic content locally. All 514 tests and lint pass; successor ceilings are 276
attempts, `$17.66269328`, and 680 data requests.

Current V91 repair (2026-09-01): post-H1 commit contract
`4d7df7b...40223f` made six charged calls for `$0.015372` and three data requests,
then rejected its only candidate in first-case Signal routing at authoritative
pointers `round=0/cycle=0`; Registry stayed at v1 and Slow did not start. All six
actual prompts, contexts, responses, correction feedback rows, and exact cache usage
were inspected. H_init correctly removed one already answered analyst-target need and
simultaneously compacted 25 items to 24 without unrelated change.

The proposer initially returned the sole optional no-op `query: ""`; its paid
correction added a query but also rewrote all three otherwise valid H_* skills. Empty
optional query is now canonically omitted before domain construction, with the exact
raw response still cached, so no correction call or new retrieval meaning is created.
Non-string query failures carry their exact raw path, and Plan correction may change
only diagnosed B/H_* paths. The shared correction diff now descends equal-length lists
and permits list-size changes only when an element path itself is authorized, so a
named child field does not authorize rewriting or deleting its whole object.

Routing selected fresh guidance as a partial answer to a 2025/2026 guidance need and
correctly retained 2026 as residual, but the old validator treated their shared
`production cost guidance` topic as the unresolved facet. Correction was told to
delete the topic words, then still claimed both years and failed. Runtime now permits
the necessary shared topic while a mechanically visible `2025 and 2026` split makes
only the retained `2026` illegal in the answer reason. Other residual branches retain
the conservative three-term phrase/reordered-overlap gate. Correction no longer emits
a pathless clause. Exact generalized fixtures and all 513 tests pass; successor
ceilings are 294 attempts, `$17.68834240`, and 683 data requests.

Current Slow-boundary repair (2026-09-01): the latest completed bootstrap artifact,
v76b, was re-audited from its two persisted H1 requests/responses through H2, H3,
Update, validation, Registry transition, and both authoritative pointers. H1 used two
calls and `$0.00246036`; H2 was the intended deterministic canonical-applicability
stage with zero model calls. All three H1 candidates then lacked enough
hypothesis-relevant point-in-time packets in both fixed groups, so H3 durably recorded
`not_called_evidence_unavailable` and Update recorded `no_actionable_target` with
`model_called=false`. The Slow pointer advanced to one, the Fast pointer stayed zero,
and Registry v1/hash stayed unchanged through an applied empty transition.

The actual H1 content exposed cross-field construct drift: hypothesis identity and
query requested guidance or analyst revisions while `expected_positive_pattern`
could compare generic revenue growth or prior-period cost instead. H1 now derives a
normalized candidate construct from the meaningful terms shared by hypothesis id and
query, requires the expected pattern to retain at least half, and normalizes ordinary
revision word forms. A bounded correction may change only diagnosed paths and cannot
rewrite another valid hypothesis; identity-leaking outputs remain withheld and are
fully revalidated rather than echoed for byte comparison. The H1 prompt states the
same invariant to avoid preventable correction calls. All 510 tests pass. The frozen
zero-attempt v90 contract predates this runtime change and is superseded; the next
external run must use a new post-commit contract.

Current ordinary-loop repair (2026-09-01): immutable v89 contract
`e0ba705...c601aa` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used 22 charged attempts, `$0.03028424`, and three
data-ledger rows. Case one completed the full Fast chain in 16 case calls; case two
failed after H_init plus correction. Locked Test remained sealed and Registry stayed
at its initial version/hash. The successor ceilings are 106 attempts, `$17.70371440`,
and 686 data requests.

All 22 actual prompts, payloads, responses, correction obligations, compact contexts,
and persisted trajectory state were inspected. Three proposer outputs contained valid
Plan objects followed by exactly one extra closing brace, creating three paid syntax
failures before the fourth call produced an accepted target-scoped Plan. Case-one
H_init was compact and material. Its first route repaired missing context tags; the
soft batch kept the valid guidance result while one financing result corrected a
cross-Signal projection citation. Four Signal rounds each contributed a new available
result or partial need transition before an explicit empty fifth route finalized.

The initial Predictor correctly returned `unlikely`: its reasons used the supplied
`23.982` mean, the `$27` target, and neutral guidance to argue against a doubling.
It described `$47.96` as the derived 2x baseline, but the validator misclassified that
threshold as the current baseline and forced correction. The correction drifted every
reason plus judgment/magnitude to `possible/2-3x`, causing the saved false positive.
Exact replay now accepts the original negative judgment. Case-two H_init then returned
25 array items against the 24 limit; correction received only a six-array choice and
returned the rejected object unchanged.

Repairs are transport/state-contract generalizations, not issuer cases. One complete
JSON object followed only by one redundant `}` is normalized with its raw hash logged;
all ambiguous suffixes still fail. Aggregate compaction now requires an exact removal
path from independently invalid items, byte-identical duplicates, then resolved
bookkeeping, without local state mutation. Predictor baseline validation recognizes
and checks `Nx/double/twice` derived arithmetic, while correction is confined to named
paths and cannot silently change judgment or unrelated evidence. Exact V89 replay,
all 508 tests, and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v86 contract
`1f8a0a1...994e4` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used five charged attempts, `$0.00936124`, and three
data-ledger rows. The first proposer response was malformed; its correction became
valid JSON but retained an H_reflect Predictor-ontology violation, so fail-closed
proposal retry produced a valid Plan. H_init and its correction then failed. Locked
Test remained sealed and the Registry stayed at its initial hash. The successor
ceilings are 167 attempts, `$17.80535132`, and 695 data requests.

All five requests/responses, including the malformed raw output, were inspected. The
accepted Plan kept every request target-issuer-scoped and separated evidence
organization from Predictor judgment. H_init received complete market/news/transcript
coverage plus six visible filing projections. The new downstream-visibility prompt
worked: its frontier retained the UBS target, production guidance, free cash flow, and
two-point market evidence. Its initial 25 items had three independently validatable
defects; correction fixed the resolved/need facet and unsupported year, but did not
remove any item for the explicit 25-to-24 aggregate obligation.

Aggregate correction feedback now adds bounded
`structurally_redundant_remove_paths` only for mechanically provable duplicates. In
the exact V86 shape, the duplicated open question / next information need yields
`open_questions[0]` as a preferred non-binding removal candidate. Runtime neither
infers research meaning nor mutates output; the normal validators rerun. Exact replay,
all 494 tests, and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v85 contract
`45b2a09...f9b22` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used seven completed model attempts, `$0.01506148`,
and four data-ledger rows. The first case completed H_init, empty routing, Predictor,
and post-hoc in four case calls; it made zero Signal executions/reflections. The
second H_init and correction then failed. Locked Test remained sealed and the Registry
stayed at its initial hash. The successor ceilings are 172 attempts, `$17.81471256`,
and 698 data requests.

All seven prompts, payloads, and responses were inspected. Case one had an explicit
SEC provider error, complete news and market context, and a single quarterly revenue /
earnings-versus-expectations need. No current Signal card directly answered that
compound need, so routing's empty selection and zero Signal calls were correct. The
Predictor received the runtime five-day mean `23.982`, returned low-confidence
`insufficient_information`, and post-hoc coherently attributed the realized non-surge
to missing fundamentals without manufacturing certainty.

H_init nevertheless retained only price evidence and omitted visible material UBS
target/Tasiast context; downstream Predictor sees this frontier, not raw Basic text.
The prompt now requires the smallest material direct expectation support or
counter-evidence when present, without enumerating every source. In case two, a Q1
year-over-year revenue/EBITDA need was falsely treated as answered by broad recent
revenue because of `company revenue`; generic company/issuer tokens are now removed
before overlap matching. Two `kind='news'` errors also split their expected-kind
clauses into pathless obligations; each diagnostic is now one exact kind-path row.
Exact V85 replay preserves the need, yields two pathful obligations, and accepts the
recorded correction. All 493 tests and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v84 contract
`9c31bbc...fbe71` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used four completed model attempts, `$0.01383564`,
and four data-ledger rows. Proposer correction was justified: initial H_reflect said
it would finalize the four-way judgment, and correction narrowed this to evidence
collection. H_init and its correction were the other two calls; Signal routing,
execution, Predictor, post-hoc, and Slow Loop were correctly not entered. Locked Test
remained sealed and the Registry stayed at its initial hash. The successor ceilings
are 179 attempts, `$17.82977404`, and 702 data requests.

All prompts, payloads, and responses were inspected. H_init saw 14/21 company-fact
projections and 1/4 news projections with explicit budget omissions, plus complete
market and transcript rows. The same-state gate falsely treated `Kinross revenue` as
a resolved topic between a historical-revenue question and a gold-price sensitivity
question. Its conservative two-word fallback now removes possessive remnants and
abstains when both phrases begin with the same title-cased entity token; semantic
lowercase topics such as construction progress remain eligible.

Although V83 had structured missing quantity groups, V84 showed that normalized
`4239700000` was not an actionable spelling for `$4,239,700,000`; correction copied
the rejected claims unchanged. Missing-quantity obligations now also carry the exact
numeric substrings found in each claim and instruct a grammatical single-observation
narrowing when one comparison endpoint is removed. Exact V84 replay removes the false
topic obligation, maps all normalized groups to authored literals, rejects the
recorded response, and accepts four source-supported claims with matching beliefs.
All 491 tests and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v83 contract
`e0014d5...7beff` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used four completed/charged attempts, `$0.00985460`,
and four data-ledger rows. The first proposer output had one extra closing brace; its
raw response and usage were durably preserved and the sole correction produced a
valid Plan. H_init and its correction were the other two calls; Signal routing,
execution, Predictor, post-hoc, and Slow Loop were correctly not entered. Locked Test
remained sealed and the Registry stayed at its initial hash. The successor ceilings
are 183 attempts, `$17.84360968`, and 706 data requests.

All four requests and three persisted model responses, including the malformed raw
proposer output, were inspected. H_init saw complete 4/4 market and 5/5 news coverage,
an explicitly unavailable 10-K request, and 13/18 earnings-call projections with five
budget omissions. Its initial state was compact, but the local same-state check
mistook the shared period `Q2 2025` for a topic and falsely said a gold-price question
was answered by a production-cost question. Pure temporal phrases no longer establish
resolved/need equivalence.

The same market claim containing an unsupported computed `25.7%` appeared on two
evidence refs. Old feedback named only the first, then exact-copy diagnostics offered
the still-invalid second ref as a valid candidate. Missing-quantity obligations now
carry every same-claim evidence path and normalized missing group, require one
identical retained repair, and exclude every named evidence index from copy candidates.
Exact V83 replay removes the false period obligation, names both market refs, excludes
their claim from candidates, rejects the recorded response, and accepts a complete
model-authored repair. All 490 tests and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v82 contract
`897e949...14d74` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used three completed model attempts, `$0.00532476`,
and three data-ledger rows. The candidate Plan, H_init, and its one correction were
the only calls; Signal routing, execution, Predictor, post-hoc, and Slow Loop were
correctly not entered. Locked Test remained sealed and the Registry stayed at its
initial hash. The successor ceilings are 187 attempts, `$17.85346428`, and 710 data
requests.

All three real V82 prompts, payloads, and responses were inspected. The accepted Plan
had three target-company-scoped requests; H_init saw complete request coverage of
4/4 disclosures, 5/5 news projections, and 3/3 market projections. It returned a
compact state. Initial correction feedback correctly named one invalid multi-row
market claim and two quantitative beliefs without byte-exact evidence claims. The
correction fixed the claim and Asante belief but changed the valid evidence wording
`Kinross's` to `Kinross Gold's`, leaving one exact-link failure. This was model
noncompliance rather than a hidden validator or contradictory prompt.

Grouped quantitative assertion obligations now add at most three path-specific exact
claim candidates, ranked only from evidence rows with no independently reported
defect. The role may copy one, remove the assertion, or repair a different evidence
claim and copy its final value; runtime still makes no semantic replacement. Exact
V82 replay ranks the correct final-price claim first for the failed belief and accepts
a one-field byte-exact repair. All 488 tests and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v81 contract
`713719f...10d46` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used three completed model attempts, `$0.00965076`,
and three data-ledger rows. The candidate Plan, H_init, and its one correction were
the only calls; Signal routing, execution, Predictor, post-hoc, and Slow Loop were
correctly not entered. Locked Test remained sealed and the Registry stayed at its
initial hash. The successor ceilings are 190 attempts, `$17.85878904`, and 713 data
requests.

All three real V81 requests/responses and all visible Basic projections were
inspected. Request-fair context live-covered every resolved request: company news
5/5, market 4/4, the nominal competitor request 3/3, and earnings calls 12/19 with
seven explicit budget omissions. The competitor request itself was unsound: Basic
Info always resolves under the target `company_id`, so its general cross-issuer
description/query merely returned more target-company news. Automatic Plan
validation now rejects such fields before case data or H_init calls; competitive
requests must explicitly use the target issuer's own disclosures or company-scoped
news.

H_init returned 32 items, asked for the runtime-owned baseline date/price, attached
two non-literal temporal/quantity claims, and authored eight quantitative beliefs
that did not copy their evidence claims. Its correction fixed most citations but
removed only four items and retained the baseline question. Raw validation now names
that exact question path, groups all quantitative assertion paths into one checklist,
and makes combination overflow computationally explicit with current total, maximum
total, and minimum removals; removing a belief/evidence pair counts as two. Exact V81
replay yields `32 / 24 / 8`, rejects the recorded 28-item correction, and accepts a
24-item repair. All 487 tests and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v80 contract
`6e9b69f...8d284` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used three completed model attempts, `$0.00525840`,
and three data-ledger rows. The candidate Plan, H_init, and its one correction were
the only calls; Signal routing, execution, Predictor, post-hoc, and Slow Loop were
correctly not entered. Locked Test remained sealed and the Registry stayed at its
initial hash. The successor ceilings are 193 attempts, `$17.86843980`, and 716 data
requests.

The new projection coverage fields live-verified correctly: both Plan requests were
source-resolved and `projection_status=complete` with 5/5 visible projections. H_init
returned a compact 23-item state. Its actual citation defects were limited to one
claim adding a date found only in metadata and the linked belief not copying that
claim. The correction removed the date and returned four valid literal refs.

Rejection instead came from the new same-state stale-need check tokenizing every
`Kinross Gold's ...` question as the shared phrase `kinross gold s` and falsely
marking four unrelated needs as resolved by the stock-performance question. The
model reasonably preserved them. Topic matching now removes possessive remnants and
current/recent/latest boilerplate, prefers an ordered three-word topic, and allows a
two-word fallback only when it is not title-cased as an issuer name in both strings.
The exact V80 initial/correction replay now yields only the two real quantitative
obligations and accepts the recorded correction without another call. All 485 tests
and lint pass.

Current ordinary-loop repair (2026-08-31): immutable v79 contract
`e208df2...d8f8` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used eight completed model attempts, `$0.01779036`,
and three data-ledger rows. KGC completed and persisted Predictor plus post-hoc
output; Wynn failed after its H_init correction reduced a 33-item ResearchState by
only two items. Locked Test remained sealed and the Registry stayed at its initial
hash. The successor ceilings are 196 attempts, `$17.87369820`, and 719 data requests.

All eight real V79 requests/responses were inspected. The KGC H_init correction fixed
its quantitative belief but retained a request for the latest analyst target/rating
even though the same visible news projection said UBS raised the target from `$20` to
`$27` and reiterated Buy. Routing correctly returned empty and spent no Signal calls,
but the already-answered need then survived into Predictor, which otherwise used the
new runtime baseline `23.982` correctly. H_init raw prevalidation now aggregates a
high-confidence visible-answer signature and same-state resolved/need contradiction
with citation and compaction errors before the only correction; it reports one exact
need path and bounded source excerpt, abstains on partial matches, and never rewrites
the need locally.

The real Wynn error said only `combined count=33 > 24`; it did not say that at least
nine items must be removed or which arrays were alternatives, so correction returned
31. Combination obligations now carry `minimum_removed_items` and
`must_reduce_any_of_paths`, while per-field overflow remains field-addressed. Exact
Wynn replay gives the nine-item minimum plus the duplicated construction-progress
need path in one correction and accepts a 15-item model-authored repair.

The actual Basic Info input exposed a second control-plane ambiguity: earlier news,
market, and transcript requests consumed the sequential 48k/32k budgets, leaving the
resolved financial request with zero visible projections and no omission marker.
Both durable span and model projection allocation now retain one highest-ranked item
per resolved request before filling remaining capacity, without increasing either
ceiling or clipping a span. Each model request explicitly separates source `status`
from `projection_status` and visible/omitted counts, which also survive in the
Predictor source index. Exact KGC/Wynn replay, all 484 repository tests, and lint pass.

Current ordinary-loop repair (2026-08-31): immutable v78 contract
`8d55189...504c4` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used 12 completed model attempts, `$0.01447992`, and
three data-ledger rows. The first KGC case finalized and persisted Predictor plus
post-hoc output; Wynn then failed after its empty routing correction. Locked Test
remained sealed and the Registry stayed at its initial hash. The successor ceilings
are 204 attempts, `$17.89148856`, and 722 data requests.

Every real V78 request/response was inspected. Empty routing feedback named neither
the matching Signal's target need nor an output path, so correction copied an unrelated
need and omitted tags; feedback now identifies top-level `selections`, ref, target
index, and phrase. KGC routing also claimed Tasiast restart coverage in
`selection_reason` while retaining the same facet in `residual_need`; partial reasons
may no longer repeat a distinctive residual phrase. Its soft-Signal correction was
not sent because a 55,761 exact reservation exceeded the 54,735 remaining case
budget. The correction had duplicated both rejected rows and incorrectly required one
quote even for current/prior comparisons. It now omits durable failed output, permits
the smallest skill-required quote set, and the exact V78 repair reservation is 53,478.

The completed KGC Predictor received no runtime five-day mean and mislabeled the old
`$19.38` observation as current, then post-hoc repeated the resulting wrong target
upside as a decision driver. The bounded Predictor packet now carries a point-in-time
five-day baseline derived from visible Basic market rows (`23.982` in the exact V78
replay); local correction rejects another dated observation labeled current/baseline,
and post-hoc retains the same baseline. H_init now distinguishes expectation repricing
inside six months from operating events occurring later, and numeric correction
advice no longer creates pathless semicolon obligations. Exact V78 routing/Predictor
replay, all 480 repository tests, and lint pass.

Current ordinary-loop repair (2026-08-30): immutable v77 contract
`449e5fe...b9aca` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used four completed model attempts, `$0.00602560`, and
three sandbox-denied staging data rows. Plan proposal and bounded H_init passed in one
call each; routing failed after its one correction. Locked Test remained sealed and
the Registry stayed at its initial hash. The successor ceilings are 216 attempts,
`$17.90596848`, and 725 data requests.

The exact initial routing output omitted `context_tags` on two rows. The parser treated
that routing-only shape defect as terminal for each row and hid already decidable
semantic errors until after correction: guidance pointed its residual at a different
analyst-estimate need, while customer concentration retained the complete generic-risk
target and lacked both required customer context and a direct-answer phrase. Current
routing continues semantic diagnosis when only tags are missing/invalid, without
inserting a tag into accepted output. A partial residual must now retain at least half
of its own non-generic topic terms from the one selected target and remove at least ten
percent of the target's topic terms. Internal routing diagnostics no longer create
pathless semicolon fragments. Exact V77 replay yields six path-bearing obligations and
accepts one minimal guidance-only correction; all 476 tests and lint pass.

Current Slow-bootstrap verification (2026-08-30): immutable v76b contract
`e0b0b6c...3462` committed authoritative `cycle=1` with zero Fast rounds, two
completed H1 calls, `$0.00246036`, and 13 data-ledger rows (one local sandbox error,
seven fetched, five quota-deferred). It used current runtime code with the compatible
v31-v33 frozen no-signal backlog and its Registry hash; the current ordinary Registry
had no eligible no-signal bootstrap source. Locked Test stayed sealed. H1 proposed
three grounded hypotheses, its correction removed fixed-group redefinitions and one
alternate horizon, deterministic H2 built 32 anonymous ready profiles with zero model
calls, and H3 was correctly not called because only one of 36 bounded evidence packets
was usable. With no candidate, Update made zero calls and the Registry transition was
an applied no-op. The remaining cumulative ceilings are 14 attempts,
`$17.91199408`, and 728 data requests.

Exact v76b correction artifacts exposed that semicolons inside four H1 diagnostics
had been split into eight obligations and every `must_change_paths` array was empty.
H1 validation now names exact hypothesis fields and keeps matched text within the same
obligation; replay of the real initial/corrected responses produces four obligations
with four exact paths. ResearchState-only quantity/claim repair prose is no longer
sent to unrelated roles, reducing this H1 system prompt from 5,792 to 5,176 characters
while preserving a byte-identical initial/correction prefix and all validators. The
real V76 response replay, all 475 repository tests, and lint pass.

Current ordinary-loop repair (2026-08-30): immutable v75 contract
`7de3a6f...f019` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used 11 completed model attempts, `$0.01025724`, and
four data-ledger rows. The first Fast case finalized and persisted Predictor plus
post-hoc output. Locked Test remained sealed, the Registry stayed at its initial hash,
and Slow Loop did not start. The successor ceilings are 16 attempts,
`$17.91445444`, and 741 data requests.

V75 live-validated the new routing schema. The first current selector response used
`answer_scope=partial` for the revenue-growth facet, persisted the exact residual
product-adoption need, and kept a second growth Signal contextual on the same target.
Its only defect was two missing `context_tags` fields; correction added only those
fields and preserved the scope/residual byte-for-byte. Both deterministic results were
unavailable because the Plan's 10-Q request resolved to provider-no-data, so runtime
correctly performed no H_reflect and a later empty routing decision finalized the case.
Post-hoc correction replaced prohibited probability language with confidence language.

The second H_init response had two independently reported defects: a missing evidence
`kind`, and unsupported `2025` in both the evidence claim and linked belief. Correction
fixed only the first and repeated the second. Aggregating several requirements into a
semicolon-delimited string is therefore not enough to make one correction executable.
Every role correction now receives the unchanged complete error string plus a numbered
`obligations` array, `obligation_count`, and extracted `must_change_paths`; the system
requires every row to be satisfied. This projection adds no semantic inference or
local repair, and the exact same parser/validators still run after the one correction.
The V75-shaped regression remains covered and all 475 tests plus lint pass.

Current ordinary-loop repair (2026-08-30): immutable v74 contract
`053795a...3fe2` rejected its only candidate during the seventh case at authoritative
pointers `round=0/cycle=0`. It used 50 completed model attempts, `$0.05659276`, and
three sandbox-denied data-ledger rows. The first six Fast cases finalized and
persisted Predictor plus post-hoc output. Locked Test remained sealed, the Registry
stayed at its initial hash, and Slow Loop did not start. The successor ceilings are
27 attempts, `$17.92471168`, and 745 data requests.

Three actual H_reflect requests live-verified the V73 result-aware interface. Enbridge
adopted no context-only evidence and preserved its state; Life Time adopted exact
cash/margin/growth claims while preserving every context-only need; Bumble adopted
two direct-answer claims and changed only their targeted needs. Deterministic claims
occurred once per result, unavailable evidence indices were hidden, routing-only
fields were absent, and each call passed in one attempt. One optional soft correction
was refused before transmission when it exceeded the adaptive reservation; its valid
sibling survived and the case still finalized, so no extra call was spent.

The exact Bumble output also showed that target identity alone cannot police compound
needs: selection reasons said that revenue growth and cash position answered only one
facet, but reflection deleted the remaining user-metrics and buyback/strategic-plan
facets. Current routing therefore persists `answer_scope=full|partial`; partial answers
must provide an exact residual need, and one routing round permits only one direct
answer per target. H_reflect receives that action and local validation requires removal
for full scope or exact residual replacement for partial scope. Non-answer and
unavailable actions still require preservation; old selections without scope remain
readable through the generic legacy path.

V74's terminal H_init failure was a separate correction-usability defect. The source
said `Stitch Fix, Inc. (SFIX) reported...`; initial and correction both returned the
absent paraphrase `SFIX reported...`. Strict rejection was correct, but feedback only
reported zero matches. Substantially overlapping absent Basic literals now receive
one at-most-800-character exact window from the named visible projection, together
with the rejected value and occurrence count. This is diagnostic only: the model must
still author a new ref and full byte-for-byte validation is unchanged. The two exact
V74 regressions plus all 475 repository tests and lint pass.

Current ordinary-loop repair (2026-08-30): immutable v73 contract
`7454f12...84f` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used 13 completed model attempts, `$0.02261952`, and
four data-ledger entries (three sandbox-denied preflight rows plus one external SEC
fetch). The first Fast case finalized and persisted Predictor plus post-hoc output;
the second reached bounded H_init, corrected routing, corrected soft-Signal execution,
and both H_reflect attempts. Locked Test remained sealed, the Registry stayed at its
initial hash, and Slow Loop did not start. The successor ceilings are 77 attempts,
`$17.98130444`, and 748 data requests.

Exact V73 inspection verified the V72 state-frontier repair live: H_init used 866 and
868 output tokens, returned bounded arrays, and its one correction changed only two
numeric beliefs whose strings did not match their cited claims. Routing correctly
reclassified a contextual revenue result from `answer_need` to `combine_evidence`,
and the soft-Signal correction correctly made guidance unavailable because the visible
source had no management guidance, outlook, or forecast. No extra H_reflect was used
on the first naturally completed case.

The second-case H_reflect adopted canonical `cash_reserves=2.07009e+09`, but rewrote
it as an unsupported `$2.07 billion`, removed the context-only revenue need, and kept
the directly targeted liquidity need. Its correction received the complete batch and
prose selection intents but repeated the same invalid state byte-for-byte. The model
view now exposes a deterministic exact claim once at result level, omits its repeated
evidence/interpretation copies, strips routing-only fields from executed intents, and
supplies one deterministic result-aware rule per prior need. Only adopted evidence
from an available direct-answer ref authorizes narrowing its named need; contextual
and unavailable refs require exact preservation. Local validation uses the same
availability boundary and hides unavailable evidence indices. The V73-shaped
regression plus all 472 repository tests and lint pass.

Current ordinary-loop repair (2026-08-30): immutable v72 contract
`e771419...8aab` rejected its only candidate during the third case at authoritative
pointers `round=0/cycle=0`. It used 23 paid model attempts—22 completed plus one
malformed response—`$0.03103324`, and four fetched/cache-hit SEC request-ledger
entries. The first two Fast cases finalized and persisted Predictor plus post-hoc
output. Locked Test remained sealed, the Registry stayed at its initial hash, and
Slow Loop did not start. The successor ceilings are 90 attempts, `$18.00392396`, and
752 data requests.

Exact third-case H_init inspection found a 44,946-byte request containing the bounded
38,855-character Basic projection. The response used exactly all 2,000 output tokens
and ended inside `supporting_evidence[0]`: before truncation it had enumerated 52
`current_beliefs`, ten open questions, ten next needs, and five resolved questions.
Its correction retained the same full Basic context and correctly became compact, but
paraphrased the first source literal (`Enbridge is considering...`) instead of copying
the visible contiguous text (`Canadian pipeline operator Enbridge Inc. is
considering...`). Strict literal rejection was correct; the design defect was that
the initial ResearchState contract had no compactness bounds, so its sole correction
was consumed by preventable transport truncation before semantic citation repair.

Provider-authored ResearchState is now a bounded decision frontier rather than a
second source summary: default field caps are 3/8/8/4/6/6/6, all arrays total at most
24 items, non-evidence text is at most 300 characters, initialize Basic literals at
most 800 characters, and canonical JSON at most 6,000 UTF-8 bytes. Raw prevalidation
aggregates every count/item/literal/byte violation without dropping content. A
full-token incomplete JSON response receives explicit truncation feedback. H_reflect
uses the larger of defaults and prior observed counts/bytes, so an old over-limit
checkpoint can be preserved but cannot grow; unchanged legacy long text remains
readable. Complete Basic/Raw Info/Signal/trajectory artifacts remain local. Three V72
regressions plus all 471 repository tests and lint pass.

Current ordinary-loop repair (2026-08-30): immutable v71 contract
`b4bd1e1...34a68` rejected its only candidate during the fifth case at authoritative
pointers `round=0/cycle=0`. Its preflight plus run used 30 completed model attempts,
`$0.03733464`, and five fetched/cache-hit SEC request-ledger entries. The first four
Fast cases finalized and persisted Predictor plus post-hoc output; case five reached
H_init, three routing rounds, one soft-Signal call, and two H_reflect calls before the
last routing correction failed. Locked Test remained sealed and the Registry stayed
at its initial version/hash, so Slow Loop did not start.

Exact case-five inspection covered all ten persisted requests and responses. H_init's
36,810-byte body used a bounded 31,015-character Basic projection and cited one literal
membership-revenue clause. The 43,144-byte guidance request returned canonical
`unavailable` because its visible projection contained no management guidance.
H_reflect then adopted only available revenue, cash, and operating-cash-flow results;
it correctly retained membership-count, future-projection, and capex/funding needs
that those contextual results did not answer. Its 9.1-9.5k-byte compact requests did
not repeat Raw Info. These state transitions match the design.

The failure was routing correction layering plus an over-strict new schema rule. In
three consecutive routing rounds, the model attached a need index to
`combine_evidence` to record which need the context supported. Runtime treated this
reasonable association as invalid and spent corrections clearing it. In the last
round, the initial output also selected `customer_concentration:v1` by analogy from
generic revenue-shortfall risk even though no current need/state named a customer,
client, order, or backlog. Validation reported only the non-answer targets; correction
cleared them, then the already-visible customer applicability error exhausted the sole
repair and discarded a separately plausible financing selection.

Current selection semantics allow any reason to retain zero or one valid association
index, while `answer_need` alone requires a target and alone authorizes H_reflect to
remove or narrow it. This preserves attribution without creating false resolution or
unnecessary calls. Routing now aggregates every structurally usable item's index
shape/bounds, reason/role, version-owned exclusion, required-context, and direct-answer
failure in the first feedback, naming selection paths/refs; malformed items remain
fail-closed and no error is repaired locally. The V71-shaped regression preserves the
financing association, reports customer applicability together with an independent
invalid index, and passes after one minimal correction. All 468 repository tests pass.
The successor contract must freeze 113 attempts, `$18.03495720`, and 756 data requests;
v71 remains immutable evidence.

Current ordinary-loop repair (2026-08-30): immutable v70 contract
`406f5f1...b71e2` rejected its only candidate during the fourth case at authoritative
pointers `round=0/cycle=0`. Its preflight plus run used 32 completed model attempts,
`$0.04067616`, and three successful/cache-hit SEC request-ledger entries. The first
three Fast cases completed H_init, all reached an evidence-exhaustion finalization,
and persisted Predictor plus post-hoc output. The fourth case reached H_init, routing,
soft-Signal execution, and both H_reflect attempts before rejection. Locked Test
remained sealed and Slow Loop did not start.

Exact Wynn artifacts exposed a cross-role attribution defect. The router called
`customer_concentration:v1` a direct answer to a request for specific recent customer
contracts, while its available result cited only strength across three sales channels.
H_reflect correctly kept the still-unanswered contracts need and therefore could not
satisfy the old coarse “remove any need” correction. An earlier completed Wynn
trajectory showed the more dangerous inverse: after adopting cash reserves and Q1
YoY revenue growth, correction deleted the unrelated Q2 revenue/EPS-versus-expectations
need, retained the compound debt/liquidity need unchanged, and passed. A routine Q2
earnings-release date was also accepted as neutral financing evidence.

Current selection output therefore binds every `reason_code=answer_need` to one
pre-execution `target_need_indices` entry; all other reasons carry an empty array.
Optional version-owned `routing_answer_need_phrases` separate direct need coverage
from contextual applicability. H_reflect receives the persisted target and, in both
continuing and terminal reflection, must remove or genuinely narrow only that target
while preserving every untargeted prior need byte-for-byte. Legacy committed
selections without the field remain readable. `customer_concentration:v1` now
requires customer/order objects in available evidence and directly answers only
concentration/dependence/diversification needs. `financing_listing_action:v1` rejects
routine-event evidence, while revenue-growth, cash, guidance, customer, and financing
versions expose bounded direct-answer objects. Exact v70 artifact replay changes the
customer selection to contextual and rejects the channel and routine-event evidence.
All 467 repository tests pass. The successor contract must freeze 143 attempts,
`$18.07229184`, and 761 data requests; v70 remains immutable evidence.

Current ordinary-loop repair (2026-08-30): immutable v69 contract
`4333c20...aab2e` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. Its preflight plus run used 12 completed model attempts,
`$0.01503012`, and three successful/cache-hit SEC request-ledger entries. The first
KGC case completed H_init, natural empty routing finalization, Predictor, and post-hoc
reflection. The second Wynn case reached H_init, routing, a shared soft-Signal initial
and correction, and H_reflect initial and correction—the deepest ordinary Fast
trajectory so far.

Exact persisted content exposed two independent semantic failures. The
`guidance_acceleration` correction cited a December 2022 Encore Boston Harbor
sale-leaseback (`$1.70 billion` proceeds, `$182 million` gain, `$1.51 billion` lease
liability) as positive current guidance even though no cited text named guidance,
outlook, forecast, or a management expectation. H_reflect then copied that false
Signal into a 678-character claim. The parser's 400-character maximum was absent from
the system output contract, and its correction feedback named no field or linked
belief, so the model repeated the invalid state byte-for-byte.

Signal versions may now own `result_required_evidence_phrases`; a non-unavailable
result must cite at least one measured-object phrase or correct to canonical
`unavailable`. `guidance_acceleration:v1` carries explicit guidance/outlook/forecast/
management-expectation phrases, while the real `$1,500 per ounce` guidance clause
still passes. Every ResearchState prompt now exposes the 1-400 claim bound, and raw
prevalidation aggregates exact `supporting_evidence[index].claim` paths, actual
lengths, and identical belief/contradiction paths before the sole correction. Direct
replay of v69's actual artifacts now rejects the sale-leaseback Signal and reports
`supporting_evidence[1].claim length=678` plus `current_beliefs[1]`. All 463 repository
tests and lint pass. The successor contract must freeze 175 attempts, `$18.11296800`,
and 764 data requests; v69 remains immutable evidence.

Current ordinary-loop repair (2026-08-30): immutable v68 contract
`9a70a62...421bb` rejected its only candidate after the first case at authoritative
pointers `round=0/cycle=0`. It used 16 attempts, `$0.02271920`, and three locally
denied SEC request-ledger entries. The v67 repair passed its paid boundary: a
30,830-character guidance projection sent both initial and correction calls, the
correction moved from a truncated `$1,` edge to the complete `$1,500 per ounce`
clause, and H_reflect removed the answered guidance need. A four-Signal deterministic
round then preserved state correctly when three results were unavailable and the
only available negative-word count was neutral.

The third routing response selected one relevant financing Signal plus an irrelevant
`customer_concentration` analogy for gold-price profitability. Its budget-trimmed
14,739-character shared context sent the initial call. Financing returned a separately
valid completed-share-sale result, while customer concentration inferred diversified
customers from silence and changed the case of four purported literal quotes. The
old mapper reported only `must map uniquely`; its 26,765-byte correction request then
exceeded the remaining budget, and the whole soft subgroup was discarded, including
the valid financing sibling. `customer_concentration:v1` now requires a pre-existing
customer/client/buyer/offtake/backlog/order/program object before routing. Literal
mapping feedback now names the evidence index, supplied projection, supplied/visible
occurrences, and matching ids. If an initial shared call has accepted siblings but a
pending correction cannot pass preflight, only the pending rows become canonical
`unavailable`; accepted results and paid usage survive for ordinary H_reflect. All
460 repository tests and lint pass. The successor contract must freeze 187 attempts,
`$18.12799812`, and 767 data requests; v68 remains immutable evidence.

Current ordinary-loop repair (2026-08-30): immutable v67 contract
`47d64a8...d364` rejected its only candidate after the first case at authoritative
pointers `round=0/cycle=0`. It used eight attempts, `$0.01462384`, and three SEC
request-ledger entries. H_init's initial UBS claim added an absent `$20` comparison;
its exact correction removed only that quantity. Routing initially repeated the v66
mature-project commercialization error, then its exact correction removed that ref
and retained the valid guidance selection, live-verifying the new applicability gate.

The selected guidance batch still made zero provider calls. Its persisted exact body
was 43,839 bytes plus a 4,000-token output reservation, while only 41,766 adaptive
tokens remained after H_init/routing and the frozen terminal reserve. The 30,830-
character projection therefore failed the conservative byte-for-token preflight;
Predictor/post-hoc completed, but the unchanged `continue` state remained correctly
ineligible. Soft-Signal projection is now budget-aware only when the complete bounded
request cannot fit: exact provider-body estimation preserves one highest-ranked
projection per selected Signal when feasible, then adds further ranked projections
while the whole request fits. Complete Raw Info, per-Signal projection scope, literal
mapping, validation, and the unchanged correction context remain intact. Exact v67
replay retains 15/19 projections and the complete `$1,500 per ounce` guidance clause,
with a 41,101 reservation under the 41,766 limit. All 458 repository tests and lint
pass. The successor contract must freeze 203 attempts, `$18.15071732`, and 770 data
requests; v67 remains immutable evidence.

Current ordinary-loop repair (2026-08-30): immutable v66 contract
`784b5eb...65bc5` rejected its only candidate on the first H_reflect correction at
authoritative pointers `round=0/cycle=0`. It used seven completed attempts,
`$0.01124816`, and three SEC request-ledger entries. H_init again passed in one call
with a literal two-row market claim and one unresolved guidance/project need. Routing
correctly marked guidance as `answer_need`; the soft batch's initial guidance quote
ended at `$1,`, and its correction moved to the overlapping projection containing the
complete `$1,500` clause. This live-verifies the projection-edge correction path.

The initial reflection then added an unsupported `2025` to the Signal claim and kept
the exact compound guidance/project need. Its aggregated error correctly named the
claim, linked belief, invalid needs field, index, and original value. Nevertheless,
correction returned the exact same ResearchState. Exact request inspection found a
contract contradiction: H_reflect's correction system said to act when
`validation_feedback` was non-null, but the actual user payload contained only
top-level `invalid_output` and `validation_error`; the named trigger field did not
exist. Provider usage also hit only 640 of 2,883 correction input tokens.

H_reflect now uses the stable correction transport already used by H_init/routing:
byte-identical system prompts, complete unchanged reflection context, and one final
`validation_feedback` field that is null initially and contains the rejected state
plus aggregated error on correction. Exact v66 replay confirms the new payload and a
minimal corrected state passes. The same routing output also treated Tasiast and
Lobo-Marte mature mining projects as product commercialization, then paid for an
LLM Signal to return unavailable. `commercialization_status:v1` now requires existing
product/technology/prototype/commercialization wording, while real prototype-product
needs remain routable. All 457 repository tests and lint pass.

Before the successor contract, the remaining frozen ceilings are 211 attempts,
`$18.16534116`, and 773 data requests; v66 remains immutable evidence and cannot
resume across the code revision.

Current ordinary-loop repair (2026-08-30): immutable v65 contract
`2568710...76a4` rejected its only candidate on the first H_reflect correction at
authoritative pointers `round=0/cycle=0`. It used six completed attempts,
`$0.00529704`, and three SEC request-ledger entries. Exact inspection covered the
complete proposer, H_init, routing, soft-Signal, H_reflect, and correction
requests/responses. The v64 repair passed its paid check: H_init required one call,
used only literal quantities, and returned two source-backed divestiture facts plus
one information need without temporal-metadata leakage.

Routing reasonably selected `financing_listing_action:v1` and a deterministic cash
context. The soft result literally confirmed the completed Asante share sale; cash
was honestly unavailable. The initial reflection adopted the available evidence but
retained its compound need for transaction terms, closing dates, and proceeds use.
Only the sale terms were partly answered, so the logically correct transition was to
narrow the need to the two unresolved facets. The old correction error stated only
that the need set must change, while the shared correction contract required every
named field/item to change; it did not identify one exact field or indexed value, and
the model returned the same output byte-for-byte.

H_reflect feedback now names `invalid_field='next_information_needs'` and supplies
every retained indexed value, while explicitly requiring only an evidence-supported
removal/narrowing and byte-for-byte preservation of unanswered items. The router may
use `answer_need` only for a facet directly covered by the card description and may
not promise coverage of other facets; contextual cards use another accurate reason.
H_init now asks only for facts absent from Basic Info and its returned state, and
partly answered compound questions retain only unresolved facets. Exact v65 replay
rejects the persisted no-op and accepts a split into closing-date and proceeds-use
needs. All 455 repository tests and lint pass.

Before the successor contract, the remaining frozen ceilings are 218 attempts,
`$18.17658932`, and 776 data requests; v65 remains immutable evidence and cannot
resume across the code revision.

Current ordinary-loop repair (2026-08-30): immutable v64 contract
`04fe683...8390` rejected its only candidate on the first H_init correction at
authoritative pointers `round=0/cycle=0`. It used three completed attempts,
`$0.00808780`, and three SEC request-ledger entries. The proposer passed in one
cache-heavy call and made the required attributable change: it retained the compact
market backbone, added a bounded earnings-call request, and expanded H_init's
expectation-gap instruction without changing Predictor semantics. The complete
proposer request/response and both H_init requests/responses were inspected.

The initial ResearchState contained two otherwise grounded transcript claims that
added `2025` to `Q2`/`Q3` even though their exact quoted spans contained only the
quarter labels, plus two other quantitative beliefs that paraphrased rather than
copied their evidence claims. The old prevalidator reported only the two missing-year
claims and linked beliefs. The 10,624/11,899-token-cache-hit correction fixed the two
unreported belief links but preserved every explicitly rejected `2025`, so validation
failed again. This repeats v62's temporal-metadata pattern and shows that sequentially
exposing locally decidable defects wastes the sole correction.

The initial role instruction now states that a year, quarter number, date, or other
temporal quantity cannot be borrowed from projection metadata, neighboring text, or
general document context. Before correction, raw validation aggregates every
decidable missing quantity and quantitative assertion-link path. Correction also
states the minimal safe repair: delete each listed absent quantity from the named
claim and linked assertion unless a same-claim literal containing it is added. It
still never rewrites evidence locally. The persisted v64 invalid state replays to all
six exact paths, and a minimal corrected form passes. All 455 repository tests and
lint pass.

Before the successor contract, the remaining frozen ceilings are 224 attempts,
`$18.18188636`, and 779 data requests; v64 remains immutable evidence and cannot
resume across the code revision.

Current ordinary-loop repair (2026-08-29): immutable v63 contract
`8d43153...01e1` rejected its only candidate after one otherwise complete and
correctly judged case at authoritative pointers `round=0/cycle=0`. It used 11
completed attempts, `$0.01701224`, and three SEC request-ledger entries. Exact
inspection covered proposer, H_init initial/correction, both routing decisions, the
soft-Signal initial/correction, H_reflect initial/correction, both deterministic
Signal results, Predictor, and post-hoc. Precise correction feedback worked live:
H_init removed only an unsupported date, the soft Signal replaced a projection-edge
`$1,` quote with the complete `$1,500` clause, and H_reflect removed only the need
that its adopted `answer_need` guidance evidence had answered.

The second routing response then relabeled an Asante equity sale as a customer order
and selected `order_quality:v1`; its actual Signal request was persisted but refused
before transmission by the conservative budget reservation. The completed
`gross_margin_change` and `revenue_acceleration` results were both honestly
`unavailable`. Runtime evaluated the generic all-unavailable shortcut before the
partial soft-refusal terminal rule, skipped the required H_reflect call, left
`decision=continue`, and excluded the case despite a complete correct Predictor and
post-hoc result.

Signal versions may now own a finite `routing_required_research_phrases` gate.
`order_quality:v1` requires existing purchase-order, customer-order, backlog,
contract-award, or customer-commitment wording in accepted research context; a new
analogy invented only in routing prose cannot satisfy it. When a soft request is
refused after an all-unavailable deterministic partial batch, runtime now performs
one terminal H_reflect call, and validation requires every prior field and item to
remain byte-for-byte while only `decision` changes to `finalize`. Both constraints
pass exact v63 artifact replay, all 454 repository tests, and lint.

Before the successor contract, the remaining frozen ceilings are 227 attempts,
`$18.18997416`, and 782 data requests; v63 remains immutable evidence and cannot
resume across the code revision.

Current ordinary-loop repair (2026-08-28): immutable v62 contract
`fe5027b...a28d2c` rejected its only candidate on the first H_init case at
authoritative pointers `round=0/cycle=0`. It used four attempts, including one
zero-cost sandbox-denied HTTP attempt, `$0.00785680`, and three SEC request-ledger
entries. The proposer passed in one call with a 1,152/1,158-token cache hit and
returned a market/news/earnings-call Plan whose four actual role fields preserve the
fixed Predictor boundary. H_init then used 11,103 input tokens; its only local defect
was `supporting_evidence[2]` claiming `Q2 2025` while the exact quote said only
`second quarter`. The correction had an 11,008/11,941-token cache hit but returned
the identical ResearchState byte-for-byte and failed again.

Exact correction-context inspection found that a local semantic `ValidationError`
was wrapped twice as `invalid JSON fields` containing every ResearchState key, while
the role instruction required every named field to change. The raw quantity
prevalidator also named only the evidence ref, not its identical quantitative belief.
Semantic errors now pass through unchanged; quantity feedback names both the exact
evidence index and every linked belief/contradiction index, and correction preserves
unrelated valid content byte-for-byte. The persisted v62 response replays to the new
precise error: `supporting_evidence[2]`, missing `2025`, linked
`current_beliefs[1]`.

All 450 repository tests and lint pass. Before the successor contract, the remaining
frozen ceilings are 238 attempts, `$18.20698640`, and 785 data requests; v62 remains
immutable evidence and cannot resume across the code revision.

Current ordinary-loop repair (2026-08-28): immutable v61 contract
`1efbf49...88efa` reached one complete real case, then rejected the only candidate
at authoritative pointers `round=0/cycle=0`. It used 11 completed model attempts,
`$0.01205232`, and five SEC request-ledger entries. Exact inspection covered both
proposer attempts/corrections, H_init, three routing decisions, deterministic Signal
results, Predictor, and post-hoc. Every selected deterministic Signal returned honest
`unavailable`; H_reflect correctly used zero calls. The final routing decision was
empty, but runtime left the unchanged `continue` state and excluded the otherwise
complete case as `unfinalized_case`.

An empty selection or exhausted eligible Registry now represents natural evidence-
collection closure, not a claim that uncertainty was resolved. Runtime copies the
complete last ResearchState, changes only `decision=continue` to `decision=finalize`,
asserts every other field remains equal, and preserves
`termination_trigger=no_signal_match`. All-unavailable batches still skip H_reflect;
cost/round/call exhaustion without a reflectable terminal batch remains ineligible
and cannot use this rule.

All 449 repository tests and lint pass. Before the successor contract, the remaining
frozen ceilings are 242 attempts, `$18.21484320`, and 788 data requests; v61 remains
immutable evidence and cannot resume across the code revision.

Current ordinary-loop repair (2026-08-28): immutable v60 contract
`ae7b3a9...2c9e9` reached the first complete real case, then rejected the only
candidate at authoritative pointers `round=0/cycle=0`. It used 15 completed model
attempts, `$0.01937908`, and four SEC company-facts request-ledger entries. Exact
inspection covered proposer, H_init, three routing/reflection rounds, soft-Signal
initial/correction, Predictor, and post-hoc payloads/responses. The first reflection
adopted available `guidance_acceleration` evidence selected specifically to answer the
production/cost need, yet retained all five needs unchanged. On the third round a
soft-Signal request could not pass conservative pre-send reservation after four
deterministic results had completed; H_reflect again returned `continue`, the fixed
Predictor and post-hoc still completed, and the trajectory was excluded as
`unfinalized_case`.

H_reflect now receives exact executed selection intents. A continuing state that
adopts evidence from an available `answer_need` selection must remove or genuinely
narrow at least one need instead of returning the same set. The last reflectable
batch also receives an exact terminal directive for round/call exhaustion or a
pre-send soft-Signal budget refusal; the model must author `finalize` while it may
retain unresolved needs/open questions. One correction remains available, and
runtime never mutates the decision. The v60 states replay directly into both new
validation errors. The financial-statements Basic request was also audited: its local
SEC-derived `financials` document was seven days outside the Plan's 180-day lookback,
so the unresolved acquisition is a real coverage gap rather than a source-alias bug.

All 449 repository tests and lint pass. Before the successor contract, the remaining
frozen ceilings are 253 attempts, `$18.22689552`, and 793 data requests; v60 remains
immutable evidence and cannot resume across the code revision.

Current Slow-bootstrap handoff (2026-08-28): immutable v59 contract `60287299...2ad8` committed cycle 1 at authoritative pointers `round=0/cycle=1` after one H1 attempt, `$0.00101332`, twelve provider requests (two SEC profiles and ten SEC company-facts fetches), and no Registry change. H1 passed in one call with a 2,432/2,521-token cache hit. H2 deterministically shortlisted 12 refs for each hypothesis and used zero calls. The relaxed full-document rule admitted strong near-complete packets, then the exact model-excerpt recomputation rejected every case because only one or two terms survived the 1,200-character window; H3 and Update therefore correctly used zero calls. This live-verifies that the new threshold improves retrieval reach without bypassing the visible-evidence boundary. A second invocation made no requests/calls and was rejected because `slow_bootstrap` is intentionally single-cycle, so E1/E2 cycle 3 cannot be tested in bootstrap mode.

No additional code change follows v59. The remaining work moves to an ordinary `fast_then_slow` contract so newly committed Fast learning can drive Update and repeated cycles can reach exploration. Under the frozen remaining attempt ceiling, the verification contract will use one full 24-case candidate per Fast round rather than three parallel candidates; this preserves the complete per-case Signal/evidence/learning path being tested while fitting at least two cycles needed for Update.

V59 leaves 268 attempts, `$18.24627460`, and 797 data requests. The repository remains at the 447-test/lint-passing `07e20ab` checkpoint with no task-file changes beyond this recorded handoff.

Current Slow-bootstrap handoff (2026-08-28): immutable v58 contract `512d16da...d8fd` committed cycle 1 at authoritative pointers `round=0/cycle=1` after two H1 attempts, `$0.00253764`, two SEC profile requests, and no Registry change. Initial validation rejected three feature-bearing group definitions plus one alternate `underperform` outcome; correction produced three valid fixed-group hypotheses. H2 deterministically shortlisted 12 refs for each with zero calls. H3 then used zero calls because no hypothesis had two positive and two control cases passing query coverage, and Update correctly used zero calls. Exact resolution inspection showed many otherwise relevant filings at 4/5 terms plus an ordered pair for production/consensus or 3/4 plus `revenue growth` for composition, but the all-terms packet rule discarded them before the bounded excerpt could be assessed. This treated abstract query modifiers such as `comparison` and `trajectory` as mandatory Boolean terms rather than retrieval vocabulary.

H3 query coverage now requires all terms for one/two-term topics and a rounded-up 75-percent supermajority for longer topics, always with at least one short-range consecutive query pair when more than two terms exist. The exact v54 false-feasibility pattern remains rejected: its visible excerpts had only 3/6 terms or no ordered pair, below the new 5/6 requirement. The same threshold is recomputed over exact masked excerpts after projection.

Verification for strong-supermajority H3 coverage: all 447 repository tests and lint pass, including 4/5 acceptance and 3/6 rejection. V58 used two attempts and two provider requests, so the next fresh ceiling is 269 attempts, `$18.24728792`, and 809 data requests.

Current Slow-bootstrap handoff (2026-08-28): immutable v57 contract `c6221179...39b9` committed cycle 1 at authoritative pointers `round=0/cycle=1` after two H1 attempts, `$0.00238112`, two SEC profile requests, and no Registry change. Initial validation correctly rejected three feature-bearing `Discovery group: issuers with ...` parentheticals. Correction rewrote all three to the feature-free alias `positive/control cases (fixed Discovery group)`, but the same-label whitelist was still overly literal and rejected that finite alias before H2. Exact replay of the persisted correction now accepts all three hypotheses under the repaired parser; no resampling was used to establish the fix.

H1 now accepts exactly two feature-free alias families: the same explicit Discovery label and `(fixed Discovery group)` attached to an already positive/control-labeled prefix. Any feature/result/issuer condition, colon payload, or opposite label remains a redefinition failure. The item-local correction instruction from v56 remains active.

Verification for finite fixed-group aliases: all 446 repository tests and lint pass, and the exact v57 correction response replays with all three ids accepted. V57 used two attempts and two provider requests, so the next fresh ceiling is 271 attempts, `$18.24982556`, and 811 data requests.

Current Slow-bootstrap handoff (2026-08-28): immutable v56 contract `7513df44...b6fb` committed cycle 1 at authoritative pointers `round=0/cycle=1` after two H1 attempts, `$0.00194404`, two SEC profile requests, and no Registry change. The initial cached-prefix response produced three grounded hypotheses; only `revenue_beat_prior_quarter` was rejected as a restatement of an existing stable revenue-growth construct. The other production-guidance and analyst-revision hypotheses were not named by validation. The correction nevertheless returned only `{"hypotheses":[]}`, so the nonempty-demand guard correctly failed it, but the whole portfolio lost two independent valid items and H2/H3 did not run. Update again correctly used zero calls.

H1 correction now explicitly preserves every hypothesis id not named by the aggregated validation error byte-for-byte, changes/removes only named invalid items, and forbids using an empty correction to erase unaffected work when demand is nonempty. This retains the one bounded correction and all local semantic gates while preventing one bad portfolio item from creating an all-or-nothing failure.

Verification for item-local H1 correction instructions: all 445 repository tests pass and repository lint passes. V56 used two attempts and two provider requests, so the next fresh ceiling is 273 attempts, `$18.25220668`, and 813 data requests.

Current Slow-bootstrap handoff (2026-08-28): immutable v55 contract `1a20af5a...8f00` committed cycle 1 at authoritative pointers `round=0/cycle=1` after two H1 attempts, `$0.00212716`, four SEC profile request-ledger entries, and no Registry change. The initial response repeated three circular parenthetical definitions and one `subsequent quarters` target; the single correction received one aggregated safe error with a 2,432/3,085-token cache hit and removed every candidate-specific definition/future horizon. It then used `positive cases (the Discovery positive group)` and the analogous control alias. The over-broad parentheses guard rejected these unchanged-label aliases before H2, although they do not redefine membership. Exact replay against the repaired parser accepts all three correction hypotheses in one call. H2/H3 were therefore not reached in the immutable v55 run, and Update correctly used zero calls.

The H1 guard now distinguishes an exact same-label Discovery alias from a feature-bearing or cross-label parenthetical. Membership clauses and candidate-specific parentheses remain invalid; only `positive/control cases|groups|cohorts (the Discovery same-label cases|groups|cohorts)` pass. This is a semantic narrowing of the false positive, not a relaxation of the frozen-label boundary.

Verification for same-group alias handling: all 445 repository tests pass with the bundled Python 3.12 runtime; repository lint passes, and the exact v55 correction response replays as accepted. V55 used two attempts and four provider request-ledger entries, so the next fresh ceiling is 275 attempts, `$18.25415072`, and 815 data requests.

Current Slow-bootstrap handoff (2026-08-28): immutable v54 contract `d47242d5...5735` committed cycle 1 at authoritative pointers `round=0/cycle=1` after two paid attempts, `$0.00216916`, four SEC profile request-ledger entries across preflight/execution, and no Registry change. Exact H1/H3 wire requests, responses, token usage, anonymous H2 briefs/rankings, all model-visible evidence excerpts, Raw Info resolution audits, ledgers, transition, and Locked-Test flag were inspected. H1 returned three hypotheses and deterministic H2 used zero calls. Two hypotheses lacked enough point-in-time cases; the revenue-composition hypothesis reached H3, whose correct `inconclusive` response noted that the visible excerpts contained only unrelated operating/risk/filer prose. The controller had nevertheless labeled those packets sufficient using terms found only across the hidden full document: none of the four exact 1,200-character model excerpts retained the complete six-term query, and `composition` was absent from all four. The H1 response also redefined frozen group membership with `positive/control cases are issuers ... as/that ...`, which the prior parentheses-only guard missed.

H1 now rejects both parenthetical and membership-clause group redefinitions and tells the correction to express a feature difference between already frozen groups. H3 now recomputes the same distinct-term and short-range-pair coverage over the exact identity-masked excerpts after projection; hidden full-document coverage remains audit-only, and an insufficient visible packet becomes local evidence-unavailable before a model call. This removes the exact v54 false-feasibility call without weakening semantic `inconclusive`, source lineage, or point-in-time checks.

Verification for membership-bound H1 and model-visible H3 coverage: all 444 repository tests pass with the bundled Python 3.12 runtime; repository lint passes. V54 used two attempts and four provider request-ledger entries, so the next fresh ceiling is 277 attempts, `$18.25627788`, and 819 data requests. A fresh frozen contract is required to live-validate H1 correction and visible-excerpt gating; ordinary Fast-derived learning remains required to exercise Update.

Current Slow-bootstrap handoff (2026-08-28): immutable v53 contract `4212dbe3...e6e6` committed cycle 1 at authoritative pointers `round=0/cycle=1` after one paid H1 attempt, `$0.00068292`, four successful SEC profile requests across preflight/execution, and no Registry change. Exact H1 wire prompt, actual field inventory, response, cache usage, local result, ledgers, transition, and Locked-Test flag were inspected. The 2,425-input-token call had a 2,304-token cache hit but returned only `{"hypotheses":[]}` in seven output tokens. H2 correctly used zero calls but had no hypothesis to shortlist, so H3 and Update were not called. The reasonless empty portfolio contradicted the same nonempty four-item Fast backlog that produced valid canonical candidates in v52 and did not establish demand exhaustion.

H1 retains the fixed positive/control target, alternate-horizon rejection, id/query-scoped duplicate boundary, aggregated feedback, stable correction prefix, standalone `P(` rule, `yoy` identity preservation, case/group/cohort synonyms, no invented refs, no short-window market outcomes, no data-readiness statements, no raw absolute cross-issuer scale, no fixed-group redefinition, group-level falsifiers, and concise two-to-eight-term retrieval topics. The controller constructs the bounded anonymous H2 briefs before H1 and publishes only their actually present optional fields and categorical values. H1 `applicability` is one machine-checkable, non-conjunctive rule: all ready issuers, bounded business-description topics, or one observed industry/sector/exchange/size/listing-age/Raw-Info-source rule. Free prose, absent values, and hidden document prerequisites are rejected together; profile shortage consumes zero H1 tokens. When real `signal_need_items` are nonempty, H1 must return at least one grounded hypothesis; a reasonless empty portfolio is valid only when the demand list is empty. H2 is a deterministic local shortlist over that exact rule, preserving bounded brief order without a model prompt, quote/reason schema, or correction. H3 retains hidden-body removal, complete ordered query coverage, and distinct inconclusive/evidence-unavailable state.

Verification for demand-bound nonempty H1: all 442 repository tests pass with the bundled Python 3.12 runtime; repository lint passes. V53 used one attempt and four provider requests, so the next fresh ceiling is 279 attempts, `$18.25844704`, and 823 data requests. A fresh frozen contract is required to live-validate empty correction, zero-call H2, and reach H3; ordinary Fast-derived learning remains required to exercise Update.

Current v23 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v23` froze exact contract `5bc1b988...cbc03` at code revision `7872ddf`, reached the first proposer approval boundary, and transmitted zero LLM requests at authoritative pointers `round=0/cycle=0`; Locked Test remained sealed. Its exact 5,859-byte proposer body was inspected and contained only the fixed prior, one committed historical seed, empty meta-info, source enum, and attributable Plan-change constraint. Readiness used three real SEC requests. A cross-request audit of v22 then isolated the largest avoidable correction cost: a 38.5k-character shared soft-Signal projection was correctly sent only once per batch, but the correction changed its system prompt and therefore received only 384-512 cache-hit tokens while repeating roughly 12k input tokens. Initial/correction Signal calls now use one byte-identical conditional system prompt, keep a stable full `batch_signal_refs`, and append only dynamic `validation_feedback` after the unchanged projection. No context, Signal skill/spec, evidence, or local validation was removed; conservative reserves remain cache-miss priced. The v23 contract cannot resume after this code change. The next contract must freeze 521 attempts, `$18.58031964`, and 921 real provider requests; v23 and earlier workspaces remain immutable evidence.

Verification for the soft-Signal correction-prefix repair: all 384 repository tests and lint pass.

Current v22 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v22` ended normally at authoritative pointers `round=0/cycle=0` after 28 attempts (26 completed plus two paid malformed-JSON failures), `109,548` input / `15,804` output tokens, `$0.03952368` settled cost, and four real SEC requests. All three candidates reached the first case and failed during H_reflect. Exact responses proved that adopting evidence is not equivalent to answering every active need: one response newly resolved production/cost guidance while retaining that same need, while two other responses correctly retained broad catalyst or gold-price questions that their new company-price/news evidence did not answer. The old blanket progress gate therefore both missed an internal stale need and forced unrelated unanswered needs to change. Exact unanswered needs may now remain byte-for-byte, changed needs retaining at least 90% of an old need remain invalid, and a newly resolved question sharing an ordered three-content-word phrase with an exact retained need fails closed. Unavailable Signal belief/resolution drift is enforced independently, and directly decidable Signal-quantity plus need-transition errors share the one correction. The next contract must freeze 521 attempts, `$18.58031964`, and 924 real provider requests; v22 and earlier workspaces remain immutable evidence.

Verification for the v22 reflection-state separation: all 384 repository tests and lint pass.

Current v21 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v21` was intentionally interrupted at authoritative pointers `round=0/cycle=0` after 34 reserved attempts (32 completed, one paid malformed-JSON failure, and one conservatively retained interruption), `$0.03687852` settled cost, a `$0.00471660` interrupted reservation, and three real SEC fetches. The new commercialization boundary worked on the actual mature-mining batch, returning `unavailable`, and H_reflect wire bodies fell to 6.8-9.4k bytes without canonical document ids/hashes/raw spans. Exact responses nevertheless exposed three logical defects: an unavailable customer-concentration interpretation became a false absence belief and resolved question; the only reflection correction embedded the entire prior need in a longer “given the absence...” sentence; and another selector returned an empty batch for an explicit production/cost `guidance` need. Every downstream model view now canonicalizes unavailable as coverage-only, same-or-larger need lists reject a new need retaining at least 90% of a prior need's word set, and version-owned `routing_need_phrases` trigger one empty-selection correction without local Signal choice. The next contract must freeze 549 attempts, `$18.61984332`, and 928 real provider requests; v21 and earlier workspaces remain immutable evidence.

Verification for the v21 semantic-state and routing repair: all 383 repository tests and lint pass.

Current v20 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v20` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 41 settled attempts (40 completed plus one paid malformed-JSON failure), `$0.05078472` actual cost, and three real SEC fetches. Every one of its seven actual `H_reflect` calls adopted new Signal evidence while returning the exact same information needs and never resolving a question; the role also received canonical long `exact_span` payloads with transcript/market serialization noise. One initialization response contained five missing evidence kinds plus three already-visible unsupported quantities, but sequential validation exposed only the first layer before the sole correction. A soft Signal response also classified ordinary mature-mine production as a positive product-commercialization transition. H_reflect now receives an 8k bounded normalized evidence view and must make a substantive state transition after adopting evidence; one correction aggregates all decidable tagged-ref/Basic-quantity errors; and the seed commercialization card/skill explicitly excludes routine mature operations. The next contract must freeze 583 attempts, `$18.66143844`, and 931 real provider requests; v20 and earlier workspaces remain immutable evidence.

Verification for the v20 adaptive-context, layered-correction, and Signal-applicability repair: all 380 repository tests and lint pass.

Current v19 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v19` was intentionally stopped at authoritative pointers `round=0/cycle=0` after seven reserved attempts (six completed plus one conservatively retained interruption), `$0.00792036` settled cost, a `$0.00322868` interrupted reservation, and two real provider fetches. Its second actual proposer response copied all three output-contract placeholders—`complete initialization instructions`, `complete reflection instructions`, and `complete final analysis instructions`—and runtime accepted that non-executable Plan because the strings were non-empty and differed from the parent. The output example now contains logically complete role instructions, exact example echoes and generic placeholders are rejected, and every proposed `H_*` field must cover its role-specific semantics before parent/focus comparison. Correction feedback names every field that must change and rejects an unchanged replay. The next contract must freeze 624 attempts, `$18.71222316`, and 934 real provider requests; v19 and earlier workspaces remain immutable evidence.

Verification for the v19 Plan-content repair: all 377 repository tests and lint pass.

Current v18 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v18` ended normally at authoritative pointers `round=0/cycle=0` after 29 attempts (27 completed plus two paid malformed-JSON failures), `$0.04007276` settled cost, and three real provider fetches. Its deepest candidate reached two Signal rounds, revealing that the 2025 Wynn case was incorrectly using 2017/2018 `Revenues` facts even though current 2024/2025 facts existed under `RevenueFromContractWithCustomerIncludingAssessedTax`; H_reflect then described the stale result as positive operational performance. The financial parser now recognizes both assessed-tax revenue aliases and makes any current period older than 550 days `unavailable`. Exact replay selects 2025-Q1 revenue growth `-0.0872356` and operating-cash-flow margin `0.0786722`, not the old 2018 values. Reflected claims may copy a deterministic Signal's exact canonical numeric interpretation, but still reject rounded percentages or extra raw quantities. `H_init` also stops asking for runtime-owned evaluation baseline dates/prices. The next contract must freeze 631 attempts, `$18.72337220`, and 936 real provider requests; v18 and earlier workspaces remain immutable evidence.

Verification for the v18 current-period and derived-claim repair: all 376 repository tests and lint pass.

Current v17 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v17` ended normally at authoritative pointers `round=0/cycle=0` after 11 attempts (10 completed and one retryable SSL failure), `$0.01099476` settled cost, and two real provider fetches. The first candidate's actual routing response selected four relevant Signals, but copied the visible card categories `catalysts`, `risks`, and `product` into `context_tags`; those values are absent from the frozen context-tag enum, the correction repeated them, and runtime rejected the candidate before executing any Signal. Auxiliary routing tags now follow the intended local non-semantic path: normalize, deduplicate, drop unknown values, and retain at most four; wrong refs, missing fields, and invalid reason/role enums still correct once and fail closed. The other two candidates independently failed the unchanged quantitative citation gate. The next contract must freeze 660 attempts, `$18.76344496`, and 939 real provider requests; v17 and earlier workspaces remain immutable evidence.

Verification for the v17 tag-normalization repair: all 374 repository tests and lint pass.

Current v16 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v16` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 15 reserved attempts (14 completed plus one conservatively retained interruption), `$0.01329608` settled cost, a `$0.00543816` interrupted reservation, and three real provider fetches. The first actual routing request named latest quarterly revenue and operating cash flow as an information need and exposed the unexecuted `operating_cash_flow_margin:v1`, `revenue_growth_yoy:v1`, and `revenue_acceleration:v1` cards, yet the model returned an empty batch and runtime prematurely finalized research. Empty routing now receives one semantic correction only when a need repeats an exact three-or-more-word phrase from an available Signal ref; unmatched empty remains valid, fuzzy/single-word matching is forbidden, and runtime never selects a Signal locally. The next contract must freeze 671 attempts, `$18.77443972`, and 941 real provider requests; v16 and earlier workspaces remain immutable evidence.

Verification for the v16 routing repair: all 373 repository tests and lint pass.

Current v15 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v15` ended normally at authoritative pointers `round=0/cycle=0` after 40 completed attempts (`110,543` input / `16,595` output tokens, `$0.04024524`) and three real provider fetches. Three accepted Plans all failed closed during initialization: one SEC table literal was genuinely ambiguous because it occurred twice; two other responses exposed a context-usability defect by constructing shortened market JSON citations and repeating the same rejected provenance after correction. The exact Life Time request also showed `H_init` treating the fixed six-month doubling evaluation outcome as if it were an issuer target whose terms should be researched. The role prompt now states that this is an evaluation definition, requires complete visible market rows, and makes clear that a correction must replace or remove every rejected item without any local evidence repair. The next contract must freeze 686 attempts, `$18.79317396`, and 944 real provider requests; v15 and earlier workspaces remain immutable evidence.

Verification for the v15 prompt/context repair: all 372 repository tests and lint pass.

Current v14 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v14` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 14 reserved attempts (13 completed plus one conservatively retained interruption) and two real SEC fetches. Candidate c01 was incorrectly rejected because its exact SEC facts `1605300000`/`2446400000` were reasonably expressed as `$1.6053 billion`/`$2.4464 billion`; numeric support now treats each explicitly unit-qualified token's unscaled and exactly Decimal-scaled values as alternatives, never as rounded approximations. This preserves the prior legitimate `2,521,793 thousand` literal match while accepting exact raw-unit conversion. c02 then produced two useful correct-case decision drivers, but the fixed-semantics scanner wasted a correction on the descriptive phrase “far below the doubling threshold”; bare threshold/cutoff references are now allowed, while set/use/change actions, explicit replacement numeric thresholds, probabilities, and odds remain blocked. The next contract must freeze 726 attempts, `$18.83341920`, and 947 real provider requests; v14 and earlier workspaces remain immutable evidence.

Verification for the v14 repairs: all 371 repository tests and lint pass.

Current v13 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v13` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 16 reserved attempts (15 completed plus one conservatively retained interruption) and two real SEC fetches. Its first soft-Signal response quoted the complete `$1,500` guidance sentence but attached the neighboring truncated projection id: that id contained the quote zero times, while the full visible projection set contained it exactly once under `projection_a3f27...`. The old Signal mapper rejected it, spent its sole correction, then lost valid guidance when the correction was malformed. Signal evidence now follows the existing Basic-ref rule: a wrong/unknown projection id is deterministically relocated only when the unchanged exact quote has one total visible occurrence; zero/multiple matches still fail closed, and internal-edge checks run on the resolved projection. v13 also live-verified that correct post-hoc output now retains three concrete decision drivers and that later H_reflect preserved the earlier Signal claim. 369 repository tests and lint pass. The next contract must freeze 740 attempts, `$18.86772452`, and 949 real provider requests; v13 and earlier workspaces remain immutable evidence.

Current v12 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v12` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 23 reserved attempts (22 completed plus one conservatively retained interruption) and two real SEC fetches. Exact first-case artifacts exposed a cross-layer evidence loss: the soft-Signal batch cited Paracatu 585,000 ounces/Tasiast 119,000 ounces and a guidance literal ending at the internal projection boundary `$1,`, but H_reflect rewrote them as unsupported 513,000-ounce/$2,200 and $1,400 claims; the full overlapping projection actually said $1,500. Current-batch Signal claims now require all quantities in their exact referenced evidence, retained older Signal claims are immutable when their backing batch is no longer visible, and internal projection-edge citations fail closed in favor of a complete overlapping clause. Exact post-hoc payloads also proved its Basic source index was silently empty because the compactor misread an already-compact Predictor view, and every framework-correct response returned an all-empty reflection despite explicit guidance; the source index now survives without restoring full Basic text, and correct post-hoc output requires a concrete `decision_drivers` item. Finally, Wynn-branded property names survived Predictor masking because the distinctive four-letter leading brand was excluded; non-generic four-letter brands are now masked and scanned. 368 repository tests pass. The next contract must freeze the remaining extension ceilings of 756 attempts, `$18.89346688`, and 951 real provider requests. v12 and earlier workspaces remain immutable evidence.

Current v11 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v11` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 14 attempts and three real SEC fetches. The first case completed in seven model calls with deterministic terminal closure; provider usage proved real cache reuse, including 1,024/1,047 input tokens on each proposer and 9,984/10,036 on a soft-Signal batch. The second case exposed that a `10-q` Basic request ranked/chunked raw SEC markup before projection: its model view contained 12 HTML/XBRL tags, seven `style=` fragments, and 10,064 quarterly characters, while one accepted literal claim combined an ending cash balance absent from its cited span. Full-document readable-text ranking now maps selected windows back to exact raw offsets, removes complete and boundary-fragment tags, decodes single-character HTML entities, and enforces numeric claim support across same-claim Basic refs. Exact v11 replay produces zero tags/style/XBRL/entities and reduces the Basic payload from 22,610 to 17,548 characters while retaining the relevant cash/debt prose. 362 repository tests pass; the next contract must freeze the remaining extension ceilings of 779 attempts, `$18.91672256`, and 953 real provider requests. The v10 and earlier paragraphs below are immutable historical handoff context.

Current v10 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v10` froze exact contract `010d3aa0...f20db` with 800 newly authorized attempts, `$18.93681116` remaining cumulative cost, and 958 remaining provider requests. It was intentionally interrupted after seven reserved attempts and two real SEC fetches at authoritative pointers `round=0/cycle=0`. Exact responses proved that fixed-semantics scanning misclassified “without calculating probabilities” as affirmative drift and that an accepted Plan ignored its deterministic `B/H_init` change focus by changing only `H_analyse`; Responses-style nested cache usage was also invisible. The owning specs and runtime now distinguish explicit negative guardrails, report the actual prohibited match, enforce the named focus against every parent, and normalize nested `cached_tokens`. The v10 artifacts remain read-only evidence. 359 repository tests pass; the next workspace must freeze the remaining extension ceilings of 793 attempts, `$18.93009424`, and 956 real provider requests. The earlier v6 paragraph and detailed module row below remain historical handoff context.

Current v6 verification (2026-08-23, v27 remediation): v26 live-validated schema-only proposal, stable correction caching, exact guard-state preservation, and finalized fitness exclusion; candidate evaluation now fail-fasts after the first unfinalized trajectory. V27 then proved that omitting invocation-level data authorization could incorrectly turn `external_not_authorized` into Random-cohort substitution. Enabled data contracts now pause before cycle/snapshot/resolution unless the same invocation explicitly supplies `--data-external`. Slow H1/H2/H3/Update remain not live-verified. [`self-evolution-live-validation-audit-2026-08-23.md`](self-evolution-live-validation-audit-2026-08-23.md) contains the exact v25-v27 evidence.

Earlier v6 verification (2026-08-23): the standing-authorized v4-v9 remediation chain terminated exactly at its cumulative 800-attempt ceiling after `$1.03074748` settled cost, `$0.03244136` conservatively retained interrupted reservations, and 42 real provider fetches. V7 committed one complete 24-case Plan at Combined Binary F1 `0.666667` and authoritative pointers `round=1/cycle=0`; no workspace reached Slow cycle 1, and v9 correctly stopped at its frozen remaining cap of 129 attempts without resetting the campaign budget. Exact live-context inspection found provider-associated other-company news propagating through Basic Info, post-hoc, critic, and Round reflection; first-per-assessment meta sampling hiding richer root causes; a single-Plan Round reflector fabricating horizontal value by copying the critic; uninterpretable document hashes repeated in routing context; and a redundant terminal LLM rewrite that usually changed nothing but sometimes erased hypotheses or falsely resolved questions without new evidence. At that checkpoint, runtime removed the terminal LLM call and used a deterministic closure; v25 later proved that changing `decision` during that closure was itself semantically invalid and superseded it with exact guard-stop preservation.

| Area | Spec | Code | Status | Notes |
| --- | --- | --- | --- | --- |
| Meta mechanism | [`AGENTS.md`](../AGENTS.md), [`spec/README.md`](../spec/README.md) | [`scripts/lint_repo.sh`](../scripts/lint_repo.sh), [`.githooks/pre-push`](../.githooks/pre-push) | Done | Spec-first work, progress/memory hygiene, repository lint, and Git checkpoint rules are active. |
| Vision | [`spec/vision.md`](../spec/vision.md) | None | Spec Done | Defines a thesis-centered stock research system, not an order or portfolio engine; historical learning now has coupled Plan and Signal evolution time scales. |
| Architecture | [`spec/architecture.md`](../spec/architecture.md) | None | Spec Done | Defines the operating spine, module boundaries, point-in-time discipline, fixed Anchor plus three issuer-owned dataset roles, Fast Plan / Slow Signal loop, and immutable cross-workspace historical Plan warm starts. |
| Spec module map | [`spec/src/stock_opportunity_agent/README.md`](../spec/src/stock_opportunity_agent/README.md) | None | Spec Done | Active spec tree includes Raw Info, reusable LLM Agent harness, Signal Library, and the replacement evolution runtime. |
| Models | [`spec/src/stock_opportunity_agent/models.md`](../spec/src/stock_opportunity_agent/models.md) | [`src/stock_opportunity_agent/models.py`](../src/stock_opportunity_agent/models.py), [`tests/test_models.py`](../tests/test_models.py) | Started | Core serializable thesis, score, decision, evidence, review, experiment, and version records are implemented. |
| Config | [`spec/src/stock_opportunity_agent/config.md`](../spec/src/stock_opportunity_agent/config.md) | [`src/stock_opportunity_agent/config.py`](../src/stock_opportunity_agent/config.py), [`tests/test_config.py`](../tests/test_config.py) | Started | Validated defaults, JSON loading, environment overrides, and secret-safe public serialization are implemented. |
| Data | [`spec/src/stock_opportunity_agent/data.md`](../spec/src/stock_opportunity_agent/data.md), [`spec/src/stock_opportunity_agent/data/raw_info.md`](../spec/src/stock_opportunity_agent/data/raw_info.md), [`spec/src/stock_opportunity_agent/data/resolution.md`](../spec/src/stock_opportunity_agent/data/resolution.md), [`spec/src/stock_opportunity_agent/data/backfill.md`](../spec/src/stock_opportunity_agent/data/backfill.md), [`spec/src/stock_opportunity_agent/data/historical_news.md`](../spec/src/stock_opportunity_agent/data/historical_news.md) | [`src/stock_opportunity_agent/data/`](../src/stock_opportunity_agent/data/), [`scripts/backfill_historical_data.py`](../scripts/backfill_historical_data.py), [`tests/test_data.py`](../tests/test_data.py), [`tests/test_data_resolution.py`](../tests/test_data_resolution.py), [`tests/test_data_backfill.py`](../tests/test_data_backfill.py), [`tests/test_historical_news.py`](../tests/test_historical_news.py), [`tests/test_scheme_core.py`](../tests/test_scheme_core.py), [`tests/test_evolution_control.py`](../tests/test_evolution_control.py) | Started | Raw Info is an explicitly identified global append-only oracle outside evolution workspaces. One local-first `EvidenceResolver` serves Basic Info and Signals with deterministic exact spans, complete document/hash lineage, durable acquisition limits, independently authorized adapters, structured DataGaps, and a derived capability backlog. Company-scoped news now requires a strong issuer name or boundary-matched ticker in visible title/body text; provider association metadata alone is filtered with durable events while complete Raw Info remains unchanged. Structured market context is selected on complete non-overlapping JSON-row offsets before model metadata normalization. New broad-research contracts use wildcard provider/capability/source-type authorization for every historical adapter registered by the frozen code revision, so future Signal types are not blocked by today's allowlist; absent adapters and genuine provider/history gaps remain fail-closed. Semantic source aliases route stable Signals to SEC facts, core-form filing bodies, Alpha Vantage news and point-in-time transcripts, and historical prices. Compatible acquisition failures are reused, provider fallback remains catalog ordered, and transcript availability is anchored to the provider-reported earnings date rather than the current retrieval time. Price documents retain adjusted-close series for deterministic market Signals. The local oracle contains 3,757 documents; all 24 exact round-1 cases have point-in-time company news, while one provider response remains explicitly saturated at 1,000 rows. Current-only profile endpoints still fail closed. |
| LLM capability | [`spec/src/stock_opportunity_agent/llm.md`](../spec/src/stock_opportunity_agent/llm.md) | [`src/stock_opportunity_agent/llm/`](../src/stock_opportunity_agent/llm/), [`tests/test_llm_model_registry.py`](../tests/test_llm_model_registry.py), [`tests/test_scheme_core.py`](../tests/test_scheme_core.py) | Started | Provider catalog and generic harness remain reusable, but neither active Signal evolution track is a free-form tool loop. Signal Mining uses four narrow structured roles (`H1/H3` and `E1/E2`) plus a deterministic local H2 shortlist. Signal Update has one narrow `no_change/defer/update` role after local target and issuer-disjoint induction/holdout selection; no actionable target or insufficient local evidence makes zero Update-model calls. Structured production roles persist exact valid responses and failure-only malformed text, usage, and hashes. V59 live-verified one-call H1, zero-call H2, and the two-stage strong-query boundary: full-document near-matches advanced, but insufficient exact excerpts still prevented H3. Bootstrap is single-cycle, so Update and E1/E2 now require an ordinary Fast-derived run. |
| Memory | [`spec/src/stock_opportunity_agent/memory.md`](../spec/src/stock_opportunity_agent/memory.md) | [`src/stock_opportunity_agent/memory/`](../src/stock_opportunity_agent/memory/) | Started | File-backed signal/theme/playbook memory exists; broader company/thesis/review memory remains incremental. |
| Themes | [`spec/src/stock_opportunity_agent/themes.md`](../spec/src/stock_opportunity_agent/themes.md) | [`src/stock_opportunity_agent/themes.py`](../src/stock_opportunity_agent/themes.py) | Started | Cold-start industry-chain theme maps are implemented; live theme discovery remains spec-only. |
| Cases | [`spec/src/stock_opportunity_agent/cases.md`](../spec/src/stock_opportunity_agent/cases.md), [`spec/src/stock_opportunity_agent/cases/packets.md`](../spec/src/stock_opportunity_agent/cases/packets.md) | [`src/stock_opportunity_agent/cases/`](../src/stock_opportunity_agent/cases/) | Started | Outcome definitions, inflection candidates, control matching, and packet construction are implemented. The approved v13 manifest uses five mature 2025 dates, keeps every issuer identity with at least one case passing the point-in-time normal-stock gate, and freezes a separate 16-case Anchor. It contains 3,511 issuers/14,575 cases: Anchor 16/16, Discovery 2,096/8,755, Evolution Validation 875/3,623, and Locked Test 524/2,181. Security identity is common-stock/active/CIK/exchange/listing-date/SPAC filtered; each case additionally requires at least $1m pre-date average dollar volume and a clean adjusted-price window. The user reviewed the exact identity-decision and Anchor hashes before approval; Locked Test remains sealed. |
| Packet signals | [`spec/src/stock_opportunity_agent/signals.md`](../spec/src/stock_opportunity_agent/signals.md) | [`src/stock_opportunity_agent/signals.py`](../src/stock_opportunity_agent/signals.py) | Started | Existing deterministic `ResearchPacket` measurements remain isolated from the new adaptive Signal Registry. |
| Signal Library | [`spec/src/stock_opportunity_agent/signal_library.md`](../spec/src/stock_opportunity_agent/signal_library.md) | [`src/stock_opportunity_agent/signal_library.py`](../src/stock_opportunity_agent/signal_library.py), [`configs/signals_v1.json`](../configs/signals_v1.json), [`tests/test_scheme_core.py`](../tests/test_scheme_core.py), [`tests/test_signal_financials.py`](../tests/test_signal_financials.py) | Started | The enabled-only Registry exposes 14 source-backed seed Signals; `market_cap` and `pilot_to_volume` remain disabled. `SignalExecutor.prepare_inputs` drives both complete-Registry readiness and execution. Adaptive case retrieval omits executed refs before one compact-card selection call, normalizes local formatting, caps each batch at four Signals and two LLM Signals, and retains executor fingerprint no-op as a second guard. Complete Raw Info stays local for fingerprints and final evidence validation; at most two soft Signals share one deduplicated deterministic source projection of 32,000 characters, model citations map uniquely back to original Raw Info spans, and per-Signal parse/validation/unavailable fallback remains independent. `unavailable` rejects supporting or counter-evidence at the value-object/parser boundary. Mining induction issuers remain excluded from paired effectiveness; insufficient independent coverage stays durable `provisional`. New and updated candidates must both have more directionally correct than wrong decisive holdout results before relative improvement can promote them. |
| Scanner | [`spec/src/stock_opportunity_agent/scanner.md`](../spec/src/stock_opportunity_agent/scanner.md) | None | Spec Done | Defines non-LLM universe filtering and current-state-aware candidate generation. |
| Research / LLM | [`spec/src/stock_opportunity_agent/research.md`](../spec/src/stock_opportunity_agent/research.md) | [`src/stock_opportunity_agent/research/`](../src/stock_opportunity_agent/research/), [`tests/test_cold_start.py`](../tests/test_cold_start.py) | Started | Formal cold start and Ralph source/acquisition diagnostics remain; the older broad information-plan experiment is explicitly not a second active evolution engine. |
| Information-plan and Signal evolution | [`spec/src/stock_opportunity_agent/research/scheme_evolution.md`](../spec/src/stock_opportunity_agent/research/scheme_evolution.md), [`spec/src/stock_opportunity_agent/research/evolution_runtime.md`](../spec/src/stock_opportunity_agent/research/evolution_runtime.md), [`spec/src/stock_opportunity_agent/research/evolution_dashboard.md`](../spec/src/stock_opportunity_agent/research/evolution_dashboard.md), [`progress/self-evolution-audit-2026-08-14.md`](self-evolution-audit-2026-08-14.md), [`progress/self-evolution-audit-2026-08-22.md`](self-evolution-audit-2026-08-22.md), [`progress/self-evolution-live-validation-audit-2026-08-23.md`](self-evolution-live-validation-audit-2026-08-23.md) | [`src/stock_opportunity_agent/research/scheme_evolution.py`](../src/stock_opportunity_agent/research/scheme_evolution.py), [`src/stock_opportunity_agent/research/evolution_runtime.py`](../src/stock_opportunity_agent/research/evolution_runtime.py), [`src/stock_opportunity_agent/research/evolution_dashboard.py`](../src/stock_opportunity_agent/research/evolution_dashboard.py), [`scripts/evolve_information_schemes.py`](../scripts/evolve_information_schemes.py), [`scripts/run_information_plan_evolution.sh`](../scripts/run_information_plan_evolution.sh), [`tests/test_data_resolution.py`](../tests/test_data_resolution.py), [`tests/test_scheme_core.py`](../tests/test_scheme_core.py), [`tests/test_evolution_control.py`](../tests/test_evolution_control.py) | v7 Ordinary MVP Verification | V44 completed a real Slow cycle but remains rejected evidence: E2 made an unsupplied sector claim and the gate promoted an all-wrong max-drawdown update. The generalized E2 correction and absolute update-quality floor pass all 713 tests and lint. Clean V45 is frozen from Registry v1 at contract `8d44c95a...06f33`, zero calls, `round=0/cycle=0`, and exact H1 request `fe5c230e...a56e`. Its 244,452-byte wire body is byte/hash/message identical to the persisted request, contains all 175 obligations, 30 reflection actions, 24 meta cases, and 14 stable cards, has no checked identity/path leak, and keeps Locked Test sealed. Its own payload-specific DeepSeek authorization is the remaining execution boundary. |
| Scoring | [`spec/src/stock_opportunity_agent/scoring.md`](../spec/src/stock_opportunity_agent/scoring.md) | None | Spec Done | Defines theme, segment, company, risk, and final opportunity scores. |
| Ranking | [`spec/src/stock_opportunity_agent/ranking.md`](../spec/src/stock_opportunity_agent/ranking.md) | None | Spec Done | Defines segment and cross-market watchlist ranking. |
| Monitoring | [`spec/src/stock_opportunity_agent/monitoring.md`](../spec/src/stock_opportunity_agent/monitoring.md) | None | Spec Done | Defines catalyst monitoring, validation-contract checks, and research-state transitions. |
| Review | [`spec/src/stock_opportunity_agent/review.md`](../spec/src/stock_opportunity_agent/review.md) | None | Spec Done | Defines outcome review, earnings validation, error labeling, and signal attribution. |
| Meta-learning | [`spec/src/stock_opportunity_agent/meta_learning.md`](../spec/src/stock_opportunity_agent/meta_learning.md) | FIFO Plan meta implemented in evolution runtime | Started | Round meta is grounded in new experiments and fixed at 10 entries by default. Durable entries preserve complete original, vertical, and horizontal layers; the model-facing view is deterministic, aggregate-complete, recency-weighted, capped at 48,000 characters, and selects the richest available original reflection per assessment rather than hiding later root causes behind an early blank sample. A horizontal role call now requires at least two new Plan records. Append and whole-entry FIFO eviction remain the only window mutations. Broader system-level version governance remains spec-only. |
| Reports | [`spec/src/stock_opportunity_agent/reports.md`](../spec/src/stock_opportunity_agent/reports.md) | None | Spec Done | Defines watchlists, cards, reviews, and audit bundles. |
| Orchestration | [`spec/src/stock_opportunity_agent/orchestration.md`](../spec/src/stock_opportunity_agent/orchestration.md) | [`src/stock_opportunity_agent/orchestration.py`](../src/stock_opportunity_agent/orchestration.py), [`scripts/run_cold_start_formal.py`](../scripts/run_cold_start_formal.py), [`scripts/evolve_information_schemes.py`](../scripts/evolve_information_schemes.py), [`scripts/run_information_plan_evolution.sh`](../scripts/run_information_plan_evolution.sh) | Started | Evolution CLI supports local preflight, label-free Raw Info migration, exact dataset approval, v6 freeze, bounded `run-cycle`, continuous `run-loop`, and pointer-driven Ctrl+C resume. The manual `approve-signals` path is removed; exact validated candidates auto-promote inside the recoverable cycle transition. `new --data-external` freezes the wildcard broad-research profile with `1000/10000` request ceilings and remains zero-network; resume repeats the data flag, while LLM execution retains its separate exact-hash acknowledgement. Locked Test and unvalidated Signal mutation remain fail-closed. |

Current Signal remediation handoff: [`signal-remediation-verification-2026-08-21.md`](signal-remediation-verification-2026-08-21.md) records the three-layer Raw Info, then-active Agent-contract, and paired-promotion repair. A real isolated AMD historical run and a later wildcard-resolver replay both resolved all 14 stable Signal inputs and produced 13 evidence-backed values or semantic judgments; the only unavailable result was a legitimate absence-of-action finding. Those historical live Mining/Update invocations predate the current locally orchestrated Update pipeline. Existing frozen workspaces are not widened; a fresh contract gets unrestricted registered-adapter Raw Info authorization from the single `new --data-external` flag.

Latest Signal Mining redesign: the active Mining path is a local dual-track controller rather than the earlier Generic-Agent tool loop. Hypothesis cycles perform one H1 portfolio call, one label/identity-hidden H2 ranking call for all hypotheses, local positive/control feasibility with independent case reservation, then one H3 evidence contrast for at most two hypotheses. Every third cycle runs label-hidden E1 extraction followed by label-revealed E2 discovery. Company briefs use bounded point-in-time profile fields and Raw Info coverage, models can rank only opaque allowed case refs, and induction/effectiveness issuers cannot overlap. Outcomes distinguish promoted, provisional, rejected, and refined work without weakening stable promotion. The final scoped DeepSeek verification completed H1/H2/H3 in three calls for `$0.003969`; two unsupported comparisons became durable refined hypotheses, no candidate was fabricated, H2 contained neither identity nor outcome, H3 disclosed labels only after local selection, and Locked Test remained sealed. The local probe inventory contained only two eligible issuers and unavailable profile descriptions, so it validates control flow and privacy but not broad-universe mining yield.

Latest Signal Update redesign: every Fast selection persists a bounded reason/applicability decision, and every committed result becomes an append-only event under its exact Signal version. Full events retain Plan/case lineage locally; the selector sees only a compact identity-free profile with the complete state/outcome matrix, distinct-observation attribution, and recurring multi-issuer context tags. Effectiveness deduplicates the same case/ref/input across Plans while their distinct selection reasons remain auditable. A Fast group's learned profiles freeze at its starting committed-round cutoff, including after restart. Slow Update locally ranks up to three repeated exact-version issues, suppresses unchanged retries per target, executes each `vCurrent` over the same deterministic issuer-distinct Discovery sample, reserves a separate hidden holdout before each invocation, and makes at most one bounded semantic `no_change/defer/update` role call per locally prepared target. Per-target failures and recovery fingerprints are isolated inside one portfolio audit; no actionable target still means zero Update calls. `vNext` preserves static identity/semantics and remains isolated until existing contract, fixture, and paired holdout gates pass. The former active Update Generic-Agent tools and workflow adapter are removed.

Post-live Signal Mining persistence hardening: feasible H1 reserve hypotheses beyond the two-hypothesis H3 contrast budget are recorded as explicitly deferred refined work, so they remain visible to the next cycle instead of existing only in the audit trail.

Latest Signal routing remediation: the paid `deepseek-v4-flash-production-20260822-015342` audit showed that two-stage category/card routing consumed 329 of 800 external attempts and 395 already executed refs were selected before the executor skipped them. Production retrieval now exposes only unexecuted compact cards in one call, treats an exact empty array as valid no-match, fails closed with cumulative usage when malformed output remains invalid after correction, and appends no empty Signal batch. Point-in-time resolution, deterministic execution, soft-Signal evidence validation/correction, exact response caching, Mining/Update workflow validation, paired candidate testing, atomic promotion, and next-cycle Registry visibility remain covered.

Latest proposal remediation: `deepseek-v4-flash-signal-context-window-20260822-v3` proved that the provider could return a schema-valid but exact historical-parent copy for all three outer proposal attempts because the engine-level duplicate rejection was not fed back into the proposer. Exact-parent equality is now validated inside the proposer's one-correction loop, every request explicitly forbids parent copying, and proposal attempts carry deterministic change focuses for `B/H_init`, `H_reflect`, then `H_analyse`. The v3 workspace remains immutable fault evidence at round/cycle `0/0`.

Latest end-to-end Signal verification: contract-bound workspace `deepseek-v4-flash-signal-context-window-20260822-v4` committed Fast round 1 and Slow cycle 1 over 24 cases with Combined Binary F1 `0.583333` (`TP=7/FP=3/TN=7/FN=7`), 301 completed external attempts, `$0.525076` actual cost, and Locked Test sealed. All 48 readiness checks were `14/14`; the runtime made 289 resolved Signal-input resolutions, executed 159 changed fingerprints, and skipped 130 unchanged fingerprints. Of 159 persisted results, 94 were non-unavailable and every one retained only literal, point-in-time, fingerprint-bound evidence. The audit also found one pre-fix `customer_concentration` result that was `unavailable` yet carried eight irrelevant citations, six nonliteral; the value validator's unavailable early return had bypassed evidence checks. The current code rejects that exact artifact, supplies indexed correction feedback, and passes its exact failure replay, but v4 remains immutable pre-fix evidence and a fresh contract is required for post-fix external revalidation. Its committed meta entry contains all 24 original case reflections, one vertical Plan reflection, the horizontal error/Signal/search synthesis, and is included byte-for-byte in both Slow-agent initial workspaces. Historical seed F1 `0.727273` is retained only as context because its snapshot differs; `same_evaluation_snapshot=false` and `metric_delta=null` correctly prevent a causal regression claim.

Verification baseline: 331 repository tests pass with the bundled Python 3.12 runtime; repository lint is rerun at every change checkpoint. Coverage includes selector failure/no-match separation, Predictor prompt/schema agreement, canonical provider wire-body persistence/transport, both Signal Mining tracks, literal H1/H2/H3/E1/E2 role contracts, label/identity-hidden case ranking, local positive/control overlay, frozen signatures before label reveal, induction/effectiveness issuer separation, durable provisional classification, reasoned single-call eligible-card Signal routing, valid empty no-match without correction, pre-selection exclusion of executed refs, version-bound append-only learning, cross-Plan observation deduplication, identity-free learned cards, cycle-start learning cutoffs, zero-call Update skipping, Top-3 Update ranking/call bounds, per-target failure isolation, v1/v2 Update-audit recovery, one-call-per-target induction, local holdout isolation/promotion, integrated Raw Info -> soft Signal -> literal evidence -> reflection, unavailable/evidence coherence with indexed Signal correction feedback, exact-parent proposal correction with attempt-specific change focus, bounded exact-window LLM Signal context with full-document evidence validation, wildcard registered-adapter authorization and one-flag broad-profile freezing, complete-Registry readiness, semantic source aliases, compatible acquisition-failure reuse, core SEC filing fallback, fiscal-quarter transcript mapping and point-in-time filtering, paired Signal effectiveness promotion, unique case-only literal-span canonicalization, ordered provider fallback, readiness-based Random replacement before snapshot finalization, immutable Anchor failure, shared-data non-rejection both before and after candidate evaluation, retryable shared-data exit 75, four-way Predictor parsing and deterministic binary mapping, durable judgment/binary consistency, all eight label-revealed feedback cases, feedback-artifact validation, additive original/vertical/horizontal reflection persistence and legacy restoration, whole-entry FIFO eviction, outcome-aware but identity/context-free proposer handoff, explicit case-reflection and compact Plan-critic consumption, compact trajectory-free round reflection, anonymous parent-to-child structural comparisons, exact-snapshot-only metric deltas, ten-hour bounded process-level recovery after repeated temporary exit-75 failures, immediate propagation of deterministic failures and `Ctrl+C`, rejection/correction of the superseded binary role shape, absence of any active binary token-score call, compact Plan-critic trajectories that omit Raw Info/context/identity fields, unchanged Binary F1 selection, canonical Signal and CIK acquisition routing, paid malformed-JSON audit/cost/correction, proposal-level compact market-backbone correction, price metadata, catalog-ordered price providers, invocation-disabled frozen data policies, the normal-stock and per-case price/liquidity gates, fixed Anchor persistence, exact `16+8` sampling, union-confusion Combined F1, rare-class Validation diversity, restart conflict rejection, fitness gates, checkpoint cross-link recovery, staged Slow-validation and partial-Registry-transition recovery, cross-cycle promoted-Signal visibility, no historical Plan reevaluation, cumulative F1 parent selection, committed-only historical seed discovery, source-family and semantic diversity, immutable seed-manifest recovery and tamper rejection, first-run empty-pool fallback, current Top-K precedence over warm starts, current-target identity expansion, legitimate third-party evidence retention, global oracle identity, explicit data authorization, point-in-time evidence, existing expansion/backfill paths, and zero-network v5 launcher boundaries.

Current evolution handoff: `deepseek-v4-flash-information-resolution-v1` and all earlier execution workspaces are retained as immutable history. Their v1-v4 contracts cannot execute under the v5 runtime, and no cache, trajectory, metric, archive record, or completion pointer is migrated into a new workspace. V2-v10 record the resolved anonymity, CIK routing, malformed JSON, and Predictor-boundary faults described in the changelog. V11 was the first run to commit a healthy nonzero Fast round: its best round-1 Plan reached Combined Binary F1 `0.695652`; round 2 then rejected all candidates because Alpha Vantage's 25/day news quota left 6-7 rotating cases without any source evidence, even though two complete candidates had nonzero diagnostic F1 (`0.133333` and `0.25`). V11 must not resume after the market-backbone correction, but its exact committed best Plan is eligible as content-addressed parent context in a new contract-bound Seed Pool; its old F1 remains provenance only and is never imported into the new Top-K. The old 53-case approved manifest has no Anchor and remains infeasible. Approved v13's Evolution Validation pool contains 3,623 cases across 875 issuers with `3,387/171/62/3` case counts for `non_surge/2_3x/3_10x/10x_plus`; the 10x+ cases span AXTI and HYMC, so exact round sampling rotates across two issuer identities. The fixed Anchor contains seven matched controls plus CIEN, FTAI, ATI, NEM, MP, SNDK, MU, PRAX, and ONDS. The exact round-1 snapshot is `63d1c0769e976aec421b6d393c4b67c9d7b26f7552bce069bb6d9d6a07dfaef8`, and every one of its 24 cases now has point-in-time news in the global oracle. The historical `v13-next-token-v5` run completed all 48 binary-threshold candidate-case trajectories but produced `TN=10/FN=14/TP=0/FP=0`; it remains uncommitted at round/cycle 0 and therefore cannot seed any new run. Its Plan-critic overflow remains useful fault evidence: compact critic input keeps the diagnostic outcome/reflection/Signal information while excluding repeated Raw Info.

Latest paid verification: `deepseek-v4-flash-fourway-20260816-230058` recovered the observed SSL EOF under its exact cached contract and completed the first 24-case candidate with `TP=5/FP=1/TN=9/FN=9`, Combined Binary F1 `0.500`, precision `0.833`, and recall `0.357`. All 24 trajectories persisted the original four-way judgment and deterministic feedback; the user then requested a safe interrupt during candidate 2, leaving round/cycle pointers at zero. That revision remains fault/metric evidence but cannot use the new built-in supervisor after the next code commit.

Current gate: the user resolved the Predictor design tension by restoring the four-way opportunity boundary, and the exact v13 proposal, identity decisions, and Anchor remain human-approved. Because run contracts bind the exact code revision, built-in ten-hour recovery must start in a fresh workspace; that workspace now automatically freezes the best compatible committed historical parent seeds and validly falls back to the manual Plan when none exist. Earlier workspaces remain immutable evidence. Before enabling SEC acquisition, the operator must set `SOA_SEC_USER_AGENT` to a real application/contact identity; it cannot be inferred or fabricated. Massive/Stooq point-in-time market data remain authorized without SEC. Locked Test remains sealed.

Latest parent-reflection verification: `deepseek-v4-flash-parent-reflection-verification-20260817-v1` completed and committed one full Fast/Slow cycle after automatically recovering four DeepSeek SSL EOFs. Its 24-case child reached `TP=4/FP=1/TN=9/FN=10`, Combined Binary F1 `0.421053`, precision `0.800`, and recall `0.285714`. On the exact shared snapshot, reflection received the v11 parent F1 `0.695652`, child-minus-parent F1 `-0.274600`, `TP -4/FN +4`, removal of annual-filing and SEC-facts requests, and addition of the market backbone. Plan critic explicitly identified missing fundamental data as a false-negative pattern; compact round reflection completed with 5,152 input tokens and no trajectories or case ids. Round 1 and cycle 1 are committed, no Signal passed Slow validation, and Locked Test remains sealed.

Latest dual-loop handoff (2026-09-19): v8 contracts can now freeze dual-loop continuation — an explicit `--cycle-mode fast_then_slow` with `--slow-history-from` imports the committed source history (namespaces, exact Registry, provisional residents, pooled evaluation) while keeping positive Fast-round targets (commit d002c2b; 852 tests and lint pass). V116, the frozen slow_only successor of V115 (2000 attempts/$16/8 cycles), was verification-launched once ($0.201, 9 attempts, 0 cycles committed) and stays unused and resumable. V117 (`9f2eeebc…`, initial Registry v6 from V115's chain) then executed the first live v8 Fast loop: two candidates produced full 24-case research trajectories (262 attempts, $0.790, zero transport/parse errors, one auto-resumed SSL EOF) before both were rejected by one structural defect — an H_reflect correction round reverts a previously-compliant `next_information_needs` item because later correction feedback names only the newest defects and the whole-state rewrite silently undoes the earlier temporal-boundary fix; full re-validation then fails closed with corrections exhausted. The exact three-attempt evidence chain, the guard-function replay proving the corrected phrasing passes, and a byte-preservation fix proposal (H1's item-local rule extended to H_reflect ResearchState) are recorded in `reports/fast-round-correction-regression-20260919.md`. Per the user's instruction the run was terminated early on this finding; V117 is immutable diagnostic evidence at pointers 0/0, Locked Test stays sealed, and the next step is the H_reflect correction-preservation fix followed by a successor freeze.

Round20 locally accepted: as-of-bounded future schedule nouns now accept explicit singular/plural variants; future actual/unbounded source requests still reject.922tests/lint and original MPMaterials production-controller replay pass. V122 completed11cases before intentional correctness stop; V123 realjointacceptance pending.

Magnitude dual-objective evolution implemented (2026-09-20, plan `reports/fast-slow-magnitude-evolution-action-plan-20260920.md` with same-day review revisions): user-approved conservative dual-objective selection is now spec'd top-down (vision/architecture/scheme_evolution/evolution_runtime/evolution_signal_roles — Binary F1 primary compared as exact rationals of confusion counts, magnitude macro-F1 secondary only at exact F1 ties, stable plan id last; legacy records without the secondary never zero-fill). Code adds deterministic per-case `magnitude_feedback` sibling blocks (never extending `candidate_judgment_feedback`) and plan-level `magnitude_diagnostics` persisted additively in meta; post-hoc/Plan-critic/round-reflector/proposer prompts and payloads separate direction vs class errors while `prediction_outcome.correct` keeps its conflated copy semantics; parent comparisons carry same-snapshot `magnitude_metric_delta`; ranked entry points (archive parents, seed main + second-seat keys, dashboard) apply the dual ordering while F1 quality gates, benefit arms, and Signal promotion keep current semantics (inventory in `reports/fast-slow-magnitude-implementation-20260920.md`). 983 tests/lint pass; V130 artifacts replay identically under new code with legacy meta loading unchanged. Not done: P5 slow-side code, P6 live fault-injection matrix, P7 real-run experiments (need separate authorization); V130 stays paused (resume requires checkout of af5966b); cache-replay dead-end and SIGINT-swallow defects remain open.

P5 phase 1 implemented (2026-09-20, same action plan): magnitude learning tasks now flow into the existing Slow source view — `_committed_slow_feedback` projects one `magnitude_feedback` feedback unit per locally committed Plan whose meta reflection carries `magnitude_diagnostics` (stable `magnitude:<plan_id>` ref, all Slow source roles, diagnostic-only limitation; legacy Plans without diagnostics yield no row, imported reserved-negative rounds excluded; spec updated in signal_evolution.md). H1 dispositions follow the existing fast_plan_action/Mining routing unchanged, and every committed `slow_loop_result.json` now carries an explicit `magnitude_contribution` block that is `assessed: false` under the first-version directional gates. 9 new tests (slow wiring), 992 total + lint pass; V130 legacy meta yields zero magnitude rows read-only. P5 phase 2 (controlled plan-consumption experiment) and P6 live fault-injection remain; P7 still needs separate authorization.

P6 offline fault-injection matrix complete (2026-09-20): tests/test_p6_fault_injection_matrix.py drives real PlanEvolutionEngine/SignalEvolutionEngine/predictor adapters with scripted LLM roles through all 12 action-plan P6 scenarios — label-reveal ordering, single-valid-candidate round without Round LLM, cross-snapshot parent comparisons yielding no paired deltas, imported negative prefix plus three local commit-restart rounds, post-commit crash with idempotent stats/learning replay on engine reconstruction, slow staged-validation crash with single-recovery and exactly one magnitude feedback row, post-promotion pre-cycle-commit interrupted state recovered via the control-layer stage_slow_result+complete_cycle sequence (idempotent rerun, no second promotion), malformed-reflection bounded correction plus fail-closed magnitude-block tampering, legacy missing magnitude never zero-filled in ranking, reflection transport failure kept as explicit failure (never fake content), empty-mining no-op cycle committing with honest magnitude_contribution:false, and promotion visible in the next Fast round's actual registry refs with prior record.json byte-identical. 14 tests green; full suite 1006 passed + lint PASS. Remaining: P5 phase-2 two-arm observation experiment and P7 live runs (separate authorization); two known defects (third cache-replay dead-end, SIGINT mid-call swallow) still open.

C0-C2 partial (2026-09-21, signal-magnitude + fast-parallel plan 18b2260): C0 recorded data gate and shared-state baselines (reports/signal-magnitude-c0-baseline-20260921.md + JSON) — ge3 raw data viable (102/270 and 44/109 distinct issuers per group; cross-split issuer overlap 0) but gate UNCONFIRMED pending user thresholds; ge10/extremes permanently blocked (2-3 cases / 2 issuers); signal_library named mandatory multi-target interface surface; V130 real-run timing table (759 attempts p50 4.6s/p90 11.2s, case p50 139s; c01→c02 strictly serial with warm-cache reuse). C1 specs updated (transport same-request guard + concurrency boundary; plan_evolution bounded parallel evaluation; gated magnitude-target sections in signal_evolution/signal_library). C2: defect #11 closed with chain-scoped same-request guard (thread-local chains, fires before cache lookup, 8 tests incl. three request-identity semantics and no cross-thread leak; commit 11cbca2); B2 primitives landed — AttemptLedger FIFO ticket admission + RLock read-modify-write, InFlightRequestCoordinator leader/waiter sharing with shared-cache zero-usage waiters and bounded waits, path-keyed append locks for data_requests.jsonl and data_acquisition_requests.jsonl with counter integrity (6 tests; 1020 total + lint pass). Remaining: B1 parallel evaluate path at concurrency 1 (evaluator factory + coordinator), C3 (#12 SIGINT fix + stop semantics + single-writer events), C4 concurrency-2 offline equivalence, C5-C7 ge3 implementation (blocked on user-confirmed gate thresholds), C8 integration; live runs need separate authorization.

B1+C3 complete (2026-09-21, same plan): PlanEvolutionEngine now supports bounded parallel candidate evaluation — evaluator_factory builds per-worker mutable role instances, the coordinator holds the workspace lock and dispatches in ascending candidate-slot order with start events emitted upfront, workers keep case order and per-plan staging, results recombine in slot order, and commit stays single-writer on the coordinator thread (sequential path byte-unchanged; commit 9286e7d). Concurrency-1 and concurrency-2 byte-equivalence vs the sequential engine verified over plans/*/record.json and meta/round-0001.json; parallel>1 without a factory fails closed. Defect #12 closed at engine level (commit a2e9420): install_stop_handler turns SIGINT into a cancel flag on the coordinator main thread (workers never install handlers), admission checks stop before every candidate in both paths, in-flight work finishes before the stop, and worker waits are bounded (worker_wait_timeout_seconds) with staged attempts preserved on timeout. 9 new tests across equivalence/cancel/SIGINT restore/bounded wait; 1029 total + lint PASS. Remaining: C4 concurrency-2 fault-replay extension and event single-writer hardening; C5-C7 ge3 implementation still blocked on user-confirmed gate thresholds; C8 integration; live throughput experiments need separate authorization.

C4 complete (2026-09-21): the P6-style fault-injection matrix now covers the parallel evaluate path at concurrency 2 — reverse completion order (slow slot 1 / fast slot 2) keeps slot-ordered artifacts byte-equal to the sequential engine, started/scored events emitted in slot order, and every engine event is emitted from the coordinator MainThread (single-writer); a worker exception mid-round crashes without false commits, preserves the sibling's staged attempt, and a rebuilt engine recovers to exactly one commit with unique learning events; a crash at the commit barrier (after all evaluations) recovers with a single commit, one meta entry, two archive records, and no duplicated learning events; an in-flight stop at concurrency 2 leaves staged work and a clean pointer. 4 new tests (tests/test_c4_parallel_fault_injection.py); 1033 total + lint PASS, all offline. B workflow (C0-C4) is now offline-complete; remaining: live throughput experiment (separate authorization), C5-C7 ge3 implementation blocked on user-confirmed gate thresholds, C8 integration.

ge3 data gate confirmed (2026-09-21): user approved the recommended minimum-support thresholds (>=30 distinct issuers per dataset per group, >=3 distinct month clusters, existing issuer-disjoint dev/check mechanism, full-pool PIT evidence-coverage audit >=90% with failures counted as a C5 pre-mining entry condition). The C0 gate record now reads CONFIRMED: issuer (102/270 discovery, 44/109 validation) and month-cluster criteria pass; magnitude_ge3-specific implementation (C5-C7) is unlocked; ge10/extremes remain blocked. B workflow C0-C4 offline-complete; C5 begins with the target contract spec and the pre-mining PIT coverage audit.

C5 PIT coverage audit executed, ge3 re-blocked (2026-09-21): the user-confirmed pre-mining entry condition (full-pool per-case PIT evidence coverage >=90%) was audited against the global oracle (11,402 docs / 1,325 companies; per-document available_at vs case prediction_time, failures counted). RESULT: FAIL — discovery 49.32% (4,437 failures), evolution validation 4.86% (3,447 failures); independent company-directory recount confirms. Cause is materialization scope, not data error: the oracle only holds issuers past runs touched; the earlier 24-case "all PIT news" finding was snapshot-level and does not extrapolate. Per the hard gate, all ge3-specific schema/projection/mining/promotion implementation stays blocked (insufficient_pit_coverage); the frozen target-contract design is recorded in signal_evolution.md for use after the gate passes. Unblock paths pending user choice: (a) authorized provider backfill then re-audit, (b) re-confirmed population restriction, (c) remain blocked and proceed with target-independent work. Audit artifacts: reports/signal-magnitude-c5-pit-coverage-audit-20260921.{md,json}; 1033 tests + lint PASS unchanged.

ge3 unlock path chosen (2026-09-21, user decision a-prime after clarification): the PIT coverage gate is re-scoped from full pool to the ge3 research population (true >=2x cases) — discovery already passes under that scope (99.4%/97.3% per group), validation fails (53.8%/29.2%) — and a one-time pre-prediction evidence backfill is authorized in principle: frozen manifest reports/signal-magnitude-c5-backfill-manifest-20260921.json (179 cases / 115 issuers; SEC free sources first, AV news quota-batched at 25/day; proposed caps 500 attempts / $5). Execution follows the existing backfill_historical_data preview->plan->run pipeline (preview offline first), then the audit re-runs under the research-population scope; ge3 implementation unlocks only after that audit passes. Path b was ruled infeasible (covered validation subset high group = 21 issuers < confirmed 30 threshold).

ge3 PIT gate PASSED, C5 unlocked (2026-09-21): backfill pipeline executed per user-approved path a-prime — scoped label-free acquisition scope (115 issuers / 5 dates, reports/signal-magnitude-c5-backfill-scope-20260921.json), offline exact plan (115 requests, hash e8f86b50), then authorized external run: SEC company facts 115/115 network requests succeeded, 321,639 fact rows materialized into the global oracle (2 zero-fact issuers), 0 pending, cost $0 — 115 of the 500-call / $5 authorized budget consumed. Re-audit under the user-confirmed ge3 research-population scope: discovery ge3 high/low 100%/100%, validation 93.85%/98.83%, all groups >= the 90% floor (reports/signal-magnitude-c5-pit-reaudit-20260921.json). Every ge3 gate criterion now passes (issuers, month clusters, isolation, confirmed thresholds, PIT coverage) — ge3-specific implementation (C5 mining-chain target projection + signal_library multi-target statistics) is unblocked and begins next; ge10/extremes remain blocked.

C5 ge3 target implementation landed (2026-09-21): research_targets.py owns the frozen ge3 contract (magnitude_ge3_v1, identity-hash over id/population/rules/version/protocol), realized-label projection (>=3x high / [2,3) low / <2x excluded, FN included via true-label population), hash-linked group manifests, target-scoped issuer-disjoint dev/check sampling (seeded base_seed:target_id), and the group-reveal boundary — per-case groups release only against one exact frozen evidence-pack manifest with matching target identity hash; contract drift after freezing fails closed. signal_research_objective() now carries the label-free target descriptor into H1 and all objective consumers, with assert_payload_without_target_groups as the group-free scanner. signal_library gained the multi-target evaluation namespace: SignalTargetEvaluation records appended idempotently by evaluation_id to registry-level target_evaluations.jsonl, load_target_evaluations filtering by exact version/target, target_support returning None (unknown, never zero) without records; direction stats and SignalStats untouched; two targets sharing one observation double-count nothing. Specs updated (signal_library.md implemented section; signal_evolution.md ge3 implemented, promotion still unapproved). 12 new tests (projection boundaries incl. 2.0/3.0, manifest hash stability, drift fail-closed, pack-coverage fail-closed, label-free scanner, H1 descriptor, issuer-disjoint deterministic sampling, idempotent records, unknown-not-zero, shared observation, invalid result); 1045 total + lint PASS. Remaining: C6 observation experiments and C7 promotion decision package (need authorized live runs), C8 integration, B live throughput experiment.

USER PAUSE (2026-09-21, mid-C5-wiring): C5 comparison wiring is implemented and committed (label_override on _mining_evidence_packet, engine research_target_reveal param, target-mode population-ref extension at the comparison site; direction path byte-unchanged; 1045 tests + lint PASS excluding the WIP file). The C8 offline integration test (tests/test_c8_integration.py) is UNCOMMITTED WIP: promotion through the ge3-classed comparison is blocked at the downstream paired-effectiveness stage ("paired effectiveness requires at least 4 Discovery cases" — fixture shape iteration in progress; the H3 stage itself succeeds with the supported decision). Resume point: fix the integration fixture/effectiveness interaction, commit the C8 test, then proceed to C8 acceptance; C6 two-arm and B live throughput remain separately-authorized items.

C8 offline integration acceptance complete (2026-09-21): the comparison-stage wiring landed as designed — engine params research_target_reveal + research_target_sampling; in target mode comparison induction is a class-balanced prefix of the target dev side (fallback to the full population ordering when no sampling is supplied), comparison packet labels come only from the frozen reveal, and paired validation uses class-balanced target check ids (helper shared by both validation-id assignment sites). build_target_sampling_manifest now produces a class-balanced, issuer-disjoint, seeded dev/check split per contrast group — a plain split starved one group's check side and failed the >=4-case paired floor. The offline integration test (tests/test_c8_integration.py) proves the full chain with real engines and scripted roles: parallel Fast round (2 workers) commits two Plans with magnitude diagnostics; the ge3 slow cycle promotes discovery_growth_quality:v1 through the target-classed comparison (H3 sample_basis 2 positive + 2 control packets; paired validation 4/4 decisive on target check cases); slow_input carries both Plans' magnitude_feedback rows; H1 payloads carry the target descriptor and pass the group-free scanner; magnitude_contribution stays assessed=false and ge3 target_support stays unknown (C6 not run); the interrupted-before-cycle-commit state recovers via the control-layer sequence; the next Fast round (parallel) commits on the promoted registry with round-1 record.json byte-identical. 1046 tests + lint PASS. Remaining separately-authorized items: C6 two-arm observation, B live throughput, C7 promotion decision package.

Friction feedback fixes landed (2026-09-21, user-approved under correctness preservation): validation verdicts untouched; only deterministic correction feedback enriched. (1) The two Basic-quantity validators (initialize preflight and tagged-refs) now name the evidence items that already contain each missing literal ("evidence_item[N]" format chosen so the copy-candidate aggregator's message regex is not perturbed) or state decisively that the literal appears nowhere so computing/converting is invalid; repair_context carries quantity_elsewhere_hints. (2) answer_need phrase feedback now names the concrete compliant repair path (retarget index to a need already containing a listed phrase byte-for-byte; needs not editable in that output). (3) residual_need grounding feedback embeds the exact targeted need text plus a one-clause template inside its as-of bound. Full suite 1050 + lint PASS (one pre-existing v64 test initially flipped by message-embedded indices — root-caused to the aggregator regex and fixed by the location-label format, not by loosening anything). Expected effect per V130 wire analysis: targets the top correction families (numeric-grounding ~69, residual/need ~46, answer_need ~8 of 247 corrections); real-world reduction to be confirmed on the next authorized run. SSL in-process retry deliberately deferred (needs B3 unknown-send review); per-case design-gate carry-over remains a policy question.

Live runs V131/V132 (2026-09-21, user-authorized external test + self-evolution with early-stop): both froze on HEAD cb278cb with data acquisition enabled; V131 ($0.98/49min) and V132 ($0.05/5min) both ended round-1 rejected at pointers 0/0. Chain correctness verified on real wire (defect-#11 guard fired correctly twice on deterministic correction fixed points; SSL EOF auto-restarted via wrapper with lossless resume; clean rejection artifacts; friction fixes show no regression, 33% vs 31% correction rate on smaller sample). Early-stop applied per user criteria: two consecutive runs with zero committed rounds — the process cannot produce F1/magnitude measurements; root cause is model capability x strict per-case gates (Kinross initialize oscillation between horizon and quantity constraints within a 2-correction budget; reflect exhaustion at case 15 in V131 c02), not new-code regressions. Total spend $1.03 of the $12 envelope. Blocked on user decisions: per-case gate carry-over policy (third time flagged), correction budget 2->3, hard-case combined-constraint example. Full evidence in reports/live-run-v131-v132-20260921.md.

Per-case carry-over + combined-constraint guidance implemented (2026-09-21, user-approved options 1+3 after V131/V132 zero-commit deaths): a model-side case rejection (correction exhaustion / same-request guard) now records the failure, persists a finalized insufficient_information abstain prediction (label-blind: counts FN on surge truths, TN on non-surge), continues the remaining cases, and stays non-blocking while <=2 cases are excluded per evaluation; the abstain row is exempt only from the source-evidence eligibility check; above the cap or on control-plane errors the previous rejection semantics are unchanged. PlanEvaluationAttempt carries technical_exclusion_case_ids for audit; initialize corrections now require satisfying all prior obligations simultaneously (horizon + quantity grounding jointly). 4 new tests; 1054 total + lint PASS. V133 freeze+launch with the same early-stop monitoring follows.

V133 crash root-caused and fixed (2026-09-21): the live run proved the carry-over path's real-wire reachability and immediately exposed that the inline abstain construction referenced names missing from plan_evolution imports (CandidateJudgment/ConfidenceLevel/PredictionSelfReflection/RuntimeStopReason/ResearchDecision/ResearchState/AgentUsage) plus a missing ExecutionTrajectory.usage field — V133 crashed three times on the first real exclusion (attempts frozen at 40, $0.15) and was stopped before the last wrapper restart. All names imported, usage field added, and the gap that let it through (unit tests used hand-built trajectories instead of the evaluator's inline path) closed with a RuntimePlanEvaluator-level regression test (rejection on case 1 -> abstain FN, case 2 completes, exclusion recorded, metrics computed). 1055 tests + lint PASS; V134 freeze+launch follows on this HEAD.

V133/V134 live runs (2026-09-21): V133 crashed on first real exclusion (missing imports in the inline abstain construction — fixed with an evaluator-level regression test; the unit-test gap used hand-built trajectories). V134 proved the carry-over mechanism live (technical exclusions recorded, abstain predictions persisted, zero candidate rejections — the V131/V132/V133 death point is passed; reached 22/24 cases, $0.90) but exposed that the exclusion cap counts per evaluation attempt, resetting on wrapper restart while staged abstains replay — cumulative exclusions reached 8/24. Terminated per the user's chain-error criterion; total live spend $2.08 of $12. Required fixes before next freeze: per-candidate cumulative cap (replayed abstains counted), restart-exit-code distinction; research-side note: this round's plan hit 12 initialize-stage case failures (harder mix than V130) — seed-slot choice or offline plan-case difficulty analysis recommended next.

Cumulative exclusion cap fixed + V135 relaunched (2026-09-21): the exclusion cap now counts per candidate — replayed abstain rows (persisted as full trajectory checkpoints so restarts replay them like any completed case) merge with fresh failures, double-counting removed, over-cap keeps metrics None (rejection semantics). Regression test simulates the crash point (only abstain checkpoints on disk, later cases fresh): the third exclusion is refused after restart. 1056 tests + lint PASS (commit d3e5377). Seed strategy: same historical seed — the frozen pool contains exactly one eligible seed (V126 winner, family-diversity rule), so no second seed exists to switch to. V135 frozen (contract 36082c71…, budget 1900/$9.00 remaining envelope) and launched with the three stop criteria: chain errors, F1/magnitude no-progress across committed rounds, budget.

V135/V136 post-mortems + supersession fix + V137 (2026-09-21): V135 never ran (progress commit moved HEAD past the frozen revision; revision guard refused 3x, $0.54 burned on pre-freeze attempts) — lesson recorded: freeze must be the last action before launch. V136 proved the cumulative cap live (c01 carried exactly 2 exclusions, refused the 3rd, slot rejected; c02 continued) but exposed a never-exercised recovery path: after a restart following a slot rejection, re-evaluating the same slot produced different attempt content and died on the staged-attempt conflict guard (exit 2 x3; $1.37 spent, 21/24 cases reached). Fix (953509e): diagnostic staged attempts (failures recorded or metrics None) are superseded on retry — old copy preserved under attempts/superseded/, per-case failure artifacts retain the audit; eligible attempts stay verify-only. Regression test added (diagnostic superseded, eligible frozen). 1057 tests + lint PASS. V137 frozen (6dc521cf…, rev match verified before launch) and running; total live spend $3.99 before V137.

Self-evolution live campaign terminated per no-progress criterion (2026-09-21): V135 never launched (HEAD moved post-freeze; revision guard), V136 proved the cumulative cap live then exposed the never-exercised restart-after-slot-rejection path (fixed: diagnostic staged attempts supersede with audit copy, 953509e), V137 exercised that fix live (re-entry survived, replays clean) but both slots exhausted the 2-exclusion cap and the round was durably rejected. Root cause is mathematical: observed per-case failure rate ~25-30% on this hard 2025H2 case mix makes P(round viable at cap 2/24) ~1-4%. Seven consecutive live runs (V131-V137), zero committed rounds, $5.14 of $12 spent. All four new mechanisms (same-request guard, per-case carry-over, cumulative cap, staged-attempt supersession) verified working on real wire. Blocked on user research decision: cap 2->6 (viability ~74%), model upgrade, easier case snapshot, or combination (cap 6 + easier mix recommended).

User decision executed: cap 2->6 (2026-09-22): MAX_TECHNICAL_CASE_EXCLUSIONS raised to 6 with spec rationale (at measured ~25-30% per-case exhaustion rate, per-slot viability 0.39-0.61 and round viability ~0.63-0.85 vs 1-4% at cap 2); tests updated for the new cap including the restart-replay regression (now excludes exactly 6 then refuses the 7th); 1057 tests + lint PASS (9a6869c). Case-mix rollback option was found VOID before launch: V130 and V131-V137 all froze the identical 24-case snapshot (100% overlap verified from evaluation snapshots) — V130's success on the same cases is attributable to code-era/provider-side model behavior, not an easier mix. V138 therefore launches with cap 6 on the same snapshot; freeze is the last action before launch (soft-reset technique if needed).

V138 milestone run (2026-09-22, cap-6 + all mechanisms, $4.39/1240 attempts): FIRST-EVER complete self-evolution loop on current code — round 1 committed (c01 F1=0.690/magF1=0.157/magAcc=0.286 with 5 audited exclusions), full Fast->Slow cycle 1 committed (mined 1 signal candidate, honestly no-op promotion, magnitude_contribution=false), round 2 committed (c02 F1=0.667/magF1=0.222/magAcc=0.357 — magnitude +41% relative round-over-round, first progress signal). Run stopped by 3 provider transport failures exhausting wrapper restarts (SSL record layer x2, empty response x1) mid-cycle-2-slow; not a stop-criterion event. F1 gap vs V130 (0.690 vs 0.800) is the honest price of abstention-in-denominator vs V130's whole-candidate-death semantics; magnitude already exceeds the V130 baseline. Workspace intact and resumable under the same contract. Reports/live-run-v138-20260922.md.

V130/V138 systemic repair ready for fresh live validation (2026-09-22): same-Signal quantity corrections now authorize only validator-proved provenance coordinates and still fully revalidate; technical abstentions remain scored but are removed from research/magnitude attribution across Critic, proposer, meta FIFO, and Slow; production freezes and wires bounded Plan parallelism with worker-local mutable roles and serialized event writes; dashboard reports completion and magnitude distributions; and Slow's controller symmetrically requires exploration of every available structured/narrative modality without candidate quotas. Zero-call replay exactly reproduces V130 `0.800000` and V138 `0.689655`, authorizes the three real provenance edits that old scope projection erased, proves round-1 reflection reaches the real round-2 proposer without synthetic technical lessons, places all five development 10x+ cases in ge3-high against 577 2-3x cases, and preserves V138's narrative candidate materialization/validation. The technical-only V130 substitution is a diagnostic `0.812500`, not a live score. See `reports/v130-v138-prompt-flow-repair-20260922.md` and the machine-readable replay report. Full suite 1061 + lint PASS; fresh revision-bound live validation remains the provider-dependent gate.

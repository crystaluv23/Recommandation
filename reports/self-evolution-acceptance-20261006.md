# 自进化端到端验收：2026-10-06

## 当前结论与要求

状态：已启动，尚未验收。用户明确授权真实自进化测试、过程中监控及必要的设计框架内修复。代码/固定prompt的正确性以实际全链路和产物检查为依据，不能用测试数量、进程存在或Registry数量代替。

1. 完整 Fast→Slow→后继 Fast 每个阶段的实际输入、原始响应、解析/修复、状态和最终产物逐份人工检查；最终验收要求无技术性排除。可成功修复的首答错误须保留并分析，但不能把终态失败隐去。
2. 至少一条真实新 magnitude 因子通过完整技术准入并原子入库；核对精确 spec/skill/tests、research target、fixture、admission proof、Registry版本/hash。随后证明新版本实际被检索、执行、进入预测证据；3–10x/10x+选择必须有证据，不能用prompt配额或自动映射强迫。
3. 追踪源反馈→诊断/Experience→后续实际prompt→改变的Plan/Signal/研究动作。有效性另用现有独立固定cohort、失败分母和四臂协议；没有预先冻结的协议及足够结果，状态为未验证。入库、使用、productive reuse、观察正确率与独立增益保持分开。

## 运行身份与冻结边界

- Run：`/Users/l/Project/Recommandation/runs/cold_start/minimal_rounds_v177_integrated`。
- 冻结源码：`/Users/l/.codex/worktrees/evolution-acceptance-20261006/Recommandation`，HEAD `a7d8a057f483251e93df602665670389ef353e5c`。运行中不得改此源码；主checkout后续文档checkpoint不改变运行源身份。
- 实际入口：冻结源码的 `scripts/run_minimal_rounds.py --root <上述run> --run`，真实生产角色、RuntimePlanEvaluator和DualLoop；非mock模型流程。
- 前序：`minimal_rounds_v171_slow_bootstrap` 的已提交 Slow cycle 1，继承其 hash-bound/transitive历史和 Registry v8。v176未提交的7案不冒充当前历史或当前版本结果；原件保持。
- Registry v8/hash：`180814422ea72ce91eff4afddde022644c5fba10b5eff4cab6723e4e373dce62`。
- Input manifest hash：`b29b79d4569aef6835f8dfc8e066b811a268bad5958403d643695e753a82f098`。
- History manifest hash：`46e922d70d62d91fb035e42bc03b4453d98b1f07ade5542b48912cef063d04c6`。
- Contract hash：`a3d0a9606e798cfa77aa70cc6584a677dd2e75d7563e57481424f628d5d7a3c9`。
- 两个Plan顺序评估，每个固定24案（16 Anchor+8 Random），16 Discovery；固定40个案例/标签/Locked Test hash与前序相同，3606个源文件已校验。Locked Test保持封存。
- 全部角色：DeepSeek `deepseek-v4-flash`，禁止模型web；可用历史数据调用按冻结broad policy和PIT纪律进行。预算为既有诊断入口的1200 attempts / $100总上限（上限，不是预估实际费用）；不得自动扩大或换模型。
- Worktree仅通过本地symlink访问原始oracle、approved输入、v143参考合同及.env.local；不复制或输出secret。完整输入manifest保存原始source_path与hash。
- 主checkout既有未提交的6份Experience reuse规格与v151文件均为本次之前的变更；未混入执行源码或本次checkpoint。当前执行版本仍使用已提交的knowledge实现，不能声称未实现reuse_success_rate已完成。

## 进程与监控

- 控制目录：`/Users/l/Project/Recommandation/.delegation/live-runs/v177`。
- `run.py` 保存实际child `process.json`、`cycle.log`、wrapper日志和最终 `exit.json`。初次wrapper/child PID为85458/85459；2026-10-06 21:45:36原代码恢复为88114/88115。检查时重新验证command，不能只相信旧PID。
- 启动：2026-10-06 21:38:16 Asia/Shanghai。
- 本聊天heartbeat：automation id `automation`，每10分钟继续本报告中的待办，状态无行动变化时安静，有意义进展/失败/完成/需用户处理时通知。
- 402余额/权限/预算耗尽：停止自动重试并报告；暂时transport只允许原代码/合同/缓存恢复。单一运行锁，禁止重复启动。
- 原入口仅完成一个Fast→Slow诊断周期；完成后应先人工验收再用当前输出Registry/提交历史准备冻结后继Fast，不能把本周期承诺成已经完成后继消费。
- 初次运行在21:43:26因SSL unexpected EOF退出1。原`exit-initial.json`/`process-initial.json`已保存；恢复保持冻结源码/合同/缓存，未扩大预算。当前监控已接续到聊天`01a11172-f0cd-7b93-a286-e9c74f59fb8f`，同一automation未重复创建。
- 第二次SSL unexpected EOF在22:00:40退出1；验证旧PID退出后保存`exit-resume-01.json`/`process-resume-01.json`，22:02:24同代码/输入/缓存恢复为wrapper/child 93431/93432。当前PID需每次重新核对；恢复未改变运行合同、预算或错误原件。

## 已亲自查看 / 已验证

- AGENTS、vision/architecture及Plan/Signal/control/benefit契约、累计收敛与增量修复经验、v176支付中断与恢复报告。
- 当前未提交规格差异；无执行源码脏变更。固定Predictor prompt全文（冻结角色代码1765–1855）：目标是六个月adjusted share price、5日均值；四态机会判断与binary分离；magnitude三档均明确可选，无最高2–3x限制；magnitude用途不自动决定预测档位，unverified因子不等同已证实收益，禁止web及身份/标签泄漏。
- 新input manifest与前序splits/Locked Test逐值一致；history/Registry/contract/current pointer已读取，当前round/cycle=0/0、phase=fast_loop。还没有阶段完成声明。
- 启动前当前已提交代码全量：1505 tests / 55.811s / PASS。测试日志 `/tmp/evolution-20261006-tests.log`。实际live请求内容验收仍待逐份记录。

## 人工阶段检查台账

|阶段|实际输入/固定prompt|原始响应与修复|终态产物/内容|结论|
|---|---|---|---|---|
|Plan proposal/经验采用|实际固定指令与首Plan内容、历史低估brief已查|两个实际新回答均缺used_experience_refs|旧解析器按legacy接受，采纳未知|发现契约缺口；主源码已修，未进入v177|
|Initialize/Basic Info/need|首案固定指令、部分Basic Info与完整初/终state已查|机械恢复/needs纠错已查|部分财报/新闻投影有明确遗漏，commentary仅开头；重复needs待查|局部内容检查，未整体验收|
|Signal routing/apply/Reflect|首案两轮选择与结果、第三案失败已查|routing与need局部patch可表达；Signal仍有技术失败|600 MW→1000 units无依据；第三案两个validation_failed及一个budget_blocked|内容/可靠性未通过|
|Predictor/预测保存/标签后反思|首案和第三案请求、首/第三及Life Time预测与反思已查|首案posthoc outcome局部纠错通过|首案阴性正确不代表增益；第三案技术失败未携带精确诊断到Posthoc|部分已查，反馈归因仍待修|
|Plan/Round critic、提交|待查|待查|待查|未验收|
|Slow input/memory/cross-round|待查|待查|待查|未验收|
|direction+magnitude Mining、Update|待查|待查|待查|未验收|
|spec/skill/tests、fixture/admission|待查|待查|待查|未验收|
|Registry atomic transition/周期提交|待查|待查|待查|未验收|
|后继Fast真实消费/预测幅度|待查|待查|待查|未验收|
|固定cohort独立增益|协议未冻结|未开始|未产生|未验证|

每次验收增加精确文件/request hash、case/role、结论与仍未知内容；只检查hash或schema不得标记内容PASS。定量指标保留全部失败分母；正常研究误判、无因子和证据不足不能自动归因于技术问题。

## 2026-10-06 21:52人工检查与修复检查点

此时有7个已保存完整案例，Fast/Slow提交指针仍0/0，88次attempt记录成本$0.3278632；记录成本含失败请求保守预留，不等于供应商账单。新快照见`reports/v177-initial-stage-audit-20261006.json`：自动库存与人工读过的范围逐案分开，余案/后续阶段保持待查。

- 已直接查看首案`cik_0000895728:20250930`的初/终ResearchState、两轮Signal结果与literal证据、预测、完整posthoc。它预测unlikely、真实1.1217x，但commentary只见开头和部分源遗漏，不能将正确结果解释为已证实因果规则。订单`order_confirmation_disclosed:v2`原skill有“1000 units (or equivalent)”，实际解释以600 MW推断超过1000 units，未提供维度/换算依据；这是内容失败，不能改冻结因子或自动猜新materiality定义。
- 首次routing纠错request `d23f2bdca1297ff9b3d78828f4ce295eda864333ef51c4b46235a6e3a1e90ddb`处理五个ownership/phrase问题，实际typed patch将四个选择改为context用途，完整结果保留未回答needs；Reflect request `fcee5e11ce762a236135cc13cca0db79c19b13a496d3a69d7e567191aaf59478`仅移除授权need；posthoc request `512cfacff8cfa1efc9eaf4863bf43c48d2d3e4cf27926bd999369eac5438f598`纠正不适用的magnitude outcome为binary事实。没有把可恢复初答错误藏成无错误。
- 第三案`cik_0000701818:20250930`的guidance citation在投影内部边缘，纠错给出可复制完整候选仍终态validation_failed；financing literal未满足精确版本required phrases，同样validation_failed；order纠错required=31524、remaining=30663而budget_blocked。案例仍finalized/possible/2-3x，真实non-surge/1.5662x；因此case技术排除0不等于因子层零技术失败。实际Posthoc request `0e87be897a937b7d136db876e0bdb29ad3a15e0e822e105de8221f0581854a4c`只见“未产生validated domain result”的通用summary，没有validation_failed/budget_blocked诊断；反思将其写入forward-catalyst信息缺口，需要检查producer→projection→posthoc→Critic/Slow全家族。
- 两个新proposal request `b55c1921612de031198c71007d36e7423d82e44871cb270d74db1479857c44a0`、`6b472ebe83a748394ddd434f17dbf50242ba55f2fcd9c0e2fff293464748fe0d`均只返回四策略字段。实际prompt明确要求used_experience_refs，旧parser却按legacy缺字段兼容，不能证明采用。修复已先写owning spec，再在主源码要求新回答字段、缺字段仅add权限、非法refs完全重验；历史Plan loader仍unknown，四策略不可被此patch重写。
- 两份付费原答通过真实生产Proposer离线重放，只脚本化补`[]`：策略/原件保持、0外部调用。这证明技术边界修复，不证明模型真实采用经验。证据`reports/v177-adoption-production-replay-20261006.json`。5新回归、250相关测试PASS；首轮全量因一份旧离线作者fixture缺新字段失败，修正fixture后1510全量/57.584s PASS。修复未热改v177。
- 独立增益标准已向用户请求具体确认：40未参与开发公司、2独立重复、四臂、Binary及magnitude macro-F1各提升0.05、Binary增益95%公司聚类下界>0、技术失败0。尚无答复；候选方案不是已冻结/已授权扩预算的protocol，不能宣称gain_confirmed。链路测试不依赖此回答继续。

## 2026-10-06 22:10技术归因修复与真实回放

- 快照22案，229 attempts，记录成本$0.89510988，Fast/Slow提交指针0/0；81 success、8 domain_unavailable、7 validation_failed、3 budget_blocked。14个非空magnitude均2–3x，8个null。这里只是库存，未把22案全部标记为人工内容验收。
- 实际固定prompt/轨迹阅读发现：`_assemble_final_context`丢掉execution，且同ref逐轮卡片从全局最新结果取值；Critic的初步trajectory视图随后被二次压缩覆盖；case→Plan→Round原始反思不保存Signal技术状态。已先补owning spec，再修主源码所有实际出口。新增可选`recorded_signal_execution_failures`只含真实round/ref/status；旧缺字段仍未知，[]只表示没有已记录故障；不把混合有效/失败Signal的整案自动排除，不改评分/经济结论。
- 固定Predictor与共享反思指令明确技术失败不代表公司数据缺失、经济事实不存在或有效因子预测失效。原始错误code/message保留在本地SignalResult，模型只接收status，避免泄漏内部路径/身份或让诊断文本充当证据。
- 6项专项测试通过：全部状态、同ref跨轮结果、实际Predictor/Posthoc/Critic请求、Round JSON持久化及生产source resolver的signal_mining读取、legacy未知与非法诊断反例。全量1516 tests / 57.534s PASS；lint PASS，日志`/tmp/v177-provenance-full.log`、`/tmp/v177-provenance-lint.log`。
- 22份真实v177轨迹经生产最终组装/Posthoc/Critic和CaseReflectionEvidence反序列化回放全部保留原status，原件sha256不变、0外部调用。逐案记录在`reports/v177-execution-provenance-replay-20261006.json`。Critic使用显式本地no-findings回复，因此回放只证明链路与保留，不证明模型正确归因、live采用或研究收益。
- 亲自读取Kinross guidance初答hash `0ede8f244460503d9e964f811db8d9150f3101237f06510d72f9f67253f59f05`、纠错hash `3e5d9bcf0a6b54780579a4067b65e5fe6d5b6d49a7b3c375ff037d9c77d56c5b`及纠错完整固定指令/实际feedback：纠错重复了内部截断句；提示列出的完整候选是资本回报句，不是原guidance比较句，不能自动替换或删除来伪造经济依据。原模型初答还引用投影外完整数字，必须后续审计上游完整片段可见性与修复边界。此次状态传递修复没有消除这些原有执行错误。
- 冻结v177仍运行a7d8a057，主源码修复未进入它；后继冻结运行才可验收技术失败消除。双轴真实入库、后继消费、幅度扩展和独立增益仍待完成。

## 接续动作

1. 检查child/exit、attempt ledger、trajectory及新requests/responses；逐份读取还没检查的实际内容，不重复已经看过的原件。审计摘要应记录看过的hash和语义结论。
2. 优先处理上述Signal内部edge、version phrase和纠错预算家族，技术失败向Posthoc/Critic/Slow的实际诊断消费及订单量纲内容错误；逐份读新失败原答/纠错/context，不能只修最新报错。新源码修复只能进冻结后继，当前v177继续保持a7d8a057。
3. 完成Fast后亲自核对24案固定评分/技术排除/magnitude矩阵和经验反馈；检查Slow是否使用真实已提交反馈，magnitude Track是否完成而非假completed。
4. 成功发布后检查proof与确切目标，准备冻结后继及检索/执行/预测消费证据。对入库0、幅度仍集中2–3x或研究增益不足如实继续诊断，不改评分。
5. 独立效果评价所需阈值/样本/重复等值只能沿用已批准协议；当前尚未找到本次预注册protocol，不能任意定义后宣称gain_confirmed。必要时给用户具体、可审核的协议选择，同时继续不依赖此决策的链路工作。

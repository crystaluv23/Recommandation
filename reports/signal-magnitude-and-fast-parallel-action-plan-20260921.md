# Signal 幅度进化与 Fast Plan 并行执行：详细行动方案

日期：2026-09-21。核查代码基线：`9f85f46`。

修订：2026-09-21 评审版。新增目标数据准入硬门控、Signal 目标统计接口清单、缺陷 #11/#12 前置验收、采集 ledger 协调；固定首版线程模型与 slot 升序，允许前期只读盘点交错推进。本次确认的是行动方案修订，不代表其中尚待确定的数值门槛或实机预算已获批准。

**文件性质：下一阶段实施提案。** 本次只编写计划，不改变现行规格、代码、冻结运行或外部调用授权。研究语义和接口变更须先确认并写入 owning specs；本文件不能被当作已经实施或已获实机预算授权的证明。

## 1. 目标、范围与完成标准

两个目标分别推进、分别验收，最后集成：

- **A：Signal 幅度进化。** 让 Slow 除了发现区分暴涨／非暴涨的信息，也能发现、验证并保留区分上涨幅度的信息，形成“幅度反馈 → 分层对比 → 可复用测量 → 独立验证 → Fast 消费 → 晋升 → 下一轮可见”的链路。
- **B：Fast Plan 并行。** 在同一轮冻结输入下并行评估不同 Info Plan，缩短等待时间，同时保持案例内研究顺序、预算控制、候选公平性、恢复和提交正确性。

“magnitude 改善”是档位判断更准确，不是预测得越来越高。“并行成功”是相同研究工作更快完成，不是减少案例、减少 Signal 检索、跳过验证或放宽门槛。

成功分三个层次记录：

1. **实现完成：**相关字段、消费者、存储、版本与测试齐全。
2. **流程完成：**真实引擎与独立授权的实机运行能够恢复、提交，并把学习和 Signal 传给下一 Fast；无候选／无晋升也能诚实完成合法 no-op。
3. **效果成立：**A 在预先冻结的配对评估上有幅度增量且满足 F1 保护；B 在可比工作量上降低耗时，且费用、限流、失败和输出完整性可接受。

单元测试通过不等于实机流程完成；一次流程完成不等于研究有效；并行不保证实时模型输出逐字相同。

## 2. 当前基线与证据

### 2.1 已完成部分

- 确定性逐案 `magnitude_feedback` 与 Plan `magnitude_diagnostics` 已实现，已进入反思、meta 和 proposer 输入链。
- Fast 选择已批准为：eligibility 后，Binary F1 主序、F1 精确相等时 magnitude macro-F1 次序，最后稳定 ID。该规则本计划不改。
- Slow source view 已增加 locally committed Plan 的幅度诊断；缺少新字段的 legacy meta 不补零、不伪造反馈。
- Slow 结果仍明确记录幅度贡献未单独评估，现有方向性晋升规则未改变。
- 已有离线故障注入覆盖多项跨轮恢复；实现报告记录全套 1006 测试通过。此为先前验证记录，实施时须重新运行当前版本。
- 当前 Fast 候选在 `PlanEvolutionEngine.run_round` 中顺序 evaluate；每个候选内部也按案例顺序执行。
- workspace 有单执行者锁；预算账本 reserve／finalize 是 JSON 读改写；角色存在可变 evaluation context；Raw Info append 已有文件锁。

### 2.2 两个尚未闭合的问题

1. Slow 可以看见幅度错误，但不能仅凭真实的幅度增量获得目标适配的晋升。现有 E2／H3 的 positive/control 分组、校验和有效性语义仍主要服务于方向目标。
2. 多 Plan 的逻辑独立性不等于当前共享对象线程安全。直接把 evaluate 循环放进线程池，可能导致预测时间串扰、预算覆盖、重复付费、事件序号冲突和错误恢复。

### 2.3 参考入口

- [上一阶段行动计划](fast-slow-magnitude-evolution-action-plan-20260920.md)
- [上一阶段实现及验证报告](fast-slow-magnitude-implementation-20260920.md)
- [当前架构](../spec/architecture.md)
- [Signal 引擎](../src/stock_opportunity_agent/research/signal_evolution.py)
- [Signal 角色及比较校验](../src/stock_opportunity_agent/research/evolution_signal_roles.py)
- [Fast 引擎与 workspace 提交](../src/stock_opportunity_agent/research/plan_evolution.py)
- [请求传输、预算和缓存](../src/stock_opportunity_agent/research/evolution_transport.py)
- [Raw Info 存储](../src/stock_opportunity_agent/data/raw_info.py)

## 3. 两项修改共同遵守的正确性边界

1. 标签、收益分母、预测时间、窗口、四分类映射和三个 magnitude 档位不变。
2. 预测先保存，之后才能揭示结果。比较研究可以在授权阶段看标签，但盲提取、Signal 执行和 Predictor 不能看到未来结果。
3. 匿名化、literal evidence、来源身份和 point-in-time 可用性不放宽；未来真实收入、价格或兑现结果不能作为预测时测量。
4. 固定评估样本、失败计入和 Combined 重算口径不变；不删掉难例、技术失败或 FN 来抬高分数。
5. correction 继续有界、保留无关已正确字段并完整重验证；控制面异常不能变成普通模型输出错误。
6. round／cycle pointer 是提交权威；staged、缓存、日志和模型自述不证明完成。恢复不重复消费输入、追加学习或晋升。
7. 本轮所有候选使用同一冻结 Registry 与 learning snapshot；某 Plan 提前完成不能改变兄弟 Plan 的输入。
8. 回顾性 meta 保留逐案／纵向／横向层、整条 FIFO 和导入历史编号规则；不得把案例标签藏进新 Plan 或 Signal。
9. Locked Test 保持封存。所有新增实验使用获准的研究／验证数据，并明确开发集与独立验证集。
10. 同一 workspace 只有一个 round／cycle 协调者；B 的 worker 不成为新的独立 run-loop。

## 4. 实施前需确认的决策

| 决策 | 建议方案 | 为什么需明确 |
| --- | --- | --- |
| 幅度目标集合 | 原方向目标保留；首版仅 magnitude_ge3 可申请数据准入，ge10／extremes 延后且不铺专属代码 | 先过数据门，再实施新目标 |
| 样本资格及匹配 | 发行人隔离，按预测时可得条件审计行业／时期／规模／流动性等混杂 | 可能实质影响研究结论，不能事后挑配对方式 |
| 最小独立支持 | 基于实际数据盘点制定每组发行人数及时间覆盖要求 | 不沿用二分类最小 case 数就声称极端幅度可验证 |
| Signal 目标语义 | 测量与研究目标分离，目标相关状态显式声明 | 防止“不支持 10x”被解释为“不支持上涨” |
| 幅度晋升规则 | 公共正确性门槛 + 目标有效性 + Fast 系统保护 | 属于晋升契约变化，需要 top-down spec 更新 |
| F1 保护与统计判据 | 第一版优先观察值不下降；支持量与不确定性要求在实验前冻结 | 不自行添加容忍区间、收益权重或显著性阈值 |
| 并行范围 | 只并行候选 evaluate，初版 max_parallel_plans=2 | 控制第一版变更面 |
| 预算紧张时调度 | 统一仲裁、确定性公平派发，全局不足则暂停 | 避免响应快者抢完预算导致样本偏差 |
| 实机运行 | 新契约、新 workspace，预算与调用范围单独确认 | 旧运行授权不自动覆盖新实验 |

当前架构已经批准 F1 同分时幅度优先，不需要退回上阶段的单目标提案。A 的目标适配晋升、B 的并发调度仍是新增契约，不得由候选模型自行决定。

## 5. 工作流 A：Signal magnitude 研究与晋升

### A0：盘点数据与现有二分类假设

**执行**

- 对获准研究池统计每档 case 数、独立发行人数、相关日期簇、行业／时期分布和预测时证据覆盖。
- 核验跨 induction、holdout、Fast 消费实验的重叠，防止同公司多个日期同时扮演独立归纳与验证。
- 逐层列出固定 surge/non_surge 假设：采样、正负标签映射、H1/H2/H3、E1/E2、contrast ref 校验、candidate tests、effectiveness、provisional、统计与检索卡。
- 接口清单必须包括 `src/stock_opportunity_agent/signal_library.py` 及其 owning spec：`SignalStats.record_result`、`record_observation`、`surge_rate`、registry 读写、学习事件与 profile 聚合／读取；追踪 `plan_evolution._record_signal_statistics` 的真实调用链。当前源码可见的 registry 外部 `record_observation` 调用在该 Fast 路径，不能假定 Mining 已有同名入口；Mining 侧须盘点实际 effectiveness／学习事件／持久化调用，分别注明目标维度如何传递。
- 把历史幅度错误分成测量缺口、归一化／适用条件缺口和纯分析策略；后者继续走 fast_plan_action。

**已核验原始支持量**：以下来自批准的 v13 数据，未扣除证据不可用、相关日期和隔离约束；不同档位的发行人数不能直接相加。仅查看 Discovery 和 evolution validation，未打开 Locked Test。

| 数据集 | 2–3x | 3–10x | 10x+ |
| --- | --- | --- | --- |
| Discovery | 406 案／270 发行人 | 157 案／101 发行人 | 2 案／2 发行人 |
| Evolution validation | 171 案／109 发行人 | 62 案／43 发行人 | 3 案／2 发行人 |

来源：[Discovery](../runs/cold_start/evolution/full-market-expanded-2025plus-v13-approved-inputs/expanded_dataset_proposal/discovery.json)、[Evolution validation](../runs/cold_start/evolution/full-market-expanded-2025plus-v13-approved-inputs/expanded_dataset_proposal/evolution_validation.json)。评审中的 ge3 高／低组 `65/171` 属于 evolution validation；Discovery 原始案例数为 `159/406`。不得用 validation 总量替代 Slow 归纳池的可行性审计。

**硬准入门控**：每个新增目标必须产出 gate 记录，包含目标／数据版本、归纳与验证各组独立发行人数、时段覆盖、发行人及日期隔离、预测时证据覆盖、已确认最低支持要求、通过／不通过及原因。门槛须在挖掘结果揭示前确认；任一侧不达标或门槛尚未确认均不得进入目标专属 schema、投影、执行或晋升实现，不得自动降门槛。

**交付／验收**：数据支持表、gate 记录、泄漏与重叠审计、接口清单。当前 ge10／extremes 不进入首版；ge3 仅是优先准入候选，不能凭原始案例总量宣告通过。数据门失败时记录 blocked／insufficient_support，并继续不依赖该目标的工程工作。

### A1：定义冻结的研究目标契约

第一版只保留原方向目标和通过 A0 门控后的 ge3，具体新增字段名在规格阶段确定：

| 目标 | 研究总体 | 高组／低组 | 用途 |
| --- | --- | --- | --- |
| surge_direction | 全部合格案例 | ≥2x／<2x | 原有方向研究不变 |
| magnitude_ge3 | 真实 ≥2x 案例 | ≥3x／[2x,3x) | 通过 A0 硬门后才实施 |

`magnitude_ge10`（≥10x vs 2–10x）与 `magnitude_extremes`（≥10x vs 2–3x）仅列为未来研究问题。首版不为其新增专属枚举、schema 分支、采样器、prompt 或验证／晋升代码。后续扩大独立数据支持并重新通过 A0 后再决定实施；极端对照届时仍须补中间档验证。

- 这是原有标签的固定投影，不重新定义未来结果。
- 研究总体按真实标签界定，由框架在回顾性研究侧管理；不能只采集现有 Predictor 的 TP，否则会排除 FN 中的高幅度案例。
- 分组规则、样本 manifest、目标版本与评估协议进入身份哈希和冻结契约。
- 新字段至少明确目标、适用总体、分组规则版本和验证协议引用；最终最小 schema 由 owning spec 决定。
- 不把高／低组直接塞入旧 positive/control 让方向验证器误解；旧方向入口保持原意，新目标使用明确投影。

**验收**：新增目标有通过 A0 的 gate 引用，未通过目标无专属实施面；原档位边界 2／3／10 不变，ge3 投影正确；同案不同目标的投影可审计；目标变化导致适当的 cache／work identity 变化；旧方向工件兼容且分数不变。

### A2：复用 Mining 链，改变比较问题

**执行**

1. H1 基于已提交反馈提出可测量假设；目标是固定的，模型不能改组、改窗口或要求未来事实。
2. E1／H2 先做匿名、无结果标签的证据提取；可知道通用研究目标，不知道当前案例的实际组别。引用 ID 和包顺序不得编码高低组。
3. 冻结证据包后，E2／H3 才获得分组，比较可观察机制；grounded floor、literal 引用和 candidate schema 按新目标一致校验。
4. 首版对 ge3 假设检查 3–10x 子群与反例，防止少数 10x+ 案例主导结论；不借此启动延期的极端对照目标。
5. 同一个测量已有实现时优先复用或 Update；仅研究目标不同，不机械复制一个新 Signal。

可探索的机制包括订单相对收入规模、经营弹性、资金约束、稀释、需求兑现条件等；它们只是候选，不是预设正确因子。提取器测量当时可见事实，不能直接输出“未来将涨十倍”。

**验收**：实际 H/E 请求与验证器目标一致；无标签提取可证明；无候选、证据不足、假设不成立三种结果不混用；一个目标失败不吞掉其他安全独立单元，但共享数据／预算暂停继续向上传播。

### A3：让 Signal 含义与 Fast 消费一致

- 优先保留现有事实测量、数值、解释和 literal 证据。研究价值通过独立、版本绑定的目标评估记录表达。
- 若需要 POSITIVE／NEGATIVE 相对某目标解释，则将参照目标显式传给所有消费者。不能让 magnitude-negative 静默进入原有 direction-negative 统计。
- 用途说明进入检索卡和分析上下文，但不把历史成功档位、案例映射、未来收益或验证答案放进执行侧。
- “不支持 ≥3x”不能被直接投影为“不支持 ≥2x”；未来如获准扩展到 ≥10x，同一边界原则继续适用。
- 同一 Signal 可以对多个目标有用；统计按 signal version × target × evaluation protocol 分开，旧数据不伪装为新目标观察。
- **`signal_library` 是必改接口面，不是可选项。** 首选保留既有 `is_surge`／surge_rate 方向统计，增加独立、版本绑定的目标评估统计命名空间，不把高低组布尔值混入旧 `surge` bucket。具体存储与接口先写入 owning spec，再修改 registry、stats、learning event／profile 及所有生产与读取入口。
- 物理执行观察与目标评估分别去重：一次真实 Signal 执行只累计一次执行数、token 和费用；多个目标记录各自 evaluation identity 与结果，引用同一观察而非重复记账。跨目标重启／补录也必须幂等。
- 旧观察与学习事件明确属于原方向语义或未具备新目标证据；不自动迁移为 ge3 验证。新目标统计缺失为 unknown，不填零，不伪装为通过。
- H_analyse／Predictor 仍负责最终方向与幅度；Signal 不另设一个替代 Predictor。

**验收**：构造“支持上涨但不支持三倍”的案例，证明检索、分析与统计不反转方向；一条执行产生两个目标记录时执行数和费用不翻倍，重启补录不重复；legacy Signal 与 surge_rate 行为不变，旧学习记录不冒充 ge3 支持；新用途不能绕过证据守卫。

### A4：先观察验证，暂不改稳定库晋升

两层观察实验：

**测量层**：独立 holdout 上复测高低组差异、缺失率、反例、已有 Signal 冗余及混杂。固定选择／阈值后再开验证；反复查看过的 holdout 不再称为未见样本。记录所有尝试，控制反复挖掘带来的选择偏差。

**消费层**：固定 Plan、模型设置、Registry 基线、数据与案例，做候选 Signal 加入／不加入或新旧版本的配对盲预测。新因子用 absent/present，Update 用 old/new；每个 arm 的实际可见差异有 manifest。

- 观察同时包含真实上涨与 non_surge，避免幅度改善却增加 FP。
- 报告 Binary F1/P/R、幅度 macro-F1/accuracy、每档 support／recall、低估／高估、FN、失败及成本。
- 条件幅度准确率只作诊断，不能单独奖励只挑简单 TP。
- 路由随 Signal 干预改变时，结论为端到端干预效果，不宣称是单条数值的纯因果效应。
- 相同请求缓存复用不算独立重复；不同 arm 不能误用同一预测。按发行人／相关日期考虑不确定性。

**验收**：得到可信的配对增量或诚实的无增量／证据不足结论。候选可保存，但没有新增晋升授权；`assessed` 只在实际完成相应协议后置真，携带协议和证据引用。

### A5：确认并实施目标适配的晋升

公共 correctness 门槛不动；方向任务继续走原有效性门槛。幅度任务新增其目标有效性与 Fast 系统保护，不要求它必须先证明方向严格增益。

提议逻辑：

```text
公共来源／时点／执行／样本隔离门槛通过
  AND 幅度目标在独立验证上有合格支持
  AND Fast 消费有增量且满足已确认的 F1 保护
  → 可进入幅度用途的正式晋升判断
```

- 不把方向 recall floor 生搬到幅度测量；也不删除该 floor 在原方向路径中的作用。
- 不仅凭 E2 的自然语言“supported”或一次组间差异晋升。
- 独立支持不足保持 inconclusive／按明确新契约管理 provisional，不能把旧方向 provisional 状态直接当作幅度资格。
- 若改变既有 Signal 的状态解释或数值，需同时检查其原有用途的退化，避免升级破坏旧 Plan。
- 原子 Registry transition、candidate version/hash、恢复与下一周期可见性继续共用现有链路。

**验收**：方向指标平、幅度确有增量的合格候选有可解释通道；方向或既有用途退化者被拦截；无效证据、样本不足、重复晋升均被拦截；真实下一 Fast 请求可见新版本和正确用途。

## 6. 工作流 B：有界 Plan 并行

### B0：测量基线并盘点共享状态

- 分解耗时：proposal、数据获取、模型等待、纠错、重试、critic、提交和 Slow；按 Plan／case／stage 记录。
- 审计共享对象：evaluator、controller、signal agent、Predictor、LLM runner、resolver/provider client、缓存、Raw Info 内存索引、attempt ledger、事件序号和统计写入；显式包括 `data_requests.jsonl` 与 `data_acquisition_requests.jsonl` 的全部 append／读／恢复入口，记录完整写入、身份去重和所有权规则。
- [累计缺陷记录](fast-slow-magnitude-baseline-audit-20260920.md) 的 #11（第三类缓存重放死端）与 #12（V127／V130 SIGINT 无效）升级为实施前置条件：#11 的通用 same-request guard 先验收，再启用 B2 in-flight 去重；#12 按 B4 修复并验证后才允许 B5 并发度 2。风险登记或旧退出日志不能代替修复验收。

**交付／验收**：耗时表、可变对象所有权表、共享写入清单、串行重放基线。先确认潜在吞吐收益，不承诺倍数。

### B1：定义并行边界与协调者

```text
唯一协调者持有 workspace execution lock
  → 冻结样本、父本、meta、Registry、learning、limits
  → 顺序生成并持久化全部候选
  → 按 candidate slot 升序有界派发两个独立 evaluate worker
      每个 worker 内 case 顺序及 case 内研究顺序不变
  → 等待全部候选达到已审计终态
  → 按原 candidate slot 顺序验证／汇总
  → 顺序 critic、round reflection、round commit
  → archive／stats／learning／meta 协调恢复
  → 进入原有 Slow
```

- 第一版固定为单协调进程＋有界 worker 线程。当前 transport 使用 urllib 阻塞 IO，不保留首版进程／SDK 分支；这不意味着共享角色和存储天然线程安全，仍须完成所有权隔离，不以多份 CLI run-loop 替代。
- 候选按 slot 升序派发，空闲名额接收下一个未派发 slot；完成快慢不改变候选身份或汇总顺序。此规则不替代 B2 的请求级预算公平性。
- 每个 worker 建立独立的可变角色、resolver 上下文与客户端；冻结对象可共享只读，共享设施必须通过明确协调接口访问。
- 不跨 Fast round／cycle 并行，不让 Slow 与未结束的本轮 Fast 重叠。
- 候选数量、案例数、研究限制、评分和 selection 不因并发改变。
- 通过稳定 candidate slot 标识工作，不按完成顺序重新编号；记录只有协调者可推进的 round／cycle 状态。

**验收**：两个不同 prediction_time 并发执行无上下文串扰；一个 Plan 的 post-hoc／learning 不进入另一个 Plan；并发度 1 与串行基线一致。

### B2：统一预算、请求去重与限流

**准入条件：先关闭缺陷 #11，再启用 in-flight 去重。** 用真实 correction adapter 重放 full-revert projection＋identical revalidation，证明通用 same-request guard 能识别同一逻辑修复中的无进展循环。失败有界终止并保留审计；只有守卫允许且确有新增反馈时才产生新请求，不添加随机 nonce 绕过缓存。预算锁等独立准备可先做，但去重接线不能越过此门。

必须区分三种语义，并用组合测试验证：

| 场景 | 处理 |
| --- | --- |
| 同一逻辑 correction 再次发出已拒绝的完全相同请求 | 无进展守卫处理，不能无意义重放到预算耗尽 |
| 不同 Plan 同时发出相同合法请求 | 合法共享，等待同一原始响应；不能判作 correction 死循环 |
| 相同请求发生可恢复传输失败 | 走原传输重试／未知发送状态规则；不能与领域拒绝混为一谈 |

guard 作用域需绑定逻辑工作／correction 链，不能用全局“见过 request hash 就拒绝”的规则。真实外部请求缓存身份仍按 canonical body 与契约计算，两类身份不能混用。

**预算**

- 所有外部调用经统一协调器的原子 reserve／finalize；可在保留 JSON 存储下先用同进程互斥保护完整读改写，避免为首版引入不必要数据库。
- workspace 文件锁继续阻止第二个独立写入者。未来若引入子进程，必须改为 IPC 单写入或真正跨进程事务，不能沿用线程锁假装安全。
- attempt ID 唯一，费用预留和结算不覆盖；结算幂等或明确拒绝不一致重复。
- 预算锁只覆盖短事务，不持锁等待模型网络响应。实际调用前必须先完成授权与费用预留。
- 按稳定 Plan 顺序公平仲裁就绪请求；记录 admitted 序列。全局预算不足暂停，不把未获额度的候选判为研究失败。

**相同请求协调**

- 以真实 canonical request identity 做 in-flight 去重：已有相同工作时其他 worker 等待，不各付一次钱。
- 区分传输结果共享与领域解析：共享同一不可变原始响应，各自保持正确的轨迹引用和上下文校验；不得共享可变角色状态。
- correction 输入、目标、model／provider、契约和会影响响应的参数不同则身份不同；不得通过省略字段扩大命中。
- 处理 leader 失败、等待者取消和接管，不让等待永久悬挂。总账只记真实物理调用，逻辑消费者引用同一 attempt，不重复计费。
- Raw Info 已有 append 锁继续使用；采集去重、provider 限额、内存索引刷新和数据可见性另行验证。并发 append 成功不自动证明采集链安全。
- `data_requests.jsonl` 与 `data_acquisition_requests.jsonl` 也须采用协调写入或受保护的完整 append，明确物理采集与逻辑消费者引用的关系；并发和崩溃后不得出现半行、重复身份、丢失完成状态或重复计算调用费用。Raw Info append 锁不覆盖这两份 ledger。

**限流**

- 全局 in-flight 上限独立于 worker 数，provider backoff 统一协调，避免两个 worker 同时重试造成风暴。
- provider 限流暂停不成为 Plan fitness；记录429／超时、重试、实际并发和等待。

**验收**：最后一个预算槽同时被争抢时最多一次准入；同请求并发只形成一次真实发送；失败可恢复；不同请求无错误复用；账本始终可重算，无重复／丢失结算。

### B3：工件所有权、提交屏障和恢复

- worker 仅写自己独占的 Plan／case staging 和原始结果；文件名与 work ID 确保不会与兄弟任务冲突。
- round 级事件经队列由协调者分配唯一序号，payload 带 round、candidate slot、plan、case、attempt。事件时间交错允许，事件不是完成权威。
- 协调者校验预期案例集合、快照、输入 hash、完整性和 eligibility，再构造聚合结果。
- 候选正常失败保持现行隔离；所有已准入候选必须有完整或明确失败结果，不能提交“恰好先完成”的子集。
- 控制面暂停时保存已完成检查点并保持 round pointer，不制造部分 round commit；恢复只处理未完成工作，不重新提案或重算已保存有效案例。
- 原 round commit 与 post-commit 幂等恢复保留，不能因并行新增第二个 archive／meta 写入者。

**在途请求**

外部发送、响应持久化和本地结算不是天然的跨系统事务。崩溃后无法确认是否已付费或产生响应时，标记 unresolved，保留预留与证据；有 provider 查询／幂等能力才据此核对，否则不能自动宣称未调用或无条件重发。明确承认无法普遍保证外部 exactly-once。

**验收**：worker 返回顺序打乱不改变固定响应重放的指标、选择和 meta；协调者崩溃可恢复；重启无重复学习、晋升或漏掉未完成候选。

### B4：暂停与停止作为上线门槛

- **关闭缺陷 #12 是 B5 前置条件。** Python 的 SIGINT 处理只由协调者主线程承担，worker 不安装信号处理器、不依赖收到 SIGINT；信号处理只标记取消意图，协调者统一停止准入，worker 在安全边界检查共享取消标志。
- 协调者等待 future／join 时必须使用可响应停止的有界等待，不进入无限阻塞或吞掉 KeyboardInterrupt 后继续派发；同时验证线程池退出路径不会再次无界等待。
- 取消标志不能中断正在阻塞的 urllib 调用；明确连接／读取等待的超时边界、在途等待截止与强停后的 unresolved 处理。不得声称设置标志即可立即停止网络调用。
- 有界等待在途请求完成和结算；不再继续派发 correction、下一 case 或新 Plan。
- 超时强停时保存可恢复状态和 unresolved 尝试，不把未知费用释放成可用预算。
- 单个 worker 的本地错误允许其他安全工作完成；授权、预算、用户暂停、共享数据故障按全局控制面传播。
- 重启先审计工作所有权与在途状态，不能让原 worker 与恢复 worker 双重执行。

**验收**：对主线程等待 worker、worker 阻塞传输、线程池关闭等路径复现 #12 的停止场景；在模型请求中、纠错前、case 写入后、round commit 前后分别注入暂停／崩溃，指针和预算一致。取消标志生效后不再准入新请求；已准入／已发送请求逐项结算或标为 unresolved，不假装全部被立即中断。

### B5：受控启用并发度 2

- B1–B4 在并发度 1 验收通过后，再启用 2；并发策略及资源限制写入新 run contract。
- 先做离线固定响应压力与故障重放，再做独立授权的小规模真实吞吐实验。
- 比较相同候选和案例工作量的执行段耗时；缓存热度对齐或单列冷／热结果，不能拿热缓存并行与冷缓存串行比较。
- 记录 p50／尾部耗时、物理调用、逻辑缓存命中、token／费用、限流、失败、停止延迟、最终完整案例数。
- 不要求真实模型在两次新采样中逐字一致；正确性等价用固定响应验证，实机实验检验系统行为和性能。
- 吞吐未改善或重试／费用恶化时保留并发度 1，先根据证据修复瓶颈；不自动扩大到 case 或 Signal 级并发。

## 7. 测试与验收矩阵

| 测试组 | 关键反例 | 必须满足 |
| --- | --- | --- |
| A 标签投影 | 2／3／10 边界，FN，高低组引用错配 | 新目标正确，旧方向语义不变 |
| A 数据准入 | 任一组发行人不足、证据覆盖不够、阈值未确认 | 禁止目标进入实施；ge3 也不能按总案例数直接放行 |
| A 数据隔离 | 同发行人不同日期跨集；case ID 暗示档位 | 拒绝泄漏和伪独立支持 |
| A 模型边界 | E1 输入带标签；候选要求未来事实 | fail closed，保留原始审计 |
| A 消费语义 | 幅度 negative、方向 positive 同时成立 | 不误判为非上涨 |
| A 有效性 | 全部提高档位；只报告 TP 条件准确率 | 高估和 FN 可见，不能虚假晋升 |
| A 多目标版本 | 同 Signal 不同 target 的缓存／统计 | 不串用，不混加 |
| A 观察与评估去重 | 同一次执行服务方向／ge3，重启补录 | 两份目标结果，执行次数／token／费用只累计一次 |
| A 晋升恢复 | staged、promoted、cycle 未提交时崩溃 | 恢复幂等，下一 Fast 可见 |
| B 角色隔离 | 两个不同预测日期同时设置 context | 无跨案例污染 |
| B 预算 | 仅余一次调用额度、重复 finalize | 不超额，不重复 attempt，不丢结算 |
| B 去重 | 同请求同时到达、leader 失败、waiter 取消 | 物理调用可解释，等待不死锁 |
| B 缺陷 #11 | correction 重复拒绝、跨 Plan 合法共享、传输重试混合出现 | 守卫不误伤共享，不绕过缓存，不吞掉传输恢复 |
| B 共享数据 | 同时采集／append／读取新数据 | 不重复污染，时点与来源不变 |
| B 采集 ledger | 两份 JSONL 同时 append、写入中断后恢复 | 无半行／丢记录／重复费用，身份和状态可核对 |
| B 汇总 | 反向完成顺序、某 Plan 正常失败 | 固定顺序输出，其他候选不被吞掉 |
| B 取消／缺陷 #12 | 主线程等待 future、worker 阻塞 urllib、线程池关闭、强杀 | 停止准入且等待有界，未知请求不假装未执行 |
| B 重启 | case 完成后、round commit 前后崩溃 | 已完成不重跑，学习事件不重复 |
| A+B 集成 | 幅度 Signal 晋升后下一轮双 Plan 并行 | 两 Plan 使用相同新快照，旧记录不变 |

使用真实 engine／adapter 的测试路径；脚本化 LLM 只替代模型决定，不替代被验证的提交、恢复、角色输入构建和 Registry 逻辑。主要复用现有 plan／signal engine、transport、magnitude wiring 和 P6 fault-injection 测试；实际测试类和运行时在实施时核验。

每次回归失败记录：原始请求／响应、失效层、同类历史故障、上下游影响、恢复结果、修复与反例。修复后回看整个 round 信息流，不以一个新增测试通过结束审计。

## 8. 实施顺序、文件与提交边界

建议先盘点并完成两项规格设计；工程上线先验收 B，使后续 A 的双臂试验可以受益；A 的新研究语义首次效果验证仍保留清晰控制组，不与未验收的并发变化混测。

A0 与 B0/B1 的只读盘点和设计可交错或并行推进，无需等待 B 全部完成才决定 ge3 是否有数据资格；共享规格编辑需协调。这里是日历安排，不授权启动额外 agent 或生产执行。A 的目标专属实现仍以数据 gate 通过为前提；C2–C4 与 C5–C7 保持独立提交、独立验收。

| 阶段／提交 | 主要工作 | 准出条件 |
| --- | --- | --- |
| C0 | A0、B0：可交错推进数据与共享状态盘点 | 数据 gate 状态、统计接口、两份采集 ledger、#11/#12 前置清单齐全 |
| C1 | 确认决策，更新 specs | 新目标、接口、晋升与并发边界无祖先冲突 |
| C2 | B1–B2：隔离、same-request guard、预算、去重与限流，并发度1 | #11 先于去重启用验收；三种同请求语义及账本回归通过 |
| C3 | B3–B4：单写入、恢复、停止 | #12 主线程／worker 阻塞／关闭路径验收通过，无在途状态伪造 |
| C4 | B5：并发度2 | 离线等价通过，实机另行授权并报告性能 |
| C5 | A1–A3：通过数据门的 ge3、挖掘、signal_library 目标统计及消费 | 旧方向路径不变，观察／评估分开去重，新目标契约一致 |
| C6 | A4：独立测量及 Fast 消费观察 | 输出真实增量／无增量／不足证据，尚不改晋升 |
| C7 | A5：已批准的目标适配晋升 | 正负反例、旧用途保护、恢复与下一轮可见性通过 |
| C8 | A+B 集成验收 | Fast→Slow→下一 Fast 及两个目标、并发恢复均有证据 |

规格落点：`spec/vision.md`、`spec/architecture.md`，以及 research 下的 `scheme_evolution.md`、`signal_evolution.md`、`evolution_signal_roles.md`、`plan_evolution.md`、`evolution_transport.md`、`evolution_control.md`、`evolution_runtime.md`、`evolution_dataset.md` 中实际受影响部分。按变更范围更新，不批量改无关模块。

必改落点还包括 [signal_library owning spec](../spec/src/stock_opportunity_agent/signal_library.md) 与 [signal_library.py](../src/stock_opportunity_agent/signal_library.py)：方向 stats 兼容、新目标统计空间、registry 读写、学习事件和 profile 聚合／消费。`plan_evolution._record_signal_statistics` 及 A0 找到的 Mining effectiveness／学习写入入口均须显式承载正确目标与评估协议，覆盖观察去重、目标评估去重和费用不重复。不能只改统计写入而漏掉 learned profile、检索卡或恢复读取方。

实现落点其余以第 2 节源文件为主；Raw Info 接口仅确有需要时修改。新增目标统计空间复用现有 registry 生命周期，不另建 archive、learning 或 promotion 引擎。

每个阶段先规格、再依赖顺序实现、再针对性测试；同步 progress 和 changelog，建立只包含当前任务文件的 checkpoint。集成前完整套件与 `scripts/lint_repo.sh` 必须通过，读取实际 lint 结果。

## 9. 实机实验、预算和效果判据

### A 的效果实验

- 先在固定 Registry 和同一 Plan 下隔离候选测量贡献，再评估整个双循环系统效果。
- 固定候选试验数量、样本、判据和停止条件，不以结果好坏决定追加哪组样本。
- V130 等已经用于反思的工件用于回归，不冒充独立泛化测试。
- 第一版仅对通过 A0 的 ≥3x 目标开展实验；ge10／extremes 延后，不从稀有样本上挑一个完美规则。ge3 也未通过时，不开展该目标实验。
- 明确方向保护、幅度改进和支持量要求。具体样本量、F1 容忍度、统计方法须在看到新结果前确认。

### B 的性能实验

- 固定候选、案例、模型、数据与资源上限，比较 1 与 2 个 worker。
- 只比较完成相同工作量的结果；候选提前研究失败导致少跑案例应单列，不能计为并行提速。
- 正确性要求硬通过；性能目标在 B0 测量后冻结。不得承诺整体 2 倍：proposal、critic、提交、Slow 和 provider 限额仍限制总速度。

### 授权与冻结

- 每次实机运行冻结代码、模型配置、目标协议、并发策略、数据和 Registry、attempt／费用上限。
- 旧 workspace 不原地替换代码或契约；暂停运行需匹配其原 revision。历史未提交 Slow 工件不当作 committed history 导入。
- 只有当前明确授权覆盖的调用可执行。本文件保存、离线测试与新实机预算是不同状态。

## 10. 回滚、停止与最终验收清单

发现标签泄漏、时点串扰、预算覆盖、未知请求重复发送、提前提交、错误 Registry 晋升或旧用途破坏时立即停止新实验并保留证据。先修正确性，不靠降低验证强度恢复运行。

研究无增量不等于系统失败：保留候选与反例、拒绝不合格晋升。性能无改善也不等于应扩大并发：保留串行模式，分析瓶颈。

回滚使用已知代码 revision 与匹配契约的新／原 workspace；不能回退已提交 pointer、删除已结算账本或覆盖原 Registry 来伪造无事发生。并发度回退是否可在原契约内发生必须预先定义，否则另冻运行。

- [ ] 当前数据是否足够支持每个幅度对比已有结论。
- [ ] ge3 的数据 gate 已通过；ge10／extremes 不在首版专属实现中。
- [ ] signal_library 与实际 Fast／Mining 读写入口齐全，物理执行和多目标评估分别去重。
- [ ] 新目标及分组不改变原标签，跨阶段投影和校验一致。
- [ ] 无标签提取、独立 holdout、旧用途保护通过。
- [ ] 幅度贡献被实际验证，assessed 状态与证据相符。
- [ ] 目标适配晋升已经确认；公共守卫与原方向路径未退化。
- [ ] Plan worker 状态隔离，快照一致，没有兄弟结果泄漏。
- [ ] 预算、in-flight 去重、限流与取消可恢复且审计完整。
- [ ] 缺陷 #11 在去重启用前关闭；#12 在并发度 2 启用前关闭；两份采集 ledger 并发恢复通过。
- [ ] 单协调者提交，完成顺序不影响选择与学习。
- [ ] 串并行固定响应等价、跨轮故障注入、全套测试和 lint 通过。
- [ ] 实机分别报告机制完成、流程完成、研究效果和性能效果。
- [ ] magnitude Signal 在下一 Fast 的实际请求中可见；两个并行 Plan 使用同一有效快照。

**本文件交付不代表上述项目已经完成。** 实施时按 C0–C8 逐项记录证据和未完成项，不把计划、测试记录或模型自述当作完整闭环。

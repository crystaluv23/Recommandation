# Slow 因子闭环：定义、入库、消费与追踪

日期：2026-10-02。用户已确认：通过结构、时点、来源与可执行测试的待观察因子允许入库并由 Fast 检索调用；效果检查转为持续追踪。本文是批准的设计方向及实施边界，**新的入库逻辑尚未实现**，不改变冻结 v168 的代码与历史产物，也不把历史拒绝记录改为成功。

## 当前链路及真实缺口

生产路径是受控 Mining controller，按 direction 与 `magnitude_ge3_v1` 分轴、按 hypothesis/discovery 种子工作；不是每个模型输出一条自由文本“因子”。候选经 spec → skill → tests 分模块物化，经完整 validator、独立效果评价和原子 Registry transition，下一 Fast group 冻结输出 Registry 后才可使用。Update 从精确旧版本及该版本的学习事件出发，生成 vNext。

当前存在三种耦合：

1. 技术可用与效果已证实共用 `accepted`。`record_candidate_validation` 要求 accepted 与 effectiveness promoted/accepted 一致；原子晋升再次要求 effectiveness.accepted=true。只删掉一个外层效果判断不能打通入库。
2. magnitude 在 paired check 通过后仍被显式变为 provisional，理由是 `fast_consumption_unassessed`。但未晋升的候选不能被 Fast 选择，导致消费验证依赖入库、入库又依赖消费验证。
3. 方向的版本级 learning ledger/profile 有生产写入；目标评价 `record_target_evaluations` / `target_support` 目前只有定义及测试调用，没有找到生产写入者。Fast 检索卡和冻结快照也没有 magnitude 目标证据摘要。存储接口存在不等于追踪闭环完成。

v167 的真实结果是 0 个新 Mining 候选、2 个已物化 Update 候选、0 个晋升；三个 Mining 种子技术终止。它既不能证明模型挖不出有用因子，也不能证明入库已经畅通。

v168 最终也没有新 Mining 候选：direction/magnitude 的 hypothesis 各 technical_failure、discovery 各 deferred_budget；Mining partial。Update 物化 revenue_growth_yoy:v3 后被 strict paired gain 门拒绝，两条其他目标技术失败；0 入库、Registry hash 不变。已完成 cycle 不能等同于探索成功。实际终态暴露动作专属结构、预算可用动作与纠错上下文的闭合问题，这一执行可靠性必须与放松效果准入并行处理。

## 因子的定义

因子首先是一个可复用的、时点合规的测量／证据提取能力：

`Signal = 测量定义 + 输入/检索契约 + 执行方式 + 证据规则 + 版本`

已有 `SignalSpec`、deterministic 函数或 LLM skill、不可变 fixtures、`SignalResult` 保持这个职责。因子不必单独判断一只股票会否暴涨。其输出是状态、解释、来源、覆盖及执行状态；数值还保留运行时计算的单位、公式和期间。需要把“测到什么”与“为什么可能有用”分开。

研究用途按独立 target 关联，不用因子名字猜用途，也不把 magnitude 的 positive 等同于股价上涨：

- direction：暴涨与非暴涨对比；
- magnitude：当前批准的 >=3x 与 2–3x 对比，包含 >=10x 个案；这只支持高低幅度研究，不能冒充独立 10x+ 区分能力。
- 同一测量可以服务多个 target。执行和费用计一次，各目标效果分别记账；不可把方向 surge_rate 当成幅度证据。

## 入库与效果是两个状态轴

技术准入必须满足：合法 schema 与版本、正确的目标/测量语义、可执行且有有效 fixtures、证据可追溯、无未来/标签泄漏、非纯语义重复、完整哈希绑定。模型声称“可执行”不代替真正执行。语义重复检查不能因文字不同而将旧因子重命名为新因子。

技术准入通过后，原子入库，Fast 可以发现并选择；效果状态初始为 unknown/待观察。少量样本不显著、正例 recall 不足、缺少 strict paired gain，作为效果记录，不再阻止技术有效的研究因子入库。效果评价报错与因子 contract 失败仍要分别记录：前者是未知效果，后者不能进入可调用库。

状态关系示意：

```text
候选草稿 -> 技术校验 -> 原子入库/可调用
                  \-> 技术不合格/保留诊断
                         入库版本 -> 持续评价 -> 支持/反证/不充分
                                  -> 下一次有依据的 vNext 提案
```

入库记录必须独立于效果记录，绑定 exact version、spec/skill/tests hash、技术评价身份和目标用途。效果 unknown 不是零效果；contradicted 也不应被改写为 supported。现有效果统计可以继续生成，旧门槛成为观察依据而非新准入门槛。这里不新增一套与 Registry 平行的执行引擎。

## Fast 怎样消费

在 cycle 边界完成原子入库；下一 Fast group 冻结 Registry、准入状态及截至该时点的学习摘要。运行中不注入新版本或后续 outcome。检索卡至少披露测量用途、技术状态、效果状态及有界版本级证据摘要；详细原件继续通过 catalog/content/provenance 读取。

待观察因子不应被描述成“已验证的暴涨因子”。选择器按当前需求和可执行数据判断是否调用，不设固定调用配额。执行结果进入 Reflect 与最终 Predictor 的证据拼装；一个 magnitude 相关测量只提供辨别幅度的证据，不能机械指定 3–10x 或 10x+。

不向盲预测注入事后案例、当次标签或 label-bearing experience。历史效果摘要若进入模型视图，必须按批准的版本/时间冻结策略做身份安全聚合，与当前案例及保留集隔离。

## 怎样追踪“有用”

复用现有 append-only learning ledger。每条实际使用记录绑定 signal_ref、案例/预测时间、输入指纹、Plan 选择原因、执行结果、覆盖和后续真实 outcome；同案例同版本同输入跨 Plan 重复使用不是多个独立观察。技术失败不进入研究效果计数；未调用不算负例；未成熟 outcome 保持 pending。

分三层报告：

| 层面 | 指标与含义 |
| --- | --- |
| 提取能力 | 正确性、可执行率、覆盖、失败类型、成本；说明测量是否可靠 |
| 目标关系 | direction 状态/结果矩阵；magnitude 分组及类支持/反证；样本与不确定性；说明测量与目标是否有关系 |
| 系统贡献 | 相同冻结输入的有/无因子消费比较，方向 F1 与 magnitude 混淆矩阵/macro-F1/TP 条件准确率；说明是否改善最终预测 |

“被选择”“产生正确结果”“与幅度相关”“帮助最终预测拉开幅度”不是同一个结论。因子可以先入库；收益主张仍需要独立对照。预测分布更分散本身不算改善，也不能让模型为了分散而强选高幅度。

目标评价必须接上真实 committed 使用或独立评价生产者，按版本×target×protocol×observation 去重；摘要再进入下一冻结检索卡和 Slow 方法视图。当前缺失的写入/披露链路应在实施中补齐。

## Update 与恢复

Update 只在明确的测量、检索、覆盖或反例问题上修改 exact vNext；原版本、旧 outcome 及效果记录不覆盖。参数变化需要声明为何改变，完整测试真实执行语义。未通过的 fixture 不能被模型修改为期望成功；合法定义变更与修复测试缺陷应有各自的明确契约。

新版本通过技术准入即可入库，效果重新标为待观察；旧版本的效果不得自动继承。保留版本选择与回滚入口，不能将新版本自动称为比旧版更好。失败的兄弟目标不丢弃已正确物化的模块或独立候选。

原子 transition、输入/输出快照、prepared/applied 恢复身份和 cycle pointer 保持。新 admission 记录必须纳入相同的 hash/恢复验证；旧 v2/v3 evaluation 按旧身份读取，禁止改写、伪造 accepted 或用新记录替换进行中的 transition。

## 固定 prompt 的职责

Mining：提出具体、可测、时点合规、目标相关的能力；对照反证；允许目前效果未知。技术可计算性不是研究相关性，宏大故事不是测量。不要要求每条因子独立高准确率，也不因少量样本无法显著而不物化。

Materialization：每次只产当前模块，显示所有真实函数/工具枚举与约束；已通过 spec/skill 不重新生成。Update：只看当前版本及相关证据，先核验缺失声明与可见原文，再修改局部模块。Predictor：明确区分机会与幅度，不要求价格证明，不为了平衡输出强选类别。

固定 prompt 可以改进，但要保存版本并检查与 parser/validator/修复权限一致。只改 prompt 而保留旧准入硬门，仍不能落实这次设计。

## 实施顺序与验收

1. 新独立 admission 记录及身份；Registry 原子入库/恢复接受技术准入，效果记录不被伪造。
2. direction/magnitude 和新因子/vNext 使用同一准入；去掉 magnitude 消费循环门，历史冻结协议保持可读。
3. 补齐目标评价生产写入、版本状态与检索卡披露；追踪按 committed cutoff 冻结。
4. 小规模真实 Slow：两个轴都实际探索；候选分别物化、技术测试、入库、恢复可读。允许明确无发现，不能将技术退出记为研究无发现。
5. 下一 Fast 实际选择/执行两个轴因子，轨迹保留 exact refs 和结果；新效果持续记录。幅度帮助需另有同输入对照，不用单次预测分散或增加调用数代替。

本轮交付是审计与贯通设计。上述新准入和持续追踪改造仍待实施及真实验证；不宣称已经挖出两个目标的新因子或证明 magnitude 收益。

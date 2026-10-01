# Fast / Slow 共同可靠性机制：设计与实施

日期：2026-10-01。阶段现状以 [context 审计](fast-slow-context-audit-20261001.md)
为依据，约束以 [共同阶段契约](../spec/src/stock_opportunity_agent/research/stage_contracts.md)
为准。本文记录实施内容；真实运行和研究质量验收另有产物，不能由单元测试代替。

## 共同机制的职责

系统运行时拥有数据来源、时间边界、标识、计算结果、预算、状态迁移和提交指针。
LLM 负责提出研究问题、解释已披露证据、形成判断和反思。每个环节的输出先作为
候选，经过所属模块完整校验，才成为可供后续阶段引用的产物。

共同契约统一五件事，领域校验器继续判断各自的内容：

1. **输入依赖**：这个阶段完成哪一个任务，必须读取哪些对象、哪一个版本。
   必要 context 包含任务约束与反证，不以字符最少为目标。
2. **披露规则**：模型当前看到什么、没有看到什么、如何读取遗漏的原件。
3. **检测规则**：结构、出处、PIT、数值、状态迁移，以及预算和运行进度。
4. **修复权限**：哪些错误可唯一确定地修复，剩余问题能改哪些具体路径。
5. **保存与恢复**：已接受产物与未接受候选分别保存，后续按依赖和提交指针恢复。

这五项没有形成另一个代理引擎。小型 `stage_contracts` 模块提供输入审计与完整条目分页；
现有 transport、领域校验器、repair、workspace 和 ledger 分工执行。

## “披露”为什么需要单独设计

披露不等于再加一份总结。它是模型与系统之间的知识可见性协议：

| 层次 | 模型看到什么 | 运行时必须说明什么 |
| --- | --- | --- |
| 目录 | 类型、标题、稳定引用、覆盖数量 | 总数、当前页、前后遗漏数量、下一页游标 |
| 工作视图 | 与任务有关的完整 brief 或精确片段 | 选择范围、截止时间、截短与遗漏情况 |
| 按需原件 | 明确引用的完整原件或 source span | 原件版本/出处、字符范围、读取上限 |

例如有 22 条反思，当前工作视图只给 6 条：它必须告诉模型还有其他条目，并给出
可浏览的引用目录；不能让模型把“没看到”当成“系统没有”。预览明确标记裁切，
不能用它证明逐字引用。读取后仍不足，与未读取、来源不可用分别记录。

本次 Mining 改动保留本地原件，限制初始 brief 页为 6 项/6KB，目录页为 12 项/5KB；
可按已披露 `item_ref` 读取 1–3 个完整条目，总量最多 16KB。超大条目与遗漏显式说明，
不静默切成伪完整证据。已有 source catalog/fetch/provenance、反思索引继续供其他角色使用。

## 各阶段的统一边界

| 阶段 | 工作输入 | 检测与修复重点 | 保存与下游消费 |
| --- | --- | --- | --- |
| Proposer | prior、父 Plan、实验摘要、可读经验目录、约束 | Plan schema、允许的 Basic Info 菜单、身份匿名化、内容去重 | 每个接受的候选 Plan 单独 staging；后续复用 |
| Initialize | 初始研究 skill、Basic Info 投影、程序计算的锚点 | 证据坐标、字面数值、时间边界；禁止把运行时锚点当成待查问题 | 接受初始 state；Basic Info 原始投影保留 |
| Signal retrieval | 未回答需求、适用性 context、Signal cards、调用上限 | 只能选择披露的 ref；区分回答需求与补充研究；不重复未变化的调用 | 选择记录与待重试请求分别保存 |
| Signal execute | 已选 spec/skill、其来源投影、as_of | literal evidence、数值/PIT、分类与 unavailable、既有 Signal schema | 合法结果保留，错误单元隔离；不吞 provider/control 错误 |
| Reflect | prior state、当前 batch、typed need transitions、相关目录 | 增量 patch、引用归属、准确需求残值、resolved/retained 冲突 | 局部合并后完整校验；state delta 与 evidence 一并进入轨迹 |
| Predictor | 运行时拼装的 typed evidence/state evolution/有效 state/baseline | 盲态、固定预测定义、可核验理由与分类 | 先固定 prediction，再揭示 ground truth |
| Posthoc | 原预测、必要 source context、程序真值 | 反思引用闭包；技术失败不得转成研究因果结论 | 原反思不可改写；brief/item/source ref 可向上引用 |
| Critic / Round | 确定性指标、紧凑案例诊断、下层 briefs 与可读原件 | 跨案例/跨 Plan 推论必须有 source；配对条件不满足不能声称指标因果改善 | 原 case/Plan 反思与新作者条目分开保存 |
| Slow reflection | 尚未消费的反馈单元、测量契约、先前方法记录 | 条件/总体/分母、append-only、读原件、失败不消费反馈 | 新反思保存后才推进消费位置 |
| Mining | 本轴标签、证据 manifest、工具结果、相关 memory、预算 | typed action、真实返回内容、来源/时间/测量条件、重试/预算 | ledger 保存每一步；候选/无模式/预算不足分别落盘 |
| Materialization | grounded candidate + cited evidence，再依赖已接受的 spec/skill | spec→skill→tests 分模块校验；分类 fixture 与技能一致 | 已接受模块在重试中复用；合成后完整候选 gate |
| Update / validation / promotion | 一个稳定 Signal、induction 观察、可变字段；独立 check | 不变定义/tests/版本权限、真实来源、fixture/效果门、匿名化 | staged/validated/promoted/used/benefit_confirmed 不混同 |

最终 Predictor 的 context 是前面合法产物的结构化组装：Basic Info 投影、采用及反对证据、
各次 state 变化、最终有效 state 和计算锚点。不能只留最后 state；同时必须标明被移除或
替代的状态，避免把历史判断当作当前有效判断。现有 append-only assembly 的证据闭包保留。

## 程序检测的能力边界

检测分三层：

- **可严格判定**：JSON/schema、必需依赖、引用是否存在、literal quote、精确计算值、
  PIT、枚举/上限、版本一致性、状态迁移、patch 权限。
- **可识别风险或停滞**：重复无变化请求、不可用证据、动作预算耗尽、前置条件不足、
  部分文本边界模式。命中后给出有界纠正机会或显式 defer；不能无限重试。
- **必须作研究判断**：证据能否支持经济推论、反证是否充分、因子是否有效。
  程序规则不宣称解决所有未知 corner case；需要原件审阅及独立测量。

关键词只是第二层启发式。v154 VSAT 的 `expectations` 复数曾被时间词表遗漏，说明
启发式也可能误拒。增加普通词形及真实回归样本，同时保留未来事实限制；不能用
“检测器通过”替代内容正确性。

## 修复与保存的顺序

```text
输入依赖 / 标签 / 身份检查 → 模型原始响应留存 → L0 JSON 候选解析
→ 所属模块校验 → 适用的确定性修复 → 全量再校验
→ 保留机械修复进展与剩余问题 → 有界、typed 权限的 LLM 局部 patch
→ 完整合并校验 → 合法产物 checkpoint → 依赖阶段继续
```

混合错误不再要求“整份输出只包含机械错误”才启动修复。可以先去掉唯一确定的重复项、
恢复运行时已经指定的精确需求，再把剩余证据语义错误交给 LLM。中间候选不是合法 state；
只有完整原校验器通过才接受。LLM 纠错的基线是最新候选，权限也根据新问题重新生成。
visited-state 与最大修复步数阻止固定点死循环。

保留未回答需求但又新增“已解决”的冲突，会暴露需求和 resolved 两个路径。只有领域
校验器明确判定新 resolution 没有本轮直接回答依据，程序才允许删除它。存在直接回答
或多义性时交由有权限的局部纠错，不从错误散文推导写权限。

无法修复的普通局部问题留下诊断并隔离该单元；provider、暂停、取消、成本预算及
其他控制面异常继续传播，避免错误重启或伪造正常产物。

## 当前实施和真实验收

已实现共同阶段输入依赖 metadata、完整工具目录返回、有界可读 Mining memory、
非负动作预算、单份 span、混合错误的机械进展保存、typed need/resolution 权限和
普通时间词形回归。仍需用真实链路观察这些机制是否能收敛，以及修复结果是否保留
研究内容；不能只检查调用成功或 schema。

v159 验收入口替换旧 harness，使用生产角色和 exact-request transport/ledger。
从批准的开发 split 预先选择全局 Label Store 可覆盖、PIT 锚点与叙事来源可用的案例，
冻结全局 Raw Info 原件引用/标签文件/Registry 的身份（不复制全局 oracle）；生产 v8 固定的 16 Anchor + 8 Random（原四档配额），两个真实
Proposed Plans，独立 Discovery 16 案（8 control、4 2–3x、2 3–10x、2 10x+）。
后者同时支持 direction 两侧的类别覆盖和 ge3 两侧各 4 案的既有效果检验下限。Locked Test 不读取。未覆盖日期明确记录，不
通过修改日期或真值填补，也不在看到模型结果后换样本。

验收包括：每种实际阶段的保存请求与响应、目录遗漏可达性、原文引用、状态迁移、
原预测与反思一致性、Signal fixture/候选 gate、Fast/Slow 提交指针，以及固定分母上的
F1/混淆矩阵。合法 no-change/defer 会保留理由；没有执行的分支不能宣称已验收。
该诊断 cohort 与 v154 不同，F1 不作配对提升比较；系统执行、研究分数和收益证据分别报告。

预检还识别到同一五个历史交易日的 provider 价格与标签档案存在数值差异。
这类调整/舍入差异记入 `baseline_comparisons`，不把事后标签价格送入盲预测，
也不以数值逐位相等为理由删除固定 Anchor；标签和时间边界均保持原合同。

另有真实身份反例：[Aris Mining 的当期 SEC 文件](https://www.sec.gov/Archives/edgar/data/1964504/000162828025012451/arismining-2025aifv4.htm)
说明美国股票当时为 ARMN，而同一 CIK 下已有价格请求使用 ARIS。
相应原件及内容 hash 记入 [来源审查](raw-info-source-integrity-review-20261001.json)，
在模型调用前将需要该未证明身份价格来源的诊断案例标记不合格，保留原因；不改历史原件
或标签，不声称已修复整个历史 ticker resolver。

按用户要求删除不再使用的旧目录 helper 和 last_read_span 缓存字段；所有读取统一由
last_action_result 返回。结构化 fact read 也补齐这个返回通路，并以实际 fetch→read→下一
次 model view 回归验证，防止删重时连正确结果一起隐藏。

## v159 实际内容审查后的边界补齐

[v159 审查记录](v159-live-content-boundary-audit-20261001.json)保留 90 个请求、
87 次外部尝试和 4 个完整案例。发现上游 Initialize/Signal 执行未匿名化，
以及 final assembly 将约 40KB 已披露 Basic Info 再裁成约 8KB；这轮已主动
中断，两个提交指针仍为 0，不接受其部分分数作为完整或盲态研究质量结果。

修复将所有 Fast 案例调用置于线程隔离的身份出站作用域。精确已知身份在真实
transport 边界替换为请求内的不透明 token；输出仅还原该请求已经提供的 token，
再进入原引用/状态/patch 校验器。原件、projection ID、hash 和反思图不改写；
缓存仍保存真实模型视图。独立 Slow Signal 执行也由 source owner 进入相同作用域。
普通业务词不因自动派生单词品牌而丢失。最终 Predictor 保留所有上游已经披露的
完整投影，仍执行实际 token/成本预算，不再用第二次裁切伪称证据闭包。

同一审查发现 Kinross 残留的 Q3 实际结果和从预测日至期限结束的公告问题。
季度完整实际结果在季度最后一天的午夜尚不可得，forward horizon 的实际公告也
不属于截止日证据；补充这两种已有时间规则的覆盖，同时保留截止日前披露的
未来 guidance/schedule 例外。逐字段 LLM 纠正承担语义改写，不由程序编造答案。

后继验证继续使用 v159 的同一冻结输入清单、标签和初始 Registry，绑定新提交代码。
这样匿名化/信息保留修复不会通过事后挑选样本获得表面通过。报表头部/历史财务
条目主导部分工作视图，以及将天然接近 50% 的距 2x 比值当作独立预测依据，仍
需要在真实后继的取证、预测和反思中审阅；离线修复不证明经济推论正确。


## v160 的真实内容复核与后继边界

[v160 内容审计](v160-live-stage-content-audit-20261001.json)记录 59 份请求、56 次
外部尝试和 2 个完整研究案例和 1 个显式技术弃权；Fast/Slow 提交指针均为 0，中断的在途调用已在
独占执行锁下结算。两种技术失败分别是：完整 Predictor 请求需 88,449 的预留，
但仅剩 85,953；一条明确“不要求预测日之后结果”的问题被时间检测误拒。

修复改为按同一真实 Predictor prompt/payload 与出站投影估算预留，逐阶段重新
装配当前证据；普通研究保护 Predictor 预留加已有收尾空间，终止反思也保护
Predictor 预留。固定限额、样本、标签和已付费批次不变。时间检测只忽略封闭的
尾部否定限定，保留原句，并继续独立拒绝主句中的真实未来事实请求。

内容检查还发现 Kinross 将 16.21 到 24.37（约 1.50x）描述为约翻倍；两案例把
接近翻倍阈值一半当成独立负面证据。计算卡原先只在上游出现，没有进入最终
Predictor。现在将引导计算卡和反思通道取得的文档/计算产物一并拼装，计算卡也
进入 posthoc 视图；Predictor 指令明确阈值距离属于定义，趋势数字须使用计算卡。
这些接线和指令修复不等于语义错误已全部消失，后继实际响应仍须逐项检查。

已有完整案例全部为非 surge，不能据此接受 F1 或宣称研究改进。后继 v161 使用
逐字相同的冻结输入清单和相同原始 Registry，不以本轮结果重新选择样本。

离线验证：1,247 项全量测试、lint 和 diff 检查通过。重放 v160 未发送的真实
Predictor packet，新估算与实际预发 wire 预留同为 88,839；修复层追加的增量
指令使用同一常量，避免预估漏算。该重放没有外部调用，也不证明预测质量。


## v161：恢复保真与跨阶段语义边界

实际保存 21 个案例，其中 19 个研究完成、2 个因真实输出猜测身份而技术弃权；231 次完成请求后 SSL EOF 中止。随后恢复尚未发出新请求即失败：冻结费用整数 100 被反序列化为 100.0，改变 canonical hash。修复保留已接受 JSON 数值类型，构造器仍拒绝非法值；真实旧契约离线加载/重复 freeze 原 hash 与原字节一致。它覆盖所有合法整数与浮点费用上限，不涉及某个 run 的硬编码。

审查还发现最终 Basic Info 卡丢失 document_id/available_at、缺少明确 prediction_time，导致陈旧的“目前”语句容易被理解为截止时仍成立。装配现在保留上游原始时间与引用字段，不为遗留缺失值补造日期。输入正确不等于经济语义必然正确，真实阶段产物仍须检查。删除近期价格/翻倍阈值比率的冗余展示及无用计算标签，保留原始均价、阈值、收盘价、距离工具与标签定义。

对反思建议强制要求量化翻倍路径的问题，在动作入库和 Plan 指令消费端共用同一有限契约检测；公共反思生成契约亦明确披露。仅允许修复出错 brief/detail，事实/假设及正确兄弟项保持原值。测试覆盖不同强制表述、否定、可选估值、普通收入量化和相邻句反例。该词法检测不声称处理所有意外语义；复杂研究正确性仍通过内容审查与独立评价检验。历史重放脚本的模型答复为明确标记的脚本化新 proposal，其 H_analyse 使用当前默认契约；历史父 Plan 和证据不改写。

详细诊断见 [v161 内容审查](v161-live-stage-content-audit-20261001.json)。Fast/Slow 指针仍 0/0，部分样本得分不作为完整 F1 或收益验收。下一版本保持同一冻结 cohort 与原始 Registry。

## v162：共同边界在真实 Fast/Slow 上的缺口与修复

真实完成两条 Plan 各 24 案并提交 Fast round 1，Slow cycle 指针仍 0。
469 次外部尝试（462 completed、6 failed、1 interrupted；以 JSON 审计为准），
两条 Plan Binary F1 均 .64，幅度 macro-F1 .089/.133。技术排除 5/6 案，
留在每条 Plan 的固定 24 案评分分母中；没有以成功子集重算正式成绩。
详见 [真实阶段审计](v162-live-stage-content-audit-20261001.json)。

这次并非统一修复模块没有被调用，而是它的上游输入和领域检测不一致：

- **必要 context**：18 个财报窗口全部位于隐藏 XBRL 头部，正常财务正文没有进入
  同一预算下的 Basic Info；Slow 原文读取也重复获得隐藏头部。数据层现在统一非可见
  区间，选择窗口前排除；投影复用同一规则并保留原坐标。Slow 目录复用已有数据卡的
  正文起点与章节索引，精确原文读取仍执行模型指定坐标。
- **披露**：明确给出原始尺寸、正文坐标、章节总数与已列出的章节；目录只用于定位，
  实际读取才建立证据。未读、片段未覆盖、已查但不足不能推导“事实不存在”。
  Predictor 继续结构拼接此前披露的 typed 产物，而不是只用最后 state。
- **检测**：原市场数据缺失正则跨越否定/转折，合法原文和合法局部修复都被拒绝。
  改为有限的主语—缺失谓词关系，保留真实联合缺失断言检查。未来预期允许截止前
  estimates/consensus，独立的未来发布时间与 actual/results 仍拒绝；已披露的未来
  发布日程仍允许。词法检查不是语义证明，PIT resolver 是事实可用性的最终边界。
- **修复**：五个真实市场数据反例的 brief/detail 权限本来正确，不应扩大权限或
  让模型改写兄弟项。纠正检测器后，原始有效内容可以保留。三项数值 Signal 的旧
  LLM 定义仍在 Registry 中，正现金流被错误当成烧钱；显式启用已有确定性函数的
  新版本，不让修复模型猜一个“更合理”的数值。
- **保存与恢复**：两次 SSL EOF 在原契约/原工作区续跑，已验收案例与失败请求的
  精确缓存保持。发现 Mining 实际 wire 泄漏 CIK/域名后停止诊断并保存 Fast 提交；
  在途未知发送按原控制面保守结算。身份投影接到 Mining 真实调用边界，匿名句柄
  只在执行前恢复；原文、引用、哈希和财务数值不改写。

[零外部调用重放](v163-source-boundary-replay-20261001.json)验证同一原始财报
预算 36,000 字符下的新窗口可见真实经营收入、16 个已保存 Mining 请求的统一身份
出站边界、5 个原始否定承认文本及句柄回读。52 次原始数值使用在 48 条轨迹上的
[确定性重放](v162-structured-signal-replay-20261001.md)验证旧版烧钱/跑道的差异。
[明确迁移清单](v162-signal-migration-plan-20261001.json)把源 Registry v6/hash
绑定到新 v7/hash，三项执行器修正及其余 modality 补齐均有版本记录；18 项能力审计
全部通过。新 workspace v163 保留完全相同 issuer/date/labels/source 文件，显式绑定
新 Registry，不修改 v162 历史。以上不证明 F1 增益。

内容复核仍发现 Critic 把整体评分的 technical negatives 描述成成功研究，并把
幅度类收缩归因于 Plan 未提示完整类别，忽略固定 Predictor 已有类别契约。
引用链能程序验证，因果归因和研究价值仍需真实内容审查/独立评价；不能再加一条
关键词就宣称处理所有 corner case。全 Slow materialization/validation/Update/
commit 与后继 F1/幅度质量仍待真实测试，当前目标没有验收完成。

### 2026-10-02：v163 终态审查与共同边界补齐

用户明确小规模验收的 Binary F1 下限为 0.60；固定样本、标签、分母和晋升规则不变。
[v163 实际内容审查](v163-live-stage-content-audit-20261002.json)记录 Fast=1、Slow=0，
505 次外部尝试、501 完成、4 失败，结算费用 1.91115288。进程因 SSL EOF 自行退出。
Plan 1 完整 24 案、Binary F1=.64、幅度 macro-F1=.133；Plan 2 只完成 21/24，
metrics=null，不能将部分样本分数作为验收。Round reflection 因只有一个完整 Plan 合法跳过。

本次按机制而非 issuer 分支补齐六处边界：

| 边界 | 共同规则与落点 | 验证与局限 |
| --- | --- | --- |
| 身份出站 | StructuredRoleClient 在没有 case scope 时使用显式 guard inventory；预估与实际发送相同，响应只还原本次给出的 token；删除 Mining 单独包装 | 两份真实 Slow 反思 wire 原先含 padded SEC CIK，新的零网络预发均遮蔽；原件/hash 不改写 |
| 跨行路由 | 校验器按精确行和 Signal 身份授权冲突恢复；唯一 full owner 保留，其余保留为 context；无唯一 full 时全部冲突行只作 context | 精确 corrected 输出零修正通过；混合缺陷只修融资行，保留已完成机械修复及全部四项选择 |
| 预算终止 | 下一次路由预发无法容纳时，用已反思的付费 batch 尝试一次 terminal reflect；清空过期 selection intents，保护真实 Predictor 预留 | 原 Impinj state/源文档重放：剩余 74593、请求 70065，可发送；离线 decision patch 仅证明完整校验/状态保留，未证明 live 成功 |
| 反思工作单元 | 默认至多三条完整反馈，lesson slots 随工作单元规模限制；未处理条目保留 pending，沿用既有 immutable slow_memory | 避免只按输入 64KB 判定能否输出；5000-token 语义质量仍需真实审查，不保证所有复杂响应均无错 |
| 原始读取 | 数据层共同可见性区间与 exact raw window 求交；报告可读性和下一处正文坐标；头部不计已探索叙事 | 不自动改 offset，不改 raw hash；控制器内按 document id/hash 缓存索引/cards；去掉重复全动作菜单 |
| 事件主体 | Signal batch 显式给出同一目标 issuer 的可逆共指 aliases，预估和执行共用 constructor | retrieval owner 不等于事件 actor；客户/顾问/承销商关系按 skill 判断；引用可校验不能替代经济语义判断 |

[共同边界重放](v164-shared-boundary-replay-20261002.json)和
[实际预算重放](v164-terminal-budget-replay-20261002.json)均零外部调用。
尚未解决的 live 质量问题保持显式：基准距离被当成独立负面证据、禁止未来观察与
已有历史价格确认混淆、融资主体归属、正例幅度均落在 2-3x。最终 Predictor 仍按结构
组合 Basic Info、运行时基准与计算、Signal 证据、state deltas 和 effective state，
不能只用最后 state；披露规则保证未读/省略条目可追溯，不能把省略当作不存在。
后继测试必须在新代码 checkpoint 上冻结相同 cohort 与 Registry v7，完整检查真实
Fast/Slow 内容和指针，不能把离线重放、pending 保存或 F1 单项达标当成整体完成。

1,267 项全量回归及 lint PASS。v164 已准备逐字相同 input_manifest（sha256 f0261bf21ab1bc21cde69e9ca8e5cdf88f13ca055bd2aa453bc703222980b694），初始 Registry v7/hash 866d821e51aa50a3272d2f7d0c2562faabf121097fc5ced75b70c527388b24d0；实际原始 filing header read 重放均为空可读窗口，下一正文坐标 138838。完整 live 验收尚未完成。

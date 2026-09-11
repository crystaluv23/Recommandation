# 信息方案自进化：行为审计与 MVP 修复执行方案

状态：待实施。本文是可直接交给 Codex 的执行任务，不表示修复已经完成。
审计基线：`63057b5`（文档），运行代码 `fed00ec`；真实完整运行 V18
冻结于 `74a7206`，最终代码的定向真实验证为 V19-validation-b。
本次仅审查代码、规格、已有请求和产物；没有修改运行逻辑或新增外部调用。

## 给执行 Codex 的任务

请在 `/Users/l/Project/Recommandation` 按本文顺序修复自进化流程。
目标是在保持 Fast/Slow 可恢复执行、固定评估和严格晋升门槛的前提下，
让反思、未满足研究需求、数据及执行故障真正驱动 Signal 挖掘和更新。
先更新所属模块 spec，再实现最小修改，最后按本文验收并提交 git checkpoint。
执行前核对最新 HEAD、AGENTS.md 和当前文件；本文行号是审计时定位，不能当作补丁。
用户进一步明确优先 MVP：首批不实现自动 meta 分页、新任务队列、通用 patch 引擎、
全局供应商配额平台或新的多阶段代理。函数级修改见
[MVP 代码施工单](information-evolution-mvp-code-actions-2026-09-11.md)。

用户已批准真实外部执行，该授权不因换任务而重新索要；沿用并核对已有模型、
数据授权与预算边界。不要启动无界调用，不要因“验证闭环”而提高预算、
购买新供应商、打开 Locked Test、修改标签、降低样本下限或放宽晋升条件。
若确有新的外部授权范围或费用需要用户决定，应先把本地修改、测试和精确执行
配置准备好，再只询问新增部分。额度不足属于可恢复数据依赖，不是 Signal 无效。

不要为了有产物而强制生成或晋升 Signal。必须验证正向候选路径，也必须保留有依据
的无候选、无变化、候选不通过。不能用 `exit 0`、完成指针、JSON 合法或引用合法
代替信息消费和研究行为的验证。

## 已确认的问题和边界

### A. 挖掘并非完全没有启动，但反馈没有形成完整需求输入

V18 普通 Fast/Slow 完成指针为 1/1。H1 返回不提假设，因此 H2/H3 没启动；
另一路 E1 实际处理 8 个案例，E2 实际比较固定归纳组的 4 个案例，返回
`{"decisions":[]}`。独立验证组没有作为 E2 归纳材料。不能把零候选解释成
完全未运行，也不能把 E2 的空数组解释成已经充分研究所有方向。

V18 正式方案 24 个案例中，20 个以 `no_signal_match` 结束，其最终状态仍有
118 条非空、按文本区分的 `next_information_needs`。这不是 118 种独立概念，
但每条都有具体来源。实际 `capability_backlog.json` 的 `signal_need_items=[]`；
只有 5 组供应商错误/无数据，累计 15 次。

代码原因：`plan_evolution.py:1071` 默认只从 bootstrap manifest 注入 Signal needs；
`data/resolution.py:298` 聚合 Resolver 的 `data_gap`，不提取普通轨迹的研究需求，
也不聚合 Signal 执行失败。结果是技术报错进入了 H1 的显式需求清单，而大量真正的
研究问题没有进入。来源包括订单在六个月内兑现、合同负债/RPO、投产日程和独立采用佐证。

### B. 完整反思已保存，但模型输入固定抽样

`evolution_core.py:4679` 的 `PlanMetaMemory.model_view()` 每类 assessment
只选一条代表案例，再检查字符预算。V18 完整 meta 序列化约 105,877 字符，
H1 视图只有 18,588 字符、4/24 案例；低于默认 48,000 字符仍省略其余案例。
Fast Proposer（`evolution_plan_roles.py:1594`）和 H1
（`signal_evolution.py:3818`）均使用该视图。

纵向总结确实在请求中，不是所有洞见都丢了。本轮没有适用的横向比较，顶层汇总字段
为空、具体方向藏在 vertical，容易把“不适用的一层”误读成“没有研究方向”。
H1 实际解释主要围绕获取失败，没有逐项说明反思中的方向为何不能形成假设。
这是输入覆盖和结论可审计性问题，不能宣称只要改成完整输入必然产生好 Signal。

### C. 电话会“缺数据”首先是响应及缓存错误

六个电话会 provider error 实际在获取 `EARNINGS` 辅助元数据时就收到额度限制信息，
尚未真正查询相应文字稿，不是已证实的文字稿覆盖缺失。HTTP 200 错误对象被记为
fetched 并写入成功缓存，
后续 cache hit 重复读到错误，再在 client 层抛出泛化 DataSourceError。

定位：`data/sources/state.py` 的 `ManagedHttpTransport.get_json()` 先读缓存，
可选响应检测器未形成所有路径的强制边界；`data/sources/alpha_vantage.py:237`
在 transport 返回之后才检查 Error Message/Note/Information；
`research/evolution_control.py` 组装实际 transport/adapter。
六个相关缓存键共被记为 6 次 fetched、2 次 cache_hit。
供应商错误正文可能回显密钥：修复、诊断及缓存整理不得复制原始错误正文到报告或日志。

### D. SEC 获取范围与研究问题不匹配

部分风险披露请求要求 10-K/10-Q，但实际发行人的披露使用 40-F/6-K。
另一个历史案例的 `submissions.recent` 已全部晚于预测时点，历史分页索引却有相关区间；
当前获取只查看 recent，因此返回无数据。`data/acquisition.py:135-152` 及
`data/sources/sec_edgar.py` 是主要入口。

这两类都不能靠增加供应商或放宽历史时间限制解决。具体表单请求与“年度/中期报告、
风险、订单”等语义需求也不能静默混同。

### E. 文本引用通过，不等于包含可用的财务事实

最终 `fed00ec` 已让 queryless JSON 窗口看到较新记录，但 V19 的财务窗口仍会从
`{accn,end,filed,...,val}` 开始，丢失其所属指标名/单位，再接上一大段旧 PublicFloat
历史。模型只能报告“某日期有某个数字”，不能可靠知道数字的含义。
`evolution_core.py` 的 `_query_relevant_excerpt()`（约 5832）仅按最新叶记录
位置截取连续字符，是语义上下文不完整的根因。
V19 的 22 条观察证明引用及提取格式通过，不证明 22 条都有研究价值。

### F. 软 Signal 有较高 unavailable，但原因不能混为一类

V18 正式方案共 240 个 Signal 结果，其中软 Signal 86 次，35 次 unavailable；
这些 35 次 Resolver 均返回文档，但“返回文档”不证明具备完整测量依据。
其中 8 次是明确技术失败（指引 3、融资 3、客户集中度 2），其余 27 次是当前模型的
domain-unavailable 判定，还需逐条核对全文、检索、投影、解释。

商业化状态 15 次执行中 12 次 unavailable，有成熟企业不适用、尚未商业化、
缺少可见证据等不同解释。不能把这 12 次全部归为数据层缺失，也不能自动改 polarity。
目前技术结果正确地排除于正式学习，所以账本是 232 条；但它们没有进入结构化修复
需求。Update 新执行的样本在 `signal_evolution.py:2324` 仅按 value 分桶，
可能再次把技术失败纳入 unavailable 归纳样本。

### G. Update 虽生成 v2，但没有兑现声称的修改

V18 `customer_concentration:v2` 与 v1 的 skill 字节相同，执行参数相同；
实际变化是原有三个检索 query 和 1095 天 lookback 被遗漏，变成默认单 query、
无 lookback。理由却声称收紧了定义、证据政策和 skill。
部分诊断认定现有结果有来源支持，总体理由却用涨幅标签把它归为抽取错误；
政府客户测试的负面预期也没有与诊断形成一致的修改解释。

更直接的根因是 `_candidate_arguments_schema()` 的 `raw_retrieval` 仅允许
`source_types` 且禁止其他字段，主动排除了当前 `SignalRetrievalPolicy` 已支持的
query、lookback 和比较要求。必须先修候选契约，不能仅责怪模型遗漏。
`validate_signal_update_candidate()`（`signal_evolution.py:1623`）验证形状和
不可变字段，但没有“诊断—实际改动—回归测试”的一致性检查。
V19 实际 4 个 fixture 中 3 通过、1 状态不符，拒绝是正确的；不能改期望来造通过。
旧期望用于回放该不变候选，不作为所有新版本的黄金语义；新候选仍须依据明确的
测量定义、诊断和独立证据制定并通过测试。

商业化更新还遇到另一处断点：因 repeated_explicit_misleading 被选中，更新取样却
只找 wrong bucket。新执行得到 0 wrong/11 unavailable/1 neutral，因而没有启动
诊断。反思认为误导，不等于重跑一定得到方向错误。

### H. 数据修好后，旧的受阻结果仍可能抑制新工作

H1 工作指纹（`signal_evolution.py:2808`）没有绑定相关 Raw Info 内容及获取
就绪变化；总 Slow 的指纹有数据哈希，但没有被上述 H1 跳过条件消费。
同一来源类型补齐电话会后，H1 仍可能命中旧无假设结果。
`:2826` 还将 technical_failure 与实质 no-hypothesis 一并去重。
Update 指纹（约 2385）只使用模型类名，没有使用已有 role `work_identity`。
这些代码路径的问题已确认；不是声称 V18 已实际发生了一个后续恢复失败周期。

## 执行顺序与最小修改

### 0. 固定回归基线和证据清单

创建本任务独立审计产物，读取 V18/V19，不覆盖其请求、响应、完成指针或 Registry。
先保存：24 案例、240 结果、86 软执行、35 unavailable、8 技术失败、232 学习事件，
以及 118 条需求的来源映射。使用现有 `execution.status` 分析，不匹配错误自由文本
来区分技术/领域失败。运行现有测试建立当前基线，不把历史 649 的数量当作本次通过。

为 35 个 unavailable 建立逐条审计表：完整本地 PIT 文档、Resolver 选择、投影实际
可见片段、模型回答、验证状态、是否有足够事实、失败阶段及证据引用。
已收到文档但缺事实应保持 unavailable；无法判定是否足够的项明确标为待审，不能算
成功或缺失。先重放本地选择/投影，再只对变化的必要模型请求做有界真实复验。

### 1. 先修响应、缓存、额度和历史获取

所属规格：`data/sources.md`、`data/resolution.md`、`data/raw_info.md`；
代码：`data/sources/state.py`、`alpha_vantage.py`、`sec_edgar.py`、
`data/acquisition.py`、`research/evolution_control.py`。

- 复用现有 provider 边界，在成功缓存写入和缓存命中消费前执行同一响应验证。
  provider 适配器识别自己的错误信封/成功结构，返回通用的成功、额度延迟、
  权限/配置受阻、临时传输失败、结构无效、有效空结果；核心流程不枚举公司或句子。
  HTTP 200 不等于成功；未知结构不等于有效空数组。
- 使用现有配额及异常机制传播类型和恢复条件。已知额度错误停止该依赖的无效重试，
  保留其他可用来源/独立工作；重置时间未知时明确未知，不编造保证或持续重试。
  数据延迟不能变成研究拒绝。新错误对象不进入成功缓存，受污染旧缓存按键失效并
  记录脱敏原因；保留已有有效缓存和不可变运行证据，不清空整个目录。
- 复用统一脱敏规则，错误正文在任何持久化前处理；用伪密钥测试回显情形。
- 从官方 submissions 返回的历史文件索引按预测窗口选择有限分页；文件名、域名和
  请求数继续受已有来源授权和预算约束。合并去重 recent/history，原始披露的
  available_at 仍必须不晚于 as_of，不用现在的抓取日期冒充当时公开日期。
- 将一般研究请求表达为年度/中期报告等能力，由实际发行人的表单清单路由；
  覆盖 10-K/10-Q 及适用的 20-F/40-F/6-K 等已知表单家族。若请求明确只允许
  某表单，保持限制并报告不适用，不静默替换。别只给这次几个 CIK 加例外。
- 获取失败记录必须有可恢复条件，不能在依赖已恢复后仍永久复用旧失败。
  backlog 的 resolved 必须由相同公司/窗口/需求的实际成功证据或明确替代依据支持，
  不能仅因为 source_type 名称已注册就宣告解决。

本阶段不新增付费供应商。先修复已有来源的可用性；确实持续缺覆盖，再单列可选扩源。
新闻新鲜度/持续通知不作为此次挖掘修复的必要工程，不顺带实现完整监控系统。

### 2. 修复证据表示，并验证已存在数据能被使用

所属规格：`data/resolution.md`、`research/evolution_core.md`、
`research/evolution_signal_roles.md`、`signal_library.md`。

- 对结构化 JSON 使用可复用的结构选择，保留指标概念、单位、期间、申报及数值的
  关联；按当前需求保留最新期和必要比较期，所有片段绑定原文路径/offset/hash。
  可以分多个原文片段，不得凭模型生成替代原始财务事实。不要继续用“最新数字附近
  截 N 字符”代表完整财务证据；不要求每次把整份财报发送出去。
- 对自然语言文档复用现有 query/evidence 排序和多文档配额。若相关句被截断或命中
  边界，提供一次有界的邻接窗口扩展/替代完整原文片段，再走同一验证器。
  不放宽 exact-span/PIT，不无界增加上下文。
- 共享 Signal batch 明确每个 Signal 的 eligible 证据范围；缺项、串用其他 Signal
  证据或结构错误只纠正失败项，纠正请求只带该项需要的证据和反馈。保留成功兄弟项，
  提前按真实请求估算一次纠正余量；不足则 typed pending，不强行构造领域结论。
  这覆盖 V18 的遗漏结果、跨 Signal 引用和纠正预算耗尽等共性问题。
- 对第一次 domain unavailable 且证据仍截断/需求比较期未满足的情形，允许一次
  通用的本地补查或已授权获取。只有证据输入指纹变化才重新执行该 Signal；
  对同一坏输入不循环重试，不重跑已成功的兄弟 Signal。
- 区分检索/适用性/事实不足/投影不足/执行失败；复用现有领域值与 execution status，
  细节放在诊断元数据，避免为了每种错误增加一种 SignalValue。

验收首先要求恢复已确认丢失的事实上下文；对于真正没有比较期、没有相应商业化事件、
或尚无法判断的案例保持保守，不以 unavailable 比例降为零为目标。

### 3. 接通普通 Fast 的需求与故障反馈

所属规格：`research/plan_evolution.md`、`research/signal_evolution.md`、
`data/resolution.md`、`research/evolution_core.md`。

- 用一个纯函数从正式已提交轨迹提取未解决需求，给每条需求稳定 need_ref、
  原文、Plan/round/case/阶段来源、终止原因及相关 Signal refs。普通路径和
  已批准 bootstrap 路径复用实现，保持各自的准入边界。
- 区分无匹配、已执行但问题未解决、预算/轮数停止、数据/技术受阻；不能每个
  no_signal_match 都机械判成需要新 Signal。归并只去重复，不丢原文和来源。
- 在现有 backlog/audit 中加入执行故障条目，复用 typed status、输入指纹、
  原始 artifact ref。技术失败继续不进入领域学习/效果计数，但必须进入下一轮
  可操作诊断。未完成 Plan 仅可贡献已有规则允许的无标签技术诊断；不导入正式
  后验学习或更改 bootstrap 授权边界。
- 跨轮保留未关闭的需求及恢复条件；只有有证据的解决/重复/不适用判定才关闭，
  不因 round 完成或原始 meta FIFO 轮出就静默丢失。复用现有落盘机制，勿建新队列平台。
- `commit_round()` 的指针先正常提交；随后重建派生 backlog，并在新 Slow 启动前
  根据已提交 checkpoint 再次幂等核对。否则当前提交前的 attempt 刷新会漏掉刚完成
  的方案。中断发生在指针与 backlog 之间时恢复派生文件，不回滚完成指针。

### 4. Fast 提案与 H1 消费完整、受授权的反思

所属规格：`research/evolution_core.md`、`research/evolution_plan_roles.md`、
`research/evolution_signal_roles.md`、`research/signal_evolution.md`。

- 删除按 assessment 固定抽样的唯一输入路径；当前 FIFO 内原始案例反思、纵向、
  横向层全部保留，用现有 round/plan/case_index 和内容哈希核对。没有横向比较
  在输入说明中明确为不适用，不新增另一套记忆记录。
  原始对象继续不可变；完整消费不意味着复制所有原始财报和请求日志。
- 首批直接发送完整当前 FIFO 内容，复用现有精确请求估算和硬预算。超过上限时
  沿现有预算暂停路径记录 context-budget-blocked，不静默抽样，不降为无假设。
  自动分页列为后续工作，只有真实完整输入确实无法容纳时再设计；首批不建设分页
  提取、合并和调度流程。V18 的约 106K 字符应先做精确 preflight，而非凭字符数猜。
- 只给 Fast Proposer、H1 和本来获准看标签的诊断角色完整后验反馈。
  E1、SignalExecutor、盲 Predictor 不能接收这些结果标签/反思。保留身份掩码与
  真实 wire request 审计，校验内容和 manifest 一致。

### 5. 让 Mining 对所有方向有去向，分开假设与证据就绪

在现有 H1 契约中加入简短的、带来源 refs 的方向分流，不另造大型代理系统：
已有 Signal 更新、数据/执行修复、可定义的新测量、重复已有测量、尚不能定义测量。
这些是工作去向，不是新的 Signal 输出值。复用当前 hypothesis 槽位和候选数量限制。

- 一个可定义、可证伪且不重复的测量，可先形成假设，再由数据准备/H2/H3 判断是否
  能检验；拿不到材料时保留假设及阻塞依赖。不从结果标签推断源事实。
- 只有 provider 错误的需求可以走修复，不必生成假设。无新假设必须覆盖输入方向，
  不能只复述几条供应商失败。不要求逐条输出长文章，允许带多个来源 refs 的归并。
- E2 增加结构化无候选结论及实际比较组 refs，解释无可测重复模式、证据不足、
  已有 Signal 覆盖或后续验证需求。空数组本身不再足以表示完成研究。
- H2/E1/E2/H3 保持固定的归纳/验证分组、issuer 隔离和样本下限；数据不足不换
  holdout 凑数，不把技术失败算反例。缺页或证据不足时记录明确受阻及后续动作。
- 为上述接口同步 prompt/parser/spec/协议版本和指纹。输出错误仍使用现有有限
  correction、逐项验证和隔离；有效兄弟项保留，不手写每种模型措辞的补丁。

### 6. Update 真正修改目标行为

- 首先对齐 `_candidate_arguments_schema()` 与现有 `SignalRetrievalPolicy` 的字段。
  保留完整候选接口，增加少量明确 changed paths 和关联 diagnostic refs。
  运行时以 stable spec 为基线构造候选，未声明更改的可选检索字段必须保留；
  删除同样需明确声明并验证。比较实际执行差异，版本/tests-only 不构成更新。
- 诊断分别记录来源事实是否支持、Signal 定义是否适用、抽取是否正确、结果与标签
  是否相关。不得因为股票涨了就把有来源支持的风险事实改成“抽取错误”。
- 候选回归测试关联所修复的诊断或保留的边界；声明修改 skill 必须有实际 skill
  差异，其他修改同理。不要试图用关键词判断全部语义正确性：结构一致性用机器
  检查，真实行为用同一执行器和有来源的测试验证。不能改答案来让候选通过。
- 取样服务于问题类型：explicit misleading 从产生归因的正式事件取证；
  unavailable/适用性问题不强制先存在 wrong 样本。技术执行状态不进入领域分桶。
  保持独立 holdout 和固定门槛；不足则准确 defer，不将 defer 等同于 Signal 无效。
- 纠正完成后才 staging。沿用完整 fixture、独立效果验证、原子 Registry 晋升；
  不修改 canonical description、评分、极性定义或晋升阈值来迎合本次结果。

### 7. 修复重复工作抑制与恢复

- 各阶段指纹使用实际依赖：完整 meta manifest、需求、相关 PIT 文档/就绪状态、
  投影及角色协议、Registry、已有完整 model work_identity。
  复用已有哈希工具；无关公司新增文档不应让所有候选重跑。
- 已完成的相同语义工作继续去重；technical failure、额度/数据/上下文预算受阻
  保留 pending 和有限恢复资格，不能永久当作搜索穷尽。
- 单轮纠正和恢复次数有硬上限；跨轮只有明确的恢复时间、依赖变化、协议变化或
  有界恢复尝试才执行。有效缓存、已完成兄弟任务和费用账本保留，避免循环付费。
- 总体 round/cycle 指针和分阶段结论分开报告：一次有界周期可以完成处理，但某些
  研究工作仍 pending。验收不得将 pending 的挖掘计成已验证有效。

## 验收矩阵：实现完成的必要条件

| 路径 | 必须看到的结果 |
| --- | --- |
| HTTP 200 额度/权限/未知结构 | 不进入成功缓存，不成为有效空数据；类型、脱敏诊断、恢复条件正确 |
| 已污染缓存命中 | 精确失效相应键；有效缓存不受损；不反复播放旧额度响应 |
| SEC 历史及外国发行人 | 使用时点前官方文件；查历史分页；语义报告请求可找到适用表单，严格表单请求不被偷换 |
| 财务 JSON 及长文边界 | 指标名、单位、期间、比较基准和数值关系可见；原文引用/PIT 仍通过 |
| V18 35 unavailable | 每项有阶段归因；证据不足与技术失败分开；已证实可恢复的遗漏真实恢复，待判定项不冒充成功 |
| 普通 Fast → backlog | 118 条原始需求均可溯源，无 bootstrap 也工作；重复重建不重复写入 |
| 全 meta 消费 | 原来被抽样丢掉的独有线索出现在实际完整输入；超硬预算明确暂停，不静默丢失；盲角色无标签泄漏 |
| H1/E2 零候选 | 有覆盖、来源和原因；可定义假设但数据阻塞与无假设区分；不强制候选 |
| 技术故障 → Slow | 故障不进领域样本/效果学习，诊断与恢复需求能到下一轮；有效兄弟项继续 |
| Update | 原配置不因遗漏退化；有实际执行差异；诊断、变更和 fixtures 可关联 |
| 重复与恢复 | 同语义输入不重复付费；补齐相关数据/改模型或协议后可恢复；无关变化不重跑 |
| 正向候选闭环 | 受控测试中：挖掘 → staging → fixtures → 独立效果验证 → Registry 晋升 → 下一 Fast 实际选择并执行新版本 |
| 负向及中断闭环 | 无候选、无变化、真失败、未知坏响应、中断恢复均有正确状态，指针/账本幂等 |

先做与改动相关的测试，再完整运行：

```sh
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests
scripts/lint_repo.sh
```

重点测试文件：`test_data.py`、`test_data_resolution.py`、
`test_evolution_routing_plan_roles.py`、`test_evolution_signal_role_adapters.py`、
`test_evolution_execution_roles.py`、`test_signal_evolution_engine.py`、
`test_evolution_reliability_matrix.py`、`test_plan_evolution_engine.py`、
`test_evolution_control.py`。发现实际类名后再选定向类，不用不存在的历史测试路径。
新增测试应验证语义/状态交接，不能只复刻实现或断言一个字段存在。

## 真实验收和报告要求

1. 本地回放及定向测试通过后，冻结新代码和新 run contract。不要在 V18/V19 上
   改完成指针、覆盖 artifact 或以旧响应证明新提示词效果；历史工作区继续不可变。
2. 在授权预算内先定向验证：额度错误恢复后的电话会、SEC 历史/表单请求、
   完整财务上下文、原来被省略的反思、Update 的有效差异。依赖仍额度受阻时如实
   停在 pending，不能用假数据替代真实可用性。
3. 跑一次普通 Fast → Slow，并审查实际传输内容与阶段产物。再实际验证下一轮
   Fast 消费刚完成的正式指针对应的新反馈/新学习快照；不能手工拷入另一运行的
   meta 或只打印预览代替实际请求。如果有晋升，必须验证新 Signal 版本可检索并执行。
   若无晋升，该分支只能标为受控测试通过，不能声称生产晋升已验证。
4. 真实运行允许零候选/零晋升，但必须给出逐方向去向、证据准备结果、无候选理由、
   候选诊断/变更/测试结果。若 H1/H3 因依赖受阻没执行，不得将其列为全部验收通过。
5. 报告区分：新挖掘数、已有 Signal 更新数、受阻数、fixture 失败数、效果验证失败数、
   晋升数。分别汇报检索/投影/抽取/技术成功率；文件存在不作“数据足够”的分母。
   重试成本、调用数、暂停原因和恢复证据一起报告，不承诺修复后一定提高 F1。
6. 更新相关 spec/status/changelog，运行 lint、检查差异，只提交本任务文件。
   不写个人 memory，除非用户另有明确要求。无需 push 或部署。

## 审计证据入口

- [完整运行与定向验证报告](information-evolution-v18-chain-audit-2026-09-11.md)
- V18 根：`runs/cold_start/evolution/information-evolution-mvp-20260911-v18`
  - `state.json`、`cycle_state.json`：权威完成指针。
  - `meta/round-0001.json`：完整反思；`capability_backlog.json`：实际需求清单。
  - `experiments/trajectories/plan_r0001_c02/*.json`：24 个正式案例。
  - `experiments/cycles/cycle-0001/slow_loop_result.json`：H1/E1/E2/Update 原始审计。
  - `requests/960fb51d419036f31bbb8d6d1cad4ece275205f7007f92553cb388d9a727101f.json`：H1 实际初始输入。
  - `signals/risks/customer_concentration/versions/v1/` 与
    `signals_candidates/risks/customer_concentration/v2/`：实际更新差异。
- V19 根：`runs/cold_start/evolution/information-evolution-mvp-20260911-v19-validation-b`
  - `targeted_e1_replay.json`：较新财务记录已经可见但概念上下文仍有缺口。
  - `targeted_validation.json`：客户集中度四项真实测试。
  - `next_fast_input_audit.json`：只验证过下一 Fast 输入预览，非实际下一轮。

待实施方案不改变当前模块契约。若实施中需要改变祖先架构、数据切分、固定评价或
晋升规则，按 AGENTS.md 单独提出；不要把这些变化夹带进可靠性修复。

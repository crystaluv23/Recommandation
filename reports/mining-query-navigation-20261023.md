# 查询选窗到原文阅读的连接

本轮在已封存v3之外修复真实query origin交付。外部API/网络/新业务标签0；没有生产作者、新候选、准入、发布、业务指针推进或原stage续答。原10答/2055941消费、316封存文件及263原source保持。工程MVP仍open；新模型自主发现→实现→准入→精确使用须另验。

## 首次丢失处与修复

旧fetch内部已选中相关normalized window，却只交付计数/标题；目录固定24个章节命中不能定位晚段。旧_verbatim_window的首词find能错锚到同文档另一重复段，不是可信导航。此次不依赖该legacy discovery preview，也不把它升级成引文：canonical Event refs/excerpt/exact_span保持，候选与S5继续只接真实已执行read证据。

owning spec先改，共享selector保精确start/end，原excerpt/clipped返回值逐字保持。HTML沿既有可见投影的raw runs；news严格保原metadata-title与title/summary/body/content顺序、split/join及原有不剥HTML行为。仅严格JSON通过后的top-level string有真实origin，decoded重复key last-wins；escape/surrogate pair/Unicode空白保真实raw间隔。标题元数据和非字符串渲染不伪造坐标。不同字段、逆序raw位置、巨大hidden/tag gap及4000raw界分成真实片段；合成空格不是阅读起点，无法映射/oversize明确披露。

非空query的普通heavy fetch增加独立导航元数据，绑定case/query/doc/hash/type/clocks/projection/raw范围与raw-slice sha；空白query不添加导航。既有ledger.coverage保存快照，最近fetch优先的12whole/8000byte工作页跨动作保留；重复hint去重，case/query不合并，实际resolver binding变化标historical。全次fetch按canonical case序保持coverage与输入case顺序无关，case内document/projection顺序保留。没有新工具、预算类别、免费阅读或第二套持久化。

hint始终discovery_only/source_read_completed=false/candidate_citable=false，不进入ledger evidence refs、materialization或exploration计数。普通browse read_span消费所给document/offset/length后才产生真实读窗。query命中可能是TOC/crossref，不能支持研究结论、完整覆盖或不存在断言；按普通成本refine query/缩小fetch范围继续。

## 原失败、反例与关联检查

父11项包含原annual/quarter来源、legacy逐字比较、metadata/hidden重复、JSON逆序字段/重复decoded key/嵌套诱饵/escape、大gap/4000界、空query、owner/PIT、50来源页界、重复fetch/不同query、changed source、共享doc双case读权限。最初测试先有28个harness错误（24次非法空正文、3次参数名、1次构造矛盾clock），修正后另3次请求不存在family、最后1次对dict切片；日志分开保留，未归因产品。有效反例使用合法源对象，矛盾clock在RawInfoDocument层即拒绝。

[独立首审8组](../runs/diagnostics/mining_query_navigation_20261023_v1/independent/review-result.md)及4337次对git f0旧helper逐字比较通过；news origin片段再独立JSON decode对projection substring核真。其首次harness只改hash被原件自身拒，原尝试保留。

首次492关联为491过/1真实回归：新增coverage导航顺序依赖case_refs，与旧whole-action顺序无关契约冲突；首审也漏查这个组合。修复canonical case序及同fetch不逆转片段后，[独立追加10组](../runs/diagnostics/mining_query_navigation_20261023_v1/independent/review-result-revision-2.md)通过：原4337比较仍同，3case×2doc全部6排列coverage/omitted同、JSON逆序字段及fetch A→B→重复A的工作页顺序/去重正确。旧报告/hash和首失败保留，不追认早期已过。

最终[492关联](../runs/diagnostics/mining_query_navigation_20261023_v1/associated-test-bindings.json)全部通过，34.323秒，测试前后源码hash同/socket tripwire0；独立审查限离线机械行为，非fresh服从或研究收益。

## 完整原生上下文与读取探针

[完整探针](../runs/diagnostics/mining_query_navigation_20261023_v1/full-native-result.json)在TemporaryDirectory复制原workspace，用原263源/18baseline/265needs/六披露/授权dev8分组及原identity inventory，经真实Engine/Factory/Controller重建旧10个已保存原答。原canonical ledger逐值同，materialization evidence的JSON值及canonical hash同；没有把旧答说成新模型服从。首探针把live tuple operand与落盘JSON list直接比较而失败；修正为JSON值+canonical hash双核后通过，仍区分数值类型/布尔/顺序，首日志保留。

随后执行明确的**脚本假设query/read工具动作**以检验接口，不作为第11作者答案，不提交任何stage。query正常扣heavy1、不增加read/materialization；四个真实origin可经普通read_span消费，再扣browse1、增加一份实际读窗。两种假设状态分别由原生Caller/完整assignment/identity/预算披露在request_ready零接收捕获，精确bytes_plus_output预留为**232555、234197**，均在原single262144以内；每份消息成本与self-disclosure同。二者各自从同一旧spent10/2055941出发，不是两次连续新请求已执行或消费，亦非host tokens/美元费用。

[独立只读终核](../runs/diagnostics/mining_query_navigation_20261023_v1/independent/full-native-readonly-review.md)另直接核原10份inbox/outbox/receipt绑定与2055941总预留、新两份完整消息成本/self-disclosure、四段raw hash及182实际代码/spec绑定；未重跑探针。审核自身两次envelope/JSON编码harness错误保留，未作为产品失败。

316旧stage文件/312终态hash及263source首末同；无new inbox/receipt/fresh reply，LabelStore/check/LockedTest/业务环/效果评价均禁用。读回原dev8授权分组用于同一受控上下文，不生成新业务标签。没有裁来源、Signal覆盖、backlog或正文来压成本。

下一步只准备保留旧失败与消费的新代码验收：核明确切资源继承/不重复计费、冻结当前代码/输入/oracle原语义义务，再由fresh独立subagent逐节点处理原生inbox。v3保持终止，不能补h011、改caps或清空旧消费；离线探针不授予正式运行或候选关闭结论。

首次lint仅因原始失败日志自带行尾空格拒绝；该日志以gzip逐字保存并核解压hash，未改原失败内容。产品和测试源码无变化。

# Source navigation boundary — private read-only audit

**确认有结构性导航缺口；没有证据把它归结为模型不会研究。** h009/h010的annual卡均为raw4,049,846、section_count43，但只给sec00–sec23。真实Item9A是**sec34/raw855371**，在被截掉的19个matcher命中内；sec07/raw251757只是TOC。前12项主要是TOC/先行引用，sec15/20/22/23又是cross-reference。共享matcher文档本就承认TOC/crossref会命中；其80字匹配还能吞进邻近标题，section_count不是43个完整真实语义章节。`document_card`明确`sections[:24]`，没有同文档章节next cursor。

h009的document next_cursor=3只翻14个文档中的下一张，不翻该annual的章节尾部。h010剩light0/browse20/heavy11；evidence目录scope已不可调用，read_span只收已知fact/event/document与raw offset/length≤4000，没有section_id或find selector。任意offset可读不等于已给模型可找到的定位。h009选择了已披露的真实Risk Factors sec13，h010明确说其loss/going-concern文本**不能证明ICFR弱点或不存在**，再沿next_readable_start续读；这两个动作本身没有错误ICFR结论。

季度source1507在本地授权263内，完整matcher27项中的真实Item4为sec17，处于其前24范围。独立按原生event identity算出的event-744536812ddcbc30确在h009/h010 known_event_refs，但**两实际请求没有其accession、document card或section mapping**；opaque handle存在不是相关正文坐标已披露。不能把审计者知道的季度位置当作模型已经看到。

## 原文及历史版本

annual source1506实际Item9A管理层段落raw860329–862663明确：ICFR **as of December31 2024**不有效，原因是complex financial instruments控制环境material weakness；随后raw862663–863768说本年度报告期间未修复。quarter1507的raw2334869–2336241在quarter endedMarch31 2025披露同类实际ICFR结论，继而本期未修复；该段先谈disclosure-controls评估，不能抹去对象区别或强化成cutoff当天新评估。这些来源结论均来自原正文，不来自已读risk window。

annual accession0000950170-25-054321 / `buru-20241231.htm` 的SEC acceptance=published=available为2025-04-15 21:15:29 UTC；quarter0000950170-25-075392 / `buru-20250331.htm` 为2025-05-20 21:28:45 UTC，均早于case cutoff2025-05-30。原SEC submission行、原Archive body cache（2026-09-17采集）与snapshot全正文相同已直接核过。精确URL、引文/完整正文/窗口hash、生成器/实际inbox绑定见[bindings-evidence.json](bindings-evidence.json)。资格仍是bounded local historical filing binding，非contemporaneous remote attestation或绝对无后更新证明。

## 优先方案：既有fetch query交付真实导航hint

不必先增tool或转移预算。`fetch_case_evidence(query)`已调用共享query selector；`_normalized_projection_text`保有真实projection→raw runs。独立固定query `internal control financial reporting material weakness` 在annual选中的真实raw origin为856999–858389（disclosure-controls评估/后续ICFR入口），quarter为2335368–2335964。当前controller把excerpt/origin丢在内部，`fetch`只交付计数/标题，目录仍为固定24节。**可在既有fetch响应增加source/hash/case-bound、discovery_only的navigation_hints，再用原browse read_span实读。** light0仍允许原heavy fetch(query)，不需把evidence metadata改计browse，也不增加任何cap。原文支持/实读权限必须继续等到真实read，不能让hint直接进入materialization或候选证据。

最小接口例子：既有`fetch_evidence {case_refs:[case-005],source_families:[filing],max_documents:3,query:...}`返回`navigation_hints[{document_ref,content_hash,case_refs,source_type,published_at,available_at,query,projection_version,raw_start,raw_end,raw_span_sha256,discovery_only:true,source_read_completed:false,candidate_citable:false}]`，再执行`read_span {document_ref:<hint>,offset:<hint.raw_start>,length:4000}`。保真实选择范围、遗漏/非穷尽披露、native identity masking和完整请求预算；无免费读取、无新研究结论。字段/调用及反例详见[findings.json](findings.json)。这是未实施方案，无需臆设新的用户审批门槛，也不授权重启本sealed stage或启动v4。

**两个限制必须保留。** 一是旧`_verbatim_window`只用excerpt开头几个词在raw里find：quarter query `controls procedures`实际选TOC raw203708–232486，却被该heuristic错锚到2327579附近，不能直接拿它作可靠hint；应保selector原projection origin。二是泛query确会选TOC，单hint不能保证语义相关或源检索完整，更不证明弱点/不存在；literal query refinement、多个非重复真实hit的有界披露及正常实读仍需保unknown。优先方案能绕过本例24节截断去找已知主题，不能冒称完整章节目录已修。

## 次级选项、因果边界与停止

若要完整目录，可在已有`inspect_catalog scope=evidence`加可选`document_ref/section_cursor`，按同doc/hash的matcher索引分页并保明确omission；它仍花原light，因此light0不可达。把此类分页改花browse属于另一个明确预算接口选择，不能偷偷做。TOC/crossref结构注释或排序只能辅助，需保unknown/原offset，不能凭regex删掉所有不确定项或把heading当证据。通用反例包括重复TOC/真实晚标题、实体/Unicode映射、同句多次出现、无匹配/隐藏正文、wrong-case/postcutoff、文档cursor与章节cursor混淆，以及hint未读却被候选引用。

本诊断只关闭“实际有晚段索引定位丢失且query定位尚未交付”的不确定性。它不证明作者换行动就一定成功，也不把独立的single-request budget阻断合并成一个“模型差”根因；精确成本由另一审查者负责，本任务未重算。没有实现新产品代码、增加caps、改oracle、advance/reentry、派h011或启动v4。

stage/各oracle/263源/182代码等**1444个受保护文件前后字节相同**，见[完整初始绑定](protected-inputs-before.json)与[不变性结果](invariance-result.json)。外部API/网络/GET均0。审计位置和引文只保存在这个私有诊断目录，绝不交给生产作者/候选。停止此有界扫描。

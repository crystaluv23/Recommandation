# Mining目录跨动作上下文

当前修复针对实际成功目录查询后，其完整响应在下一次read/compute后丢失的错误家族。生产角色为独立fresh subagent，外部LLM API和本轮网络调用0。没有改测量、canonical业务记录、标签、来源、PIT或资源预算。

## 实际断点与遗漏

98147bc1原生stage-v2已证已读两来源三正文窗持续可见；原答正确保留DCP有效与ICFR assessment未知的差异。但目录页、章节坐标和next_cursor仍只在last_action_result，读正文即替换。h007必须恢复cursor0，用完最后light；h008只看到2/14目录项，h009又失去目录。h010/h011沿next_readable_start继续case005封面并诚实保留未知，不能倒称这些动作本身错误，也不能由未读12份证明不存在模式。

正文修复保了source→S4含义及原S5交接，遗漏了同一工作链的目录→下次read和目录→下页导航依赖。旧测试在脚本中保存目录/定位坐标，与每节点无会话历史的真实组合不同。适用家族还包括已查Signal后页/完整定义、backlog按需原件和memory响应；未实际触发的风险将与本次目录实证区分。

## 冻结历史与验收边界

stage-v2保11实际首答/0纠错、1,837,419逻辑预留，323文件和182源码归档。h012未派未答，原生仍pending；不是终态、预算耗尽或no-pattern。stage-v1的12答/2,001,316、336文件及h013未答继续保留。两轮候选分母各1未完成，消费者各4未试，没有准入、发布或业务完成指针推进。

新driver只允许stage-v3，逐次检查两个旧文件集、pending无答、归档和原生receipt计费，并在新contract记录各自历史。新评估保持263源/stable18/full265/six disclosures/dev8/original groups及原所有caps；不导入旧LLM答案，不手写候选或forced ref。oracle-v3须在新演员前冻结，并逐字段保持既有语义义务。

## 最小修复范围

成功inspect_catalog的实际完整响应统一进入catalog_observations，四scope共享8whole responses/32000 UTF8 JSON bytes，保原runtime handles、args、ledger action、response/source snapshot hash。whole页入选或显式给遗漏/超大请求坐标与所需字节；未查询页、未读原件和模型语义笔记不补入。重复查询仍扣原scope预算，完整页面、披露和重复last result均计原生请求成本。

目录来源快照保真实文档/hash/case及顺序，与阅读进度分开：read/compute不使旧next_cursor失效，新增来源改变目录时标明snapshot不再匹配。历史页上的read_windows不是当前阅读状态。Signal原件仍守精确版本/hash；backlog缓存只有当前实际可见、hash匹配且仍pending项能进入当前allowedrefs，已staged/遗漏/超大/变化项不获权；既有basehash/typed校验保持。memory已读原件的原48KBdisclosure路径保留，大于32KB的合法响应明确oversized，不裁正文。

家族审计也识别到静态可达的compute后继含义缺口（当前11节点未触发compute）。新增小页直接从既有ledger/relations/facts派生12whole/8000 bytes实际计算值、rule及ordered operands，非自动关系不冒充计算。旧relation无operand快照，任何后fetch保守标invalidated；保历史relation供寻址，不附新facts冒旧operand。失效关系在S4引用前typed拒，普通付费compute可恢复；不重算、不删原relation/ledger/S5、不改算术或可比性含义。该层不声称证明统计关系有效。

实现层18新+63关联81过，最后历史重算locator小修另有3定向过，原hash和日志均保留。归档98147的五回归为4个缺新工作页错误、1个backlog可见权限断言失败；不是五个语义误判。最初测试将最多8页误作必有8页，实际32KB先到只6页，原harness及失败日志保留，仅修正容量断言。父在冻结前还纠正了read_progress混入目录population hash，以及invalidated计算页缺重算坐标两处设计遗漏；没有带入新stage。

[独立8组](../runs/diagnostics/mining_catalog_working_context_20261023_v1/independent/review.md)首5/8通过，3组因memory测试任意字段不属canonical source、docid含非法空格、fact.value类型预期错误而失败；原脚本/结果保留，只纠正3组输入后3/3通过，5已过不重跑，最终产品hash均同。两真实source目录/三窗与旧部署逐项核sections/坐标/case/时钟，old/new ledger/S5/预算同；read+compute游标保持、source顺序变化失效、case/hidden拒、need已处理/陈旧/变化/淘汰拒及Signal原件守卫通过。实际memory packet35274字节超过32KB页时whole omission明确且原48KB原件仍在；synthetic native完整wire成本30403、身份正反投影及receive前cap通过。其中一条本地synthetic响应不是生产作者，不计fresh链能力。

父最终470关联全部通过（31.491秒），测试前后相关源码hash同、socket tripwire0；真实temporary prepare/首请求捕获属于零作者连接检查。最初stage模块20过/1错误为oracle-v3尚未冻结的harness依赖；冻结器的runtime/import与root路径前置错误均保留，不算产品语义失败。最终oracle-v3 sha256为dada4c92bac32c133f4efa7bea523d0b0f05d57d0340d1660cdf7976bf257096，15个原有受保护字段逐字段同，三版canonical hash均4951c16c4d3cb976595e0ca12d16388fb13b85e7096fc34831e728ab55914429；两旧pending-progress另精确绑定，未改旧映射。

本地与独立边界验证已完成；后续实际v3已验证自主目录→正文→下一目录页的窄连接，结果见下；完整候选、S5、准入和精确消费仍是原能力正控要求。目录保留本身不关闭S3–S8或整体MVP。


## 9ae48904实际v3结果

原生stage-v3按manifest 23ffcb31d7cb9d50dfc84bde262b8b2d6c63a7fd63b4cfa369f3f3abf4f630f4冻结后运行；10个独立fresh首答、0模型纠错，2055941逻辑预留，外部API/网络/新业务标签0。完成收据为terminal_resource_or_control_stop / MiningRequestBudgetExhausted before prepare；没有第11个inbox/answer/receipt，不重入或续补。候选正控分母1未完成/0passed，4消费未试，无候选、准入或业务指针推进，MVP保持open。

[固定实际窄核](../runs/diagnostics/mining_catalog_working_context_20261023_v1/actual-deployment/report.md)只审7答+h008输入：h003–h008完整18卡同；首evidence页及sections/next_cursor2在A/B/C后保留且population匹配。h007直接读原目录另一case的C，没有重查页0；h008有两源三窗且light1。7答完整入账1285176，h008仅预留251665。223固定文件及182冻结source hash均同，真实raw_span_view/source/hash/range/case/时钟匹配。v3实际document targets与v2 event targets、broad2879facts/1342relations与targeted2088/952不同，不声称修复导致因果效率提升。

随后h008按保存next_cursor2查询，h009获得第三份case005年度申报的完整本页目录并直读risk section；原答明确未读12/11份不证明不存在。h010保留亏损/going-concern事实不冒充ICFR，继续原next_readable_start。下一请求被原预算门阻断；两项独立只读诊断已完成，详见下。预算异常不等于no-pattern或模型语义失败。

182实际冻结source已逐hash归档/读回，archive sha256=02acdd0479bae8d2cbbd53743224db580c42d1b5e5503d5d4d356adb004291f1。后续只做封存目标外的只读诊断/最小方案，不自动起新控制或增加caps。


## 完整请求与晚段定位：独立诊断结论

[原生完整成本重建](../runs/diagnostics/mining_catalog_working_context_20261023_v1/terminal-boundary/report.md)在临时副本通过同一Engine→Controller→RoleModel串联前10份旧原答；10轮实际projected messages、stage、output allowance和request hash逐字一致，随后同一预算门在prepare前拒绝。下一完整请求估算**264980**，比原single262144高**2836**；Mining累计仍余10526971、只用10/80调用，global也未耗尽。264980未发送、未计已答成本；这是离线旧答重建，不是h011真实请求或新模型服从证据。

known_fact_refs2879条贡献74875，known_relation_refs1342条贡献40285，合计完整成本43.4599%；4份whole目录27221、5份正文13917，均未到各自局部淘汰边界。只修掉此次2836或删几段正文仍不能证明后继可运行。此前预检只覆盖首请求，局部工作页边界不能限制整个后续图谱；这是本轮遗漏的完整组合层，不是已部署目录修复回归。316封存文件前后同，312终态表匹配、182代码及263原source保持。

[独立源导航核查](../runs/diagnostics/mining_catalog_working_context_20261023_v1/source-navigation-boundary/report.md)确认annual matcher有43个命中，但卡固定只给前24项；真实Item9A在sec34，前段有TOC/cross-reference。document next_cursor翻文档，不翻同文档章节尾；opaque event ref也不提供其原文定位。已核原SEC行、完整archive cache及本地正文相等，资格仍限bounded local historical binding，非绝对历史无更新证明。私有审查位置和结论不交给后续生产作者。

既有fetch(query)内部已有真实projection→raw runs，却只交付数量/标题，未将所选命中坐标交给角色。light0时原heavy fetch(query)仍可用，随后可用原browse read_span实读；无需加工具或转移预算。旧_verbatim_window以开头几词find的近似锚点在重复TOC反例中错位，不能用作可靠导航。查询命中也可能只是TOC，必须保持非穷尽、未读/不可引用和语义unknown。

下一最小范围为**封存目标外的spec-first离线修复**：先验证fact/relation不透明标识能否在模型边界无损短编码并反投影，保每个事实/关系/顺序/权限与canonical原件；再将既有query的真实原文origin作为有界discovery-only hint交付，普通charged read仍是证据入口。两者都须经原失败、碰撞/重复文本/Unicode/错case/PIT/未读引用等反例及完整成本验证。没有证据支持删事实、裁正文、加cap、重启v3或直接起新控制。修复通过后仍须另外冻结合法的新版本验收及不重置既有资源的计费方案，不能把本诊断当授权或候选完成。

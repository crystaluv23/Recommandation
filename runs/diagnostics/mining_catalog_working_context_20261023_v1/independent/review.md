# 独立反例审：有界目录工作上下文与已计算结果

最终源码绑定已确认：controller `1f5dfc82…`、role_model `105325b1…`、owning spec `2f62346d…`、new tests `a8f00a60…`，与父提供完整hash一致。11个相关source/spec/fixture文件在首次控制和纠正控制的开始/结束全部相同。`review-manifest.json`为最终绑定；结果文件预置preliminary标志保原样，不把它覆盖成另一轮。没有改产品、spec/tests、stages、oracle或任何生产答案；没有读取h012、运行真实stage、联系actor；socket连接禁止，网络/外部API0。

**本次8组独立离线控制已通过，没有发现具体产品缺陷。** 首次5/8过，另外3个错误均发生在独立测试输入构造/预期：memory顶层任意detail不属于canonical feedback字段，未成为所读canonical source正文；document_id含空格违反原始安全ID契约；EvidenceFact.value实际是str，不能加int。初始script、results/tracebacks完整保存。只修正这3组输入后3/3通过，前5组不重跑，产品hash未变。此外第一次启动缺repo根tests导入路径，在控制开始前报错，单独保留 initial-import-error.txt；改为PYTHONPATH=src:.，没有产品变更。

| 独立控制 | 具体证据与拒绝边界 |
|---|---|
| 原两真实source→目录→A/B/C | 原始两份filing hash与之前固定绑定同，query/24doc上限与真实fetch一致，但仅加载两已绑定source。重建目录的sections、section_count、raw_chars、readable_start、case_bindings、available_at逐项等于实际h005对应卡。与冻结98147bc1执行同一工具序列，ledger/预算/S5完全相同；旧版目录消失，新版whole response在三个读取后仍等于初始原件且source_snapshot_matches=true。历史卡无read_windows，当前目录已有真实read_windows，两者没有混同。此为两source离线投影，不是14doc/8case全回放。 |
| cursor与顺序 | 19份synthetic原生fetch目录，cursor12，经两个实际read及一次compute后仍current，直接cursor12到达新文档，无需cursor0。另对native fetched-result输入顺序做同集合/同hash逆序变体，实际目录顺序改变且旧source_snapshot_matches=false、whole旧卡不被替换。顺序变体直接改局部输入状态，不冒称生产fetch实际发生过这个重排。 |
| scope/hidden拒绝 | 真实原生catalog后，只读共享doc的case001 event，case002 event citation仍前置拒；hidden-only窗口也拒。目录没有授予read scope；S5不出现未读case event。失败不改变ledger/预算/S5。这里只检查确定性citation readiness，不宣称候选研究语义正确。 |
| backlog授权 | 已读offpage原件n037/n038经另一次read后仍可见并合法进入allowedrefs；未读n039没有权限。处置n037后再提拒，旧base给仍pending n038拒；改同ref原件来源后旧缓存不再授权；9个其他actual whole reads挤出旧项后不得授权；未知ref拒且不污染缓存。历史可见性、当前pending与当前base分开，不用历史缓存恢复staged权限。 |
| Signal/Unicode/容量 | 读后页及measure19完整原件，再读source；measure19 skill保留，未读measure18 skill不出现，身份明文不出现。改原件后再读以hash drift拒且原缓存不变/标历史。5个独立多字节whole originals只容2个、明确遗漏3个，每个可见原件2800个四字节字符完整保留，items≤32000；backlog9请求同样执行8页上限/明确遗漏检查。没有截断补齐。 |
| 真实indexed memory | 用canonical feedback字段注册两个真实ReflectionMemoryIndex来源，仅读large来源，原生packet35274bytes（48KB以内）完整保留在既有meta_memory_disclosures；catalog wrapper35764bytes超32KB，whole oversized locator含hash/args/required_bytes，未附正文。未读另一来源正文不出现在catalog context；未知memory ref拒，已有disclosures/ledger/预算/S5不变。无需为恢复该原件再次read。 |
| 原生身份/成本/cap | 使用真实StructuredRoleClient+LocalRoleExchange，只在本目录synthetic-native创建synthetic inbox/outbox/receipt并消费一份明确synthetic响应，未交给任何actor。已披露目录中的安全doc handle包含身份alias，实际wire匿名化后响应选该handle，native恢复精确原document_ref。被读Signal全文保留，未读skill/hidden脚本无泄。完整messages bytes+max_output=30403，等于实际payload request_budget.this_request；更低cap在receive前抛MiningRequestBudgetExhausted，receive guard未触发。控制器ledger/预算/S5不变；这里的30403是synthetic逻辑成本，不是实际新stage成本/host tokens/费用。 |
| computed_statistics | native compute后经catalog/read仍保rule/value/orderedfacts/case与完整operands，仅实际computed关系进入页。真正原生fetch后，再对局部同fact_ref输入value/taxonomy做对抗变化；旧行invalidated但原relation精确保留、没有当前operands，旧ref propose前置拒。关系原件未改；ordinary compute后新行附现值/现taxonomy、恢复citation。items≤8000。不重新推断可比性；这是保守阻断及离线对抗输入，不是实际11节点发生过compute失败，也不证明真实producer会重用这种fact_ref。 |

whole-response的边界没有变成免费读：cached目录仍是discovery_only；raw section是导航，不能作为候选正文；memory只保存实际read返回内容；Signal card不会展开本地所有originals；backlog allowedrefs只来自当前可见whole项且匹配当前原件、pending。未知/失败请求不加入已接受缓存。所有缓存工作页均复制投影，whole数据仍由既有source/ledger/S5持有。

局限：此轮独立控制没有新增production LLM执行，没有证明模型会使用缓存避开h007式重查，也未证明研究语义/候选唯一性/准入/consumer/收益或MVP关闭。容量测试覆盖whole Unicode、9请求淘汰、真实memory oversize；没有穷举每种scope的所有异常参数/oversize构型。same-ref输入变化和重排是明确synthetic对抗变体，不记为生产触发。旧h001–h011实际证据与第一次可避免重查结论在前一catalog-family-review中保留，没有改写旧stage或旧失败。

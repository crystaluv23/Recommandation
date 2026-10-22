# Mining 定向 query 投影修复与泛化前置预算失败

本轮推进了 **S3/S4 原材料可达性**：修复既有 fetch query 在结构化概念投影处丢失的连接，并以真实 IFRS 原件和代表性变体验证。新泛化两控仍在**正式准备前阻断**，没有生产作者回答。外部 API/GET、新业务标签、候选、发布、评分、业务指针和完整后继均0；整体 MVP 未关闭。

## 为什么没有直接调用作者

上一轮比较 locator 已在真实当前请求中离线可达，本轮选不同来源实例检验泛化。按原 Discovery 顺序固定case-001/002首份财务文档1179/0770：分别为ifrs-full年度负经营现金流与us-gaap九个月正经营现金流。两个issuer/accession/期间/数值均不同于旧0671。既有opaque label/time仅从原native wire导入，没有新写业务标签。两控都是受控单文档材料消费，不是跨组比较、完整S3/S4或新provider能力。

独立审查先读原文、冻结[source-reference](../runs/diagnostics/mining_locator_generalization_20261023_v1/reference/source-reference.json)及[判定义务](../runs/diagnostics/mining_locator_generalization_20261023_v1/reference/prefreeze-obligations.json)，不读未来模型回答。要求两operand真正读过、期间/单位/namespace/含义准确且保留历史范围；可选通用算术不作为必过义务。原件均为retrospective normalized SEC API extraction并要求primary-filing audit，本轮不把它们升级为原始申报真值或case最新资料。

首个真实 fetch 检查发现：1179原文有两期IFRS OCF，但no-query和显式target-query都只投影30facts，目标0。没有选择别的容易样本。精确旧tools源码、受控receipt/ledger及0作者失败保留在 [preflight-initial-failure](../runs/diagnostics/mining_locator_generalization_20261023_v1/preflight-initial-failure/result.json)。

## 局部修复及证据

根因是 `fetch_case_evidence` 只把query用于候选document匹配/排序，调用 `_facts_from_document` 时丢弃；后者又固定向共享selector传 `query=None`。小型表和US-GAAP优先概念测试没有暴露“原文存在、概念超出默认投影”的路径，上一轮工具定位修复也未覆盖这个更早的边界。

先改owning spec，再让既有query贯穿共享selector；仍用12,000字符完整concept单元投影，不增加工具、名单、预算或measurement权限。查询覆盖只数实际投影的fact binding/span或实际narrative excerpt中的literal terms，不把仅在未投影body命中的词称为已覆盖；词面命中仍不证明充分回答。query不改来源选择、源row、namespace/单位/期间/数值或共同fact_ref；no-query保持原行为。

- 真实1179 target-query现返回31facts，其中两目标为USD -2378789（2022-07-01–2023-06-30）与-15122354（2023-07-01–2024-06-30），完整literal和来源hash保真。
- 独立对精确旧源码核1179/0770/0671三个no-query FetchResult逐字段相同；target原row数分别0→2、2→2、2→2，共同refs/绑定不变。
- 276关联测试通过，网络tripwire0，被测文件前后无漂移；覆盖真实原件、typed/legacy拥挤表、未投影hint、PIT/无匹配及原生shared-module连接。首次synthetic fixture遗漏filing_date导致2项测试错误，修正合法fixture后通过；不把它当产品失败。
- shared module构造器仅加optional `controlled_query`，默认None保留旧阶段；新driver受控初始target-query fetch仍严格选原1179/0770，不注入oracle refs，不声称自主source retrieval。[补充义务](../runs/diagnostics/mining_locator_generalization_20261023_v1/reference/prefreeze-obligations-supplement.json)已在正式回答前冻结。

## 原生前置预算失败

[新driver](../scripts/run_mining_locator_generalization_stage.py)沿用真实Controller→RoleModel→StructuredRoleClient/LocalRoleExchange、原single32768/aggregate98304/6decision/output2000/heavy6。preflight每次只从当前实际user JSON取得下一ref，不保存上一步ref或查私有fact表。a的两operand已读入最终视图，但第四个请求在inbox前被累计预算拒绝。

| a的四次prepared请求 | 逻辑预留 |
| --- | ---: |
| compare前 | 22917 |
| 首operand前 | 24274 |
| 第二operand前 | 26955 |
| 结束意图前，已阻断 | 28417 |
| 合计 | **102563 / 98304，超4259** |

前三次input-only捕获、第4次只有prepared journal；0 inbox/receive/模型原答，b未启动，正式stage及成功preflight/result不存在。因此不能称两控fresh失败0/2或语义通过；正式语义验收**未执行**，前置预算不通过。没有增加预算、更换样本、给a追加作者回答或启动完整后继。旧0671/namespace正式1/2与预算终态保持。

[预算归因](../runs/diagnostics/mining_locator_generalization_20261023_v1/preflight/budget-failure.json)：system内容59864、user内容30911、output预留8000、JSON framing/string escaping3788，总量102563。Mining静态prompt本身每次12953字节，实际system含共同边界/envelope每次14966。仅修ref可达不保证该规模资料的完整动作路径可容纳；不能把0作者预演称为新模型服从。

预算归因辅助脚本首次调用code_bindings未先configure，列表含旧shared SPEC，不是正式manifest；原JSON保留，[配置后inventory补充](../runs/diagnostics/mining_locator_generalization_20261023_v1/preflight/configured-inventory-supplement.json)明确更正。关联测试已经绑定当前新SPEC；该harness局限不改变四份实际journal/数值。所有原source绑定复核无漂移。

独立终核还发现第3/4条prepared wire的document_ref保留原accession坐标：issuer CIK/CRML已遮蔽，但这不足以证明整个document handle匿名。0inbox/作者，因此不是本轮已经发送的泄漏；也未证明由本次query改动引入。将其作为fresh前另一项未关闭边界，不能把issuer字符串检查通过宣称为完整匿名通过。

## 下一步

本轮值得关闭的是query丢失的局部producer连接，不能关闭S3/S4。下一步先核source handle的实际身份边界，并检查固定prompt/状态/证据回执的重复成本，判断在保留全部接口、候选/准入义务、证据和完整失败分母时能否满足原资源边界；无信息增量就停止该策略。不能通过缩窄完整MVP、删除工具/义务、减少证据、调小验收义务或换样本制造通过。重要语义改变仍须遵循上层设计权限。Critic/Slow canonical分类声明A/B选择仍待原用户决策，本轮未改该schema。

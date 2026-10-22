# Mining taxonomy 的实际消费验收

本轮修复已读取 fact 回执在后续请求中消失的问题，并完成两个预先冻结的原生控制。**完整模块验收1/2：跨 namespace 反例通过；实际历史财务样本在最终消费前受原预算阻断。** 共7个 fresh 独立 subagent 原答、0模型纠错、0外部 API/资料 GET/新业务标签或 Locked Test 读取。没有新候选、发布、评分、Fast/Slow 提交或完成指针推进，MVP仍未收敛。

[正式独立终审](../runs/diagnostics/mining_taxonomy_consumer_20261023_v1/independent/fresh-consumer-final-review.json)核对两终态、全部1790源/103代码绑定及原答→receipt/cache→action→工具回执→实际消费者请求，不以字段保存或局部测试替代完整模块结果。

## 原失败与局部修复

[修改前真实请求捕获](../runs/diagnostics/mining_taxonomy_consumer_20261023_v1/baseline/result.json)使用原 reviewed1780 view 的 case-008、一次受控 financial fetch，选择原0671历史正文。两个 OCF operand 实际读取后再 compare，真正的 MiningAgentRoleModel→StructuredRoleClient request-ready 请求没有任何 fact 读取历史，只有最新 compare 结果。0 receive/inbox/回答。捕获绑定的 Controller hash与 `ad5870d6` 原版本一致，时间早于修改；不是用旧回答模拟模型。

先改 owning spec，再新增运行时 `structured_read_progress`：保留已经成功发出的完整 masked fact 回执及 taxonomy/concept/unit/period/value、case/document/content_hash/available_at和上下文。按 fact_ref 去重、最近读取优先、重复读计数；最多12个完整单元、8,000 UTF-8 JSON字节的所选内容，遗漏/超大项显式披露。重读仍计原 heavy 预算，未读 facts 不自动进入。相同 ref 的回执绑定变化在更新 ledger/预算前拒绝。模型看到完整源绑定，不由 ref、read_count 或同名概念推断测量等同。

原 fact/ledger/hash、canonical schema、工具、算术权限和研究定义未变。后续请求实际计入这些回执与披露 envelope 的字节成本。266项关联测试通过，网络 tripwire0、103个代码/spec/test绑定执行前后相同；另有独立8组局部反例及阶段边界复验。首次新测试的 action wrapper 和 `heavy_used` fixture 形状错误留原日志，只修断言。

阶段脚本预审还发现 source/code inventory 可被重新冻结、单请求上限未显式传给 local transport、prepared次数/终态自身元数据校验不全。现已分别拒绝预演后漂移、在真实 ready 边界核单条/累计预算并在第七个 decision 准备前停止、验证 terminal_hash/state/sample及所有封存文件。这些是诊断控制的局部修复，不等于业务循环恢复通过。

## 冻结输入与真实结果

[来源侧参考](../runs/diagnostics/mining_taxonomy_consumer_20261023_v1/reference/source-reference.json)和[判定义务](../runs/diagnostics/mining_taxonomy_consumer_20261023_v1/reference/prefreeze-obligations.json)先于任何正式回答冻结，未交给作者。阶段绑定103代码/spec/test和1790源/参考文件；使用实际 Controller、角色适配器、transport、原始 inbox/outbox、receipt/cache、action校验与执行。只预置一次声明过的 fetch，后续 refs/顺序由各 fresh 作者选择；不声称自主检索或完整发现。

| 固定样本 | 首答、工具与终态 | 结论 |
|---|---|---|
| 实际0671 typed历史正文 | compare→read current→再次compare→read prior；4首答、0纠错。current 的 fresh解释正确：us-gaap/USD9,506,313，2011-01-01至2011-06-30。第二 operand 是原文2010H1/USD4,342,261，但其最终消费请求未交付。 | 模块0/1；没有最终语义 endpoint，不能按两条 fact 已落盘或预算门正常工作算通过。 |
| 原 synthetic namespace-before | read namespace-b→read namespace-a→停止意图；3首答、0纠错。末答精确保留两namespace、USD100/120、2023/2024年6月30日期末，拒将同名 Metric 视为可比测量。 | 模块1/1。未compute，不要求它背诵泛型算术权限；本案不证明新的方向/magnitude因子或所有 unknown 变体。 |

实际样本的来源是完整原0671文件，但所选 projection仍有19 facts与其他概念遗漏；financial fetch另有55份文档被 max_documents 排除。它是历史同文件期间控制，不能称2025最新或完整dev8覆盖。本轮未新增原 filing 主文独立审查，不扩大既有 reviewed输入资格的结论。Discovery分组仅从原冻结 native opaque label_map导入；synthetic分组明确为控制数据，没有编造真实 issuer outcome。

namespace末答的“YoY ratio未建立/no statistic warranted”处在测量同义性语境；它没有声称 tool不合法或120/100不能计算。冻结合同允许不做该算术。独立判定保留措辞范围的局限，未追加“必须算1.2/必须复述权限”的事后要求；泛型算术的 fresh 分支本轮未验。

模块停止意图在执行 `record_deferred` 之前由专用边界截住，未把有充分事实的模块结束写成 domain evidence_unavailable/no_pattern。actual则封存为明确技术/预算失败。[阶段合同](../runs/diagnostics/mining_taxonomy_consumer_20261023_v1/stage/contract.json)、[actual失败](../runs/diagnostics/mining_taxonomy_consumer_20261023_v1/stage/actual/failure.json)与[namespace完成](../runs/diagnostics/mining_taxonomy_consumer_20261023_v1/stage/namespace/completion.json)保留原样。

## 新的连接缺口与预算

actual的比较首先返回 current/prior refs；下一次读 current 后，compare输出被 `last_action_result` 覆盖。read progress只保留已读 current，prior再次混在19个不带概念映射的 known_fact_refs 中。第三作者明确说邻近 excerpt不建立 prior完整期间，选择再次比较；这是生产上下文丢失 locator，而非模型无视已给材料。

其4答逻辑预留 **90,772**；第五请求需要26,243，prepared总和117,015超过原98,304，故在receive/inbox前阻断。第五请求没有作者/receipt/原答，也没有新的最终消费。namespace3答 **63,412**；两样本实际回答合计154,184逻辑预留，7 receipts。单请求上限32,768、每样本最多6 decision/98,304均未增加；逻辑预留不是host模型实际tokens/费用，后者未知。

此前受控预演与独立 compare-first字节检查在脚本外保存了 prior ref。它们能证明给定动作序列的 wire、匿名和预算，**不能证明下一 fresh 作者能从当前 view取回该locator**。本轮最初“可达四步”的称谓过强，现予收窄。旧测试同样直接提供第二个fact_ref；只测已读回执未覆盖发现结果→下一工具参数的中间连接。下一修复须让已发现 refs 在适用快照下可见，同时防止新fetch/冲突后把旧比较资格当成当前事实；测试须仅使用前一真实请求可见的句柄，不从 Controller私有事实表补给答案。优先修可见性，保持原失败和预算。

另一次身份判断也已纠正：本地 canonical document_ref含CIK，但实际四份传输 messages已用匿名token替换。现有可逆transport会从 `cik_...` 提取numeric CIK；独立实际wire和缓存响应逆映射证实其生效，未为本案改alias或产品。不能把投影前视图当作已发送wire。

## 保存、重建与证据局限

[缓存操作重建](../runs/diagnostics/mining_taxonomy_consumer_20261023_v1/cache-reconstruction.json)从封存副本构造明确的临时 pending fixture：namespace重建两次读/停止；actual从第五请求准备前重放四个原缓存答，重建同一 blocked journal并再次在原预算停止。7次cache receive、0新交接，62非终态文件逐字节同，两个组装产物同，原64文件全部未变。这是受控操作重建，不是原完成stage重入、OS中断恢复或完整双环。

独立审查中，一个预算反例JSON被复验脚本意外覆盖。没有已知原字节副本；[覆盖说明](../runs/diagnostics/mining_taxonomy_consumer_20261023_v1/independent/stage-budget-original-overwrite-disclosure.json)区分历史tool stdout所留首失败字段与现有复验文件。不得声称原JSON字节保真；正式原件、四份预冻reference和生产原答未受影响。

旧财务消费者F9语义0/1、financial9、routing0/1和maturity strict0/1均不变。critic/Slow分类声明的canonical持久化仍等待此前[方案A/B](classification-context-persistence-proposal-20261023.md)决策，未推断批准。当前可继续修复比较locator跨action可见性；完整S3/S4、方向/magnitude发现→忠实实现→准入→后继复用、完整反馈与恢复、整体MVP仍未关闭。

`.githooks/pre-push` 已通过，随后亲读 `.lint-feedback/pre-push-last.log`：status0 / Lint result PASS。行政一致性检查未提升模块1/2或整体MVP结论。

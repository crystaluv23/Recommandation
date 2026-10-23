# v3封存预算边界独立诊断

**停止由单次完整请求上限触发。** 精确离线重建的下一请求需要 **264980**（既有bytes_plus_output口径），超过single_limit262144 **2836**。不是Mining总额或调用次数耗尽：10份唯一已答请求合计2055941，Mining总额12582912尚余10526971，calls_used=10/80；global同为10答/2055941，56MiB总额与728调用也未耗尽。下一请求若可提交的remaining_after=10261991、calls_remaining_after=69只是预算披露中的假设，不是新消费。

原stage的failure/completion均为`terminal_resource_or_control_stop / MiningRequestBudgetExhausted / Mining scoped request budget exhausted before prepare`。没有h011 inbox，不应恢复、advance、reenter或补一个终态答案。候选正控1仍未完成/0passed；consumer4均未尝试。没有mining-output、publication或Fast use产物，不把控制停止改称no-pattern或模型无能力。

## 精确重建与安全边界

仅在本诊断目录临时复制66MB workspace，用同一182份冻结代码、原inputs/factory/baseline/identities、263份原始document bindings及原生Engine→Controller→MiningAgentRoleModel重建。未调用sealed stage的advance、construct、prepare、submit或seal；未读取或改写oracle语义。原生Caller的估算、assignment、身份投影/原答反投影和budget gate保留。仅把最终provider/cache执行边界替换为只读前10份已保存原答；无fresh采样，不能作为模型新服从/研究效果证据。

每一轮到该边界时，重建的完整native projected messages、stage和output limit逐字等于该真实请求，实际request_hash亦验证；10轮全部对齐。原答经原生identity restore后由原生Controller执行，之后同一MiningRequestBudgetExhausted在prepare前发生。只捕获native estimator已经算出的would-be messages/payload，未调用新prepare或receive。socket连接及receive均有拒绝guard，provider执行边界不调用super。临时副本已删除，没有新stage、inbox、答复或actor通信。

`Budget.records()`独立核验10个request identity、原始inbox/outbox/receipt、transport hash、scope membership、完整messages+output reservation，并按hash唯一计数。全部仅属mining。成本依次为：

| 请求 | 唯一已答逻辑预留 |
|---|---:|
| h001–h007 | 90877、108402、111714、234074、246816、245898、247395 |
| h008 | 251665 |
| h009 | 258996 |
| h010 | 260104 |
| 合计 | **2055941** |

h010输入距single上限还余2040；执行其已有原答的read后，下一完整输入增加4876到264980。增量含正文工作页/last result/回执/计数字段，不等于新增正文token数。无h011真实wire或费用；264980为前10轮精确对齐后的原生离线估算，未计入已答总成本。

## 下一payload的可加总占比

下表是固定would-be messages中各top-level key+value经过外层JSON转义后的独占字节；不是“删掉此字段就有合法等价输入”的反事实。全部31字段的字节及相对完整请求/相对payload百分比分别在`cost-field-shares.json`，可精确加总为264980。

| 字段/部分 | 贡献 | 完整成本占比 |
|---|---:|---:|
| known_fact_refs（2879） | 74875 | 28.2568% |
| known_relation_refs（1342） | 40285 | 15.2030% |
| catalog_observations（4 whole responses，全入选） | 27221 | 10.2729% |
| slow_method_memory | 23500 | 8.8686% |
| narrative_read_evidence（5 whole units，全入选） | 13917 | 5.2521% |
| evidence_digest | 12107 | 4.5690% |
| meta_memory_disclosures | 11193 | 4.2241% |
| meta_info | 9428 | 3.5580% |
| signal_catalog | 8674 | 3.2735% |
| backlog_needs | 7477 | 2.8217% |
| measurable_evidence_manifest | 5696 | 2.1496% |
| last_action_result | 3455 | 1.3039% |
| narrative_read_progress | 2170 | 0.8189% |
| 系统内容（转义后） | 16017 | 6.0446% |
| output reservation | 4000 | 1.5095% |

payload编码内容共244902（含32bytes braces/commas），系统16017、message envelope61、output4000，加总264980。其余小字段不省略出证，在完整JSON中列明。这里没有触发catalog8/32000或正文12/40000的局部whole-unit淘汰；触发的是所有合法可见字段叠加后的完整角色请求gate。

v3 query=null/max_documents32生成2879facts/1342relations；v2 targeted query生成2088/952。两类known refs在本次占115160（43.4599%），正文、whole目录、memory及重复last result/首页同时贡献实际上下文。source选择、完整payload和fresh原答不同，不能据此推导v2总成本更优、修复致因果效率改善或某字段应被删掉。

h009读取的case005风险窗口讨论亏损/going-concern，h010原答明确承认它没有建立ICFR weakness或其缺席，再选381224/4000继续read。离线下一view真实执行了这份已有原答，得到相邻宏观/融资风险文本；未生成新答案。该行为不证明ICFR无法获取或模型能力不存在。目录43章节只显24/后段不可分页的接口事实由另一独立source审查处理，本轮不重复扩大源审。

## 封存与下一最小检查

完整stage **316个文件**检查前后集合及sha全部相同，其中completion封存的312文件全匹配；completion sha为`9f79f2d634fd9b07a3e9e90a334c28c2e187685d39d7ceae161ee5a81c9eb32b`。新增inbox/receipt/原答0。业务last_completed_round=0、last_completed_cycle=0、active_cycle=null及其文件hash不变。182 code sha在起止均对应manifest，263原source文件在最终readback均对应manifest。原stage/failure/completion/答案不改；网络/API0，host tokens/费用未测量。

下一最小检查只需沿这份已精确绑定的离线payload，回答“下一合法研究动作必须同时可见哪些完整信息、哪些handle/重复投影可有边界地呈现，且不削弱source/case/PIT/身份/Signal覆盖/未知状态和已读正文保真”。把该必要性证明与并行目录可达性审查合并后，再提出具体方案；不预先选删字段、加cap、新机制或启动v4。当前已封存运行保持终止，候选与consumer验收保持未完成。

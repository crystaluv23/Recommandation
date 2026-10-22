# Mining 比较定位关系：当前请求可达与快照失效

本轮关闭的是 **S3/S4 材料消费路径中的局部定位缺口**：执行比较后，下一次模型请求仍可找到对应概念的 current/prior fact_ref；事实图、分组或研究轴变化时，旧比较资格失效。没有新生产作者回答，旧预冻两控 **1/2** 不变，整体 MVP 未关闭。外部 API、GET、新业务标签、候选、发布与业务指针变化均0。

## 原失败与这次区分

[原正式两控](mining-taxonomy-consumer-20261023.md)的 actual 作者在读取 current 后看不到 prior 与 OCF/可比期间的映射，谨慎地重新比较，最终第五请求被原98304累计预算阻断。prior ref 仍在19个不透明 known_fact_refs 中，不能据此认定其可定位。此前脚本在请求外保存了第二个 ref，只证明给定动作下的预算，漏验了下一步动作的真实输入来源。

本轮只读复用原1780来源视图和已有 opaque Discovery 分组/时点；没有重入原 stage、提供第五回答、重置预算或改变原 oracle。原0671为 **CIK0000800457/DGICA** 的2011年历史 SEC normalized fact 文档；snapshot目录名含GPRE不代表该文档的公司。它不是2025最新资料、完整发现集或原始申报正文真实性的独立审计。

## 改动与边界

先修改 owning spec，再实现 `comparison_progress`，保留实际执行过的比较。每 concept 是完整单元，含两组 case_count、available_cases、latest、comparable_prior、unresolved_basis_cases；同概念只保留最新执行，按最近比较优先，同次动作按概念名排序。最多12个完整单元、items最多8000 UTF-8 JSON字节，遗漏和超大概念/所需大小显式列出；已有 compare_groups 可按普通 heavy 成本刷新。

每单元绑定实际计算时已抓取的完整 canonical fact 图、runtime group map和research axis。计算前后图不同则在接纳 last_result/ledger/预算前拒绝；后来变化时，working view 同时隐藏 progress 和 last_action_result 中的旧比较内容，只显示失效/刷新提示。重新比较新图时清除旧代单元。幂等抓取、插入顺序、正文读取和工具计数不改变资格。

view 只选择已执行结果，不重新计算、不增加 read proof或自动配对、不改变 canonical Fact/ledger/hash/工具/measurement 定义。旧 namespace/unknown 仍无自动可比 pair；显式同案通用算术仍合法，不新增“必须算1.2”之类模型义务。新增视图和提示均进入原生字节预算和既有可逆身份投影。

## 实际请求证据

[专用脚本](../runs/diagnostics/mining_comparison_locators_20261023_v1/capture-view-only.py)仅在新诊断目录做 input-only request_ready 捕获，0 inbox/receive/作者回答。每次选择器只拿**当条实际 user JSON payload**；不读取 controller._facts、旧请求、先前 Python ref 或 oracle。四步为 compare→读一个 operand→从新请求定位另一个 operand→截获停止意图；没有执行 domain terminal。

| 顺序 | 四次逻辑预留（message bytes + output reserve） | 总量 / 原上限 |
| --- | --- | --- |
| current先读 | 21400 / 22764 / 25938 / 27539 | 97641 / 98304 |
| prior先读 | 21400 / 22764 / 25854 / 27581 | 97599 / 98304 |

两条各4个输入，heavy_used均4（含受控fetch），单请求均小于32768、decision上限仍6。最后请求含两份完整已读 operand 回执。**余量只有663/705**，不能推定任意作者路径都能完成，不能据此加预算。源1785文件绑定与5个直接脚本/产品绑定前后未漂移。

使用精确旧提交341b94a5的 controller，实际 source compare→首读后，同一 view-only选择器无法再定位第二 operand，构成旧版失败反例。正反顺序分别从新 controller 重建，最终 view及ledger逐字节相同；这是**确定性 action 重建**，不是 cached LLM接收、OS中断或完整研究恢复。见 [原生结果](../runs/diagnostics/mining_comparison_locators_20261023_v1/native-view-only/result.json)。

诊断脚本初版身份字符串列表误沿用snapshot目录名中的GPRE/Green Plains；这两项检查不支持本源身份结论。原脚本与绑定保留，独立终核另按原0671 metadata的DGICA、实际CIK/case ID复核全部wire。CIK/full ID原检查有效，没有生产作者收到本轮任何请求；不把canonical prewire的CIK称为已发送泄漏。

## 验证与剩余工作

- 273项关联测试通过，116个被测文件绑定前后一致，网络tripwire0。包含只凭当前实际role adapter payload选下一operand、两读取顺序、完整双组/空/冲突分支、重复/排序、8种上下文变化、失效双副本、计算中变化原子拒绝、deepcopy、幂等fetch、Unicode超大项/分页及确定性重建。
- 独立预审先冻结T01–T11，再验证8组 controller反例和namespace/legacy通用算术权限；另终核实际wire、预算、来源/代码绑定、正反重建和身份检查边界。审查文件在 [independent目录](../runs/diagnostics/mining_comparison_locators_20261023_v1/independent)。所有新证据使用新目录/新文件，未覆盖旧失败。
- 独立artifact审查v1误按通用12-heavy默认值断言，实际stage为6，在自身断言处停止；保留v1脚本，新v2按实际剩余2验收，没有覆盖原文件或把该harness错误称作产品失败。见 [独立终核](../runs/diagnostics/mining_comparison_locators_20261023_v1/independent/native-view-only-final-review.json)。
- 本次只证明局部生产连接的离线可达，不证明fresh作者消费、跨组研究、候选/准入/后继复用、完整S3/S4或预测收益。原namespace首次endpoint通过、actual原预算终态及1/2分母保持。

下一步值得做的是在**真正不同且预先冻结的合格来源控制**上验证fresh角色；先核定义、独立源义务、当前wire可达性和资源边界，再把 exact inbox/outbox交给独立subagent，禁止把原actual改名续答求通过。完整 Fast/Slow 运行前提仍未满足，不启动完整后继。Critic/Slow canonical分类声明持久化仍等既有A/B选择，本轮不改该schema。

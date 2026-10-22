# ICFR原生能力链：引用前提修复与冻结驱动

本轮验收对象为S4已读证据→S5忠实实现→S7技术准入→四案原生Fast诊断消费；不是完整Slow/Fast提交或收益实验。外部LLM API/网络/GET/新业务label为0，LLM节点只允许全新独立subagent读取exact native inbox并写raw outbox。

## 为什么需要这次修复

上轮whole-unit交接已能保留完整读窗，但原Mining正常提示仍允许headline/attribute比较支撑candidate，S4 gate只要求读过任意叙事来源。因此读A后引用未读B、同一文档另一个case的event、隐藏/空白窗、混合已读与未读引用仍可接受，直到S5才缺证据。此前检查止于交接payload，没有覆盖初始声明与候选接受之间的前提矛盾。

先更新owning spec，再用同一materialization_evidence单向接口核每个引用的document/hash/case及非空实际可读窗；失败发生在候选、ledger和sink改变之前，要求read_span后再提出。匹配document读取可支撑event或direct document引用；normal prompt同步明确这两种原有合法引用。不改schema、研究定义、分类语义或typed权限。

## 独立证据与边界

[独立审查](../runs/diagnostics/icfr_native_capability_20261023_v1/independent-review/review.md)用独立构造的六拒绝、三合法及一个刻意不受语义支持的控制，对照原f9904bd5和新Controller：旧六项误放、新六项拒绝，合法路径保留。另两document路径在最后prompt版本下补验。各批hash分别绑定，不将早期证据归给后改版本。假设性材料仍可通过access gate，说明此门只证明正确来源被读，不证明候选含义或方向成立。原harness把整份RawInfo构造成纯空白被拒的错误已留档。

## 新诊断驱动

[owning spec](../spec/scripts/run_icfr_native_capability_stage.md)和[driver](../scripts/run_icfr_native_capability_stage.py)串接真实双seed Controller、原seed证据与native materializer、真实fixture运行/候选staging、独立语义review、native技术校验/原子发布，以及完整新Registry的自主检索/apply/Reflect/final context。只复用已有接受prefix，不重答S1/S2。保留263源、18原版本、265 backlog和六memory披露。新workspace零业务指针、无旧active状态；不调用effect或制造committed use。

新诊断host上限单请求262144，Mining共享80请求/12MiB，每自然候选S5/S7共享300/16MiB（至多双seed两个候选），四Fast各12/3MiB，合计728/56MiB。预算在准确下一whole request进入receive前检查，submitted malformed/identity答计费，pending不当answered；实际tokens/费用未知。原终态0/2与1/2不重入或加额度。独立review发现显式0预算被or覆盖、input-only可越过无请求的发布/终态，两处已修并作定向入口检查。

私有oracle在生产作者之前冻结，保留原v1全文及修订说明。四案保留真实弱点、相反结论、假设/缺管理评估和术语冲突；候选自己的不可变定义决定消费预期，不硬套未见候选枚举。作者看不到oracle、定位或答案。诊断S8不冒称业务提交。

## 当前关闭范围

最终440关联测试全部通过，测试前后绑定一致、网络0，见associated-test-bindings-final.json及associated-tests-final.log。历史prefix权威检查另验证原firstwire/reviewed snapshot、完成回执中原始approved/factory/slow input/memory等六文件及原committed input hash，五种parseable输入漂移均拒；只冻结当前hash不能替代这项原授权校验。实际stage进展见当前status。离线通过仅关闭本次引用前提和驱动边界问题；真实候选、忠实实现、准入、四案消费及全MVP仍需actual产物，未因脚本存在而关闭。canonical分类持久化A/B仍待原用户决策，与本轮独立工作分开。

## 真实阶段结果：停止调度但不伪造终态

代码checkpoint cbc9f1ab后真实prepare一次；263源/18版本/265needs及原prefix完整绑定，初次input-only在receive前捕获88063逻辑预留、0inbox。随后12个fresh fork_turns=none subagent各仅读当前exact inbox、写raw outbox，12首答/0纠错、12原生receipt、累计2001316逻辑预留；host tokens/费用未测量。没有外部LLM API、网络/GET、新业务label/check/LockedTest、候选、发布或Fast消费。第13个请求6fc59b…已准备，尚无作者、outbox或receipt。

[独立固定10请求审查](../runs/diagnostics/icfr_native_capability_20261023_v1/stage/actual-read-frontier/report.md)确认首个实际断点：case003读窗A/B及case002读窗C只各进入紧接一次last_action_result；h009两旧正文均无、h010只见C，既有两窗完整回执却未遗漏。匿名ID跨wire变化，按case/content hash/raw range对齐。运行时/S5仍保全部readable_text，故不是持久化或交接再裁剪，而是S4可见投影只保metadata。当前公开tool contracts没有同时带回两个narrative正文的动作。必要续页、合理回读和更佳来源选择分别保留判断；审查不据重复直接判Mining能力失败，未读h011及以后。父另外两原答继续请求原生窗口，不改该独立集合。

[Parent控制停止记录](../runs/diagnostics/icfr_native_capability_20261023_v1/parent-control-stop.json)在h013之前停止更多盲调度。原stage仍pending，不造completion/failure/no-pattern，不报预算耗尽：候选正控1尚未完成/0通过，四消费者均未尝试。182份实际冻结runtime/spec/driver/test全文已归档并逐文件读回/hash核同，含原有未提交spec差异；只证明版本保留，不是OS恢复。12原答/接收/工具结果和冻结原件均保留。下一修复此通用跨步正文可见性，先owning spec、反例/真实原答复验，再在明确新代码合同下继续完整能力验收；禁止热改或重答此冻结pending请求。此前local gate/driver测试不证明这一真实规划链，旧失败分母与整体MVP保持open。

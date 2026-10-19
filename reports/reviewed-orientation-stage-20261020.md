# Native orientation 有界阶段

本批只冻结1个原生proposer和3个H_init：h01必须消费p01精确accepted Plan，h02
使用默认Plan及新ENB三SEC，h03默认Plan/BMBL早cutoff周期报告不足。独立预期在
任何新答案前写入reviewed-orientation-stage-expectations-20261020.json；不作
Signal/Predictor、标签、score、trajectory、Fast提交或Slow来源。正式四个节点均已原生接受，独立语义窄审已通过，系统误拒保留。

源由既有两份reviewed input manifest恢复，完整Registry/version/hash/learning/files
冻结。p01人工seed仅operating+market及默认H技能，没有虚构fitness/PlanRecord；
meta_info为空，声明的sec_filing/prices与真实filing/market路由兼容。生产默认
DEFAULT_EVOLUTION_PRIORS.propose_plan原字冻结后使用，不使用初稿简化prior。
实际可选action由原nativeproposer决定；h01不补action或改H技能来满足oracle。

H_init运行真实execute_information_plan bootstrap：shared compiler/resolver、投影、
价格anchor、price_shape180和文档provider均由core产生。薄resolver保存原bundle，
controller只委托nativeinitialize，保存原AgentStep后用原_consume_model_step
核真实usage，才抛InitialBoundary。若预算拒绝，保留parsed原答但不标accepted。
后继routing/Reflect/Signal/Predictor/sink/truth为tripwire，未造trajectory。
H_init原生没有渐进文档读协议；不能把core设置provider说成发生read。

新共享call ceiling24、单request131072 native reservation units（messages bytes+
outputreserve），request_ready在receive前硬查；另有真实case256000/max8-call
预算，禁止拆开或热增。原生proposer最多3次memory交互，role/parser/transport
纠错规则原样且每个实际exchange计24。宿主tokens/cost/精确模型版本仍null，
外部LLM和新资料请求0。24×131072仅保守逻辑上界，不是实耗或付费授权。

初版预检和开发测试暴露：误将unfinished队列交completed-only verifier、events
数组用object reader，以及p01持久化失败后临时Plan仍可授权h01。当前均已修：
未完成请求由原nativeclient继续，完成后严格验证完整响应/immutable map；events
显式数组；只有save_exact成功才绑定Plan，terminal proposer失败明确blocked_by_proposer，
pending为awaiting，不减3case分母。原v1开发预检保留，不冒称正式冻结/模型通过。

相关65项/42.674s通过；新6项实际core、nativeparser/receipt、budget和完成恢复通过，
测试使用临时离线答，不是fresh模型行为。生产prior/样本事件修正后的最终6项/2.303s通过。
最终v3预检位于runs/diagnostics/reviewed_orientation_preflight_20261020_v3：实际
p01/h02/h03分别19567/57939/35786units，重复resume所有文件hash全同、0答案。
h01请求只能在p01接受后确定，仍受冻结cap，无默认替代。代码22491605冻结后，
root独占派fresh41–45并submit，driver独占resume。

本批不宣称F1/F2/F3整体通过或MVP收敛；原8dirty、v182完成指针及已有prefix/Posthoc
原件保持。新答案的每个事实、scope、单位/PIT、needs和source缺口需独立原材复核。

最后observer反例发现全局同型event去重丢样本归属；现按sample_id+原eventdict
保留观察顺序/deepcopy，不合并h02/h03，也不把replay event数当新物理调用。
root与独立reviewer最终v3分别核100currentcode、原件/Registry、三canonical请求与
inbox字节/匿名/生产prior/控制数据/正句和早gap及0答。该预检仅支持冻结，
v1/v2旧开发预检均保留；以下实际答案另行验收。

## 正式执行与恢复

正式root为`runs/diagnostics/reviewed_orientation_stage_20261020_v1`，manifest
`9fc5567749f3e12ce9fff084ce30fcb7cf541d3393fd2f3ec06560c253059c5c`。
1proposer+3H_init固定分母，5个隔离角色实际执行（四首答+唯一p01 typed纠错），
原答、请求、cache与actual agent receipt均保留。没有按events空数组抹去纠错。

p01首答使用合法闭合operating+market action，原生校验却误把“Decide only the
collection action, without deciding price direction...”当作越权方向决策。独立原失败
复现证实改成明确must-not禁令可过、肯定决策反例仍拒；该机械false-positive保留，
本冻结不热修。唯一纠错仅替换H_reflect，其余authored Plan字段不变，随后原生接受。
h01实际消费该精确Plan；三H_init均首答接受，没有默认Plan替换h01。

实际五请求分别19567、26020、57939、35786、60299 reservation units，总199611；
这是本地逻辑预算，host tokens/cost与精确模型版本未知。5inbox/receipt/cache均对应，
没有额外模型调用；外部LLM/新资料请求0、标签未读。实际bootstrap锚点由core计算：
h01 mean6.494/threshold12.988/recent6.3及price_shape180逐字段传入原请求。

完成后唯一completed resume的42个完整文件before/after SHA映射保存在正式
`execution_summary.json`，与completion及当前原件逐项相同；0新dispatch/receipt。
独立检查脚本与原材料对照位于v3预检目录的`independent/actual-orientation-checks.*`，
机械绑定和语义判断分别记录。独立语义判断回到实际可见原材，未以native accepted或引用hash替代。

独立最终审查保存于正式reserved `independent-review.json`：三H_init窄语义3/3，
1个原生proposer→exactPlan consumer连接成立。h01七引文/五needs保留晚期BMBL
恢复与恶化的竞争假说；h02六引文/五needs正确解释基础设施经营，未把重分类当增长，
未作CAD/USD算术；h03五引文/五needs保留周期报告不足、Q2forecast与缺prior，
未把gross savings当净利润、cash realized或上调方向。全部18引文逐一核实际wire、
canonical材料、期间/对象/单位/PIT，未补未来actual或声称缺口不存在。

这里只关闭声明的1+3例连接/初始状态/恢复子项；仍有局部guard false-positive，
不关整体F1/F2/F3、Signals履约、完整F10/Slow/完整MVP或收益。下一批只修该确定性
negation scope错误，不重写本批首拒/纠错/原状态；无需新增模型答来检验纯guard。

## 后续局部 guard 修复（非冻结 stage 重跑）

证据checkpoint e89f20b6之后，owning output-validation spec先明确局部否定scope，
仅H_reflect方向检测新增等长空格mask。合法without deciding/determining/judging/
classifying/concluding从句可过；句号/分号/newline/contrast/独立后续finite动词
不被豁免。not-without/not-only、外层do-not包住innerwithout决策、普通do-not后
另行then-decide均拒；price/share/stock简单复数与单数一致。共享prohibition regex
与其他consumer不变，原ontology scrub仍保留；不是一般英语否定语义证明。

旧red日志分别保留实际full-p01误拒、nestedwithout误放与plural两误放；新原生
proposer回放原41完整答可在首答直接接受、所有authored字段不改。204相关测试
8.402s通过，独立family与全module另有当前hash日志。本地回放不声称新的模型服从，
也不将原冻结首拒改成accepted；正式42文件恢复是原冻结代码时取得的证据，
当前源码变化后不以currentcode重新恢复该旧冻结。

末次负控审查还保留原有合法双禁令：or/nor协调及第二动词自带明确negative cue
不作为独立肯定决策；该正控修后204相关8.402s通过，之前candidate日志不冒充终版。

本轮最初只围绕without误拒看局部修复，漏测共享prohibition内嵌双重否定、
后续独立finite和原本合法双禁令，单数target也掩盖了复数漏放。终版同时保留
误拒/误放/旧合法正控，204相关及独立3+93通过；词法守卫仍有明确有限scope。

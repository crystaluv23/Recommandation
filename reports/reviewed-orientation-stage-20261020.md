# Native orientation 有界阶段

本批只冻结1个原生proposer和3个H_init：h01必须消费p01精确accepted Plan，h02
使用默认Plan及新ENB三SEC，h03默认Plan/BMBL早cutoff周期报告不足。独立预期在
任何新答案前写入reviewed-orientation-stage-expectations-20261020.json；不作
Signal/Predictor、标签、score、trajectory、Fast提交或Slow来源。正式答案尚0。

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
h01请求只能在p01接受后确定，仍受冻结cap，无默认替代。独立短审及lint后先checkpoint，
再新formal root，root独占派fresh41+并submit，driver独占resume。

本批不宣称F1/F2/F3整体通过或MVP收敛；原8dirty、v182完成指针及已有prefix/Posthoc
原件保持。新答案的每个事实、scope、单位/PIT、needs和source缺口需独立原材复核。

最后observer反例发现全局同型event去重丢样本归属；现按sample_id+原eventdict
保留观察顺序/deepcopy，不合并h02/h03，也不把replay event数当新物理调用。
root与独立reviewer最终v3分别核100currentcode、原件/Registry、三canonical请求与
inbox字节/匿名/生产prior/控制数据/正句和早gap及0答。h01仍awaiting，正式答案
尚待新root；检查仅支持冻结，不是已通过模型行为。v1/v2旧开发预检均保留。

# Mining v4：保原额度的新代码真实验收

当前为**因低信息增量而停止的隔离诊断**，不是 Fast round、完整 Slow 或工程 MVP 通过。
正式状态以 [stage progress](../runs/diagnostics/icfr_native_capability_20261023_v1/stage-v4/progress.json)
和[父控制停止记录](../runs/diagnostics/icfr_native_capability_20261023_v1/parent-control-stop-v4.json)为准；native保持pending，不伪造completion。所有生产角色走独立subagent；外部API、网络、新标签和业务指针推进均0。

## 已关闭的前提

此前 subagent 工具上限本次已实际恢复，独立审查者与生产作者均已启动。
[预算与恢复实现反例审查](../runs/diagnostics/mining_preserved_budget_20261023_v1/independent-implementation/review.md)
通过：独立重跑27项既有阶段测试，另17组真实 v3 前缀、双层 exact-fit/超限、无剩余 call、malformed 原答计费、重复不重扣、旧 root/symlink 与原件保真控制通过。
这只关闭原缺失的实现独立审查，不证明 Mining 能力。

[正式 v4 oracle](../runs/diagnostics/icfr_native_capability_20261023_v1/oracle-v4/acceptance-obligations.json)
先于新作者冻结；15项原始语义字段与三个旧版本严格相等，263源、18定义、dev8/分组/时间、265 needs、六披露、候选1与消费4分母不变。
[独立冻结审查](../runs/diagnostics/icfr_native_capability_20261023_v1/oracle-v4/oracle-review.md)
及父回读均核完整182文件源码归档；归档保存实际工作区字节，不仅依赖 Git revision。
冻结脚本首次混用了两种 JSON serializer 的 hash，preflight 在写 oracle/归档前停止；原失败保留，改为原算法与逐字段相等，没有改语义求 hash 一致。

旧三控制仍分别保留12/2,001,316、11/1,837,419、10/2,055,941；旧答/动作/cache 不导入。
v4继续扣原 v3 的10次/2,055,941，Mining原80/12MiB、global原728/56MiB、single262144不增；新 Mining 初始实余70/10,526,971。

## 实际请求与已核范围

[前四份真实请求审查](../runs/diagnostics/icfr_native_capability_20261023_v1/oracle-v4/actual-first-wires-review.md)
核前三原答→receipt→cache逐字、身份及成本同；h004实际 used=2,369,181=历史2,055,941+新313,240，calls13。
首页7卡及实际已查看两页7+4保留完整18个精确版本，query贯穿真实fetch；34导航坐标逐原文/PIT核真，显示8、遗漏26明确，未读导航不作证据。

[实际阅读保真审查](../runs/diagnostics/icfr_native_capability_20261023_v1/oracle-v4/actual-read-retention-review.md)
核两次原始3970161/4000、26191/696读取，原文slice、返回、ledger与跨query保留均同；h007仍有两段正文/对象/时间及18卡。
新旧65导航坐标逐原文核真，展示与遗漏明确。h006对封面404(b)问句、DCP有效和季度无重大ICFR变化的区分忠实，没有推成无重大弱点、ICFR有效或截止日现状。
该结论只覆盖实际读过的路径，不关闭完整F5、候选语义或全部来源真实性。

本检查点25份新原答已提交并原生接受，0模型纠错，新逻辑预留5,126,205；与历史合计35/7,182,146。
h026为当前新请求，不计已答。其实际输入显示browse7/heavy8/light0，Mining原总限12,582,912、single262,144未变。尚无候选实现、准入或消费者结果。

[后续23份固定前缀独立审查](../runs/diagnostics/icfr_native_capability_20261023_v1/oracle-v4/actual-later-wires-review.md)
核原答→receipt→native cache逐项同、旧债贯穿，及15个实际源窗、65个原坐标、每wire完整18卡。h024只作为第23动作的实际消费者，不当新答计费；父回读118份静态绑定全同。
该前缀末正文页12/15、backlog12/265，另3正文locator及253 needs遗漏均明确，不能称全文同时可见。缺陷等级、ICFR/DCP、审计程序/有日期意见及计划/完成整改区分忠实。
其后h025主动选择普通付费重读已省略的case001窗口，不计为独立新覆盖；该动作尚未由上述23份语义审查覆盖。
每次 CLI 推进均从原生缓存重建并校验相同历史消费；这不是 OS 中断恢复证明。

## 后续与限制

本策略现已停止，不再提交h027、重入v4或立即新建v5。源、旧答、原caps、分母和完整182文件归档保持；后续须先处理前提与资源债务，不能改名重置。
不向作者提供私有 oracle、预写候选、locator或建议动作；新缺陷先定位首次丢失，不能热改冻结代码。
无结果如实保留，不能把技术/预算终止称 no-pattern，不能追加调用求过。

Fast F1–F10 整体仍未通过；历史正文/时间、完整检索阅读、新代码实际路由、Predictor语义和提交后的Slow消费仍有未关闭项。
方向/magnitude完整链、committed S8、完整双环与必要恢复尚未验证，独立收益未知。

## 最终停止边界

[独立增量诊断](../runs/diagnostics/icfr_native_capability_20261023_v1/oracle-v4/reread-frontier-review.md)确认h025重复h008、h026重复h010的同源/hash/坐标整窗。每恢复一个旧窗，下一份被选择旧窗恰被挤出12/16工作页；16唯一窗口/9文档、2093facts/947relations/14events和候选0无新增。两回读耗478826逻辑预留。h027拟重复h011，仅raw、无receipt/cache/实际读取。

最终26新答/5367457，加旧债36/7423398，仍余44calls/5159514，**不是预算耗尽**。按AGENTS低信息增量条件停止当前逐窗回读策略；两次观察不证明无限循环、代码bug、第三次不可能综合或领域无模式。候选1未完成/0passed、消费者0/4未试，native pending、业务0/0，不能造no-pattern。

父回读25静态审查绑定、182代码与1481源绑定均同后保存完整前缀快照，随后才整合另行批准的代码。现转向已批准分类meta A及财务期间新定义；不恢复本次搜索或启动完整后继。上述25答为中途检查点。

# 已提交Signal使用的目标追踪（2026-10-02）

生产持续追踪已接通本地Fast提交、重启重建和hash核验后的历史导入，以及Slow实际source消费。这是完整目标的进一步进展；最新完整真实Fast/Slow周期、真实新方向/magnitude候选和独立幅度增益仍未验收。

## 定义及边界

因子是可复用测量，不是独立股票分类器。持续使用记录描述选中/执行/覆盖与后续outcome的关联；单案positive与暴涨同时出现不会变成supported。方向保留既有语义，额外target只读取已发布exact-version用途；无声明的历史版本不回填magnitude效果。

复用学习事件和SignalTargetEvaluation；新的committed-use协议与独立配对协议分别记账。有效测量为inconclusive（已观察、效果未验证），不可用为insufficient_evidence。技术执行失败仍保存在原trajectory/统计，不进入研究效果计数；其他阶段失败也不证明某测量无用。效果状态不因观察次数或均值变成validated。

每个目标身份绑定版本、物理观察键、target合同、测量状态/覆盖与真实outcome。不同Plan的选择理由分别留存，但相同测量共享目标记录；重启复用首次写入时间。目标批次先检查全部类型、引用和重复ID完整内容，再原子写JSONL；后部无效项或中断不能留下部分目标批次。学习事件重复ID与重复物理outcome同样检查完整内容，包括realized multiple。

research/signal_tracking.py提供目标人群内状态矩阵、物理观察/issuer数量、out-of-population、不可用/冲突、按状态的真实最大倍数均值及source hash。它们是selected-use观察，可能包含生成样本，不是独立收益研究。ge3只覆盖真实>=2x人群的>=3x/2–3x对比；不把非暴涨混入low，也不冒充10x专属因子。

## 实际接线及披露

PlanEvolution在round已提交后调用tracking；构造engine时从committed archive补齐缺失衍生。已核验的Slow-history与Fast-bootstrap导入使用同一桥接；staged attempts不产生效果证据。Slow frozen input加入有界signal_target_observation source，Update模板也收到截止当前committed round的目标使用摘要。明细learning source仍可审计。

实际消费发现并修复原source catalog把生产者manifest权限展开成所有角色的问题。新的共享catalog保留manifest的visible_to；processed ref不授予额外权限。H1方法视图省略隐蔽目标source、显式读请求拒绝；reflection/H3/E2/Update可读。新target source没有显式scope则拒绝，旧无manifest单位保留既有解释。未向盲Predictor添加目标结果。

## 验证

- 最终1430全量测试PASS（92.738秒），4项新追踪回归PASS；repository lint PASS。
- 新回归覆盖方向/magnitude用途隔离、跨Plan物理去重、target population边界、不可用、冲突状态排除、cutoff冻结、目标写入中断/重建、ID冲突原件不改，以及实际Slow H1/Update方法视图和source reader权限。
- 真实v168历史经原contract/pointer恢复2个已提交Plan，274条使用事件生成209条目标记录；193个物理观察，其中16个状态/覆盖冲突（目标记录保留各变体），14个无争议不可用。17个版本级观察摘要保持效果未验证。
- 冲突涉及 guidance_acceleration:v2（6）、customer_concentration:v2（4）、order_confirmation_disclosed:v2（2）、financing_listing_action:v3（4）。有同状态但coverage不同，也有状态不同；未将它们当作技术排除或独立反证。
- 重启新增0、记录逐字一致、Registry定义hash及源文件hash不改，外部调用0。完整目标记录、摘要、source/policy hashes见 `v168-committed-target-use-replay-20261002.json`。全部新写入仅在临时Registry副本。

此重放证明生产追踪、去重、恢复和来源边界，不能证明新版真实流程近零技术排除、模型抽取内容全正确或收益。接下来审查上述四类实际Signal输入/输出冲突，并推进新冻结周期，检查方向/magnitude真实新候选、后继使用和独立幅度对照；原固定标签/分母保持。

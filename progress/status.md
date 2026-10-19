# 当前状态

更新：2026-10-19。本轮目标为用户批准的
[Fast/Slow 工程 MVP](../spec/engineering-mvp.md)，**尚未收敛，继续迭代**。
独立预测收益属于后续里程碑，仍未验证。用户要求生产 LLM 位置由独立 subagent
处理；外部 LLM 调用保持零，用户现允许只读公开资料取证。新资料请求单独计数，
不热加入已冻结输入；未恢复旧目标或完整付费运行。

当前修复批次最终 1770 全量通过；首轮 1768/1769 的 critic payload 预算回归及原尺寸
保留。仅最后 wire 改为同 payload 可逆 profiles，全部字段/IDs 保真，原预算不变。

## 新证据：F7 范围通过，F8 新消费时间边界已修

[v3 报告](../reports/local-role-mvp-v3-stage-acceptance-20261019.md)、
[冻结七样本与原始结果](../runs/diagnostics/local_roles_mvp_20261019_v3/progress.json)、
[独立范围审查](../runs/diagnostics/local_roles_mvp_20261019_v3/independent-review.json)。
显式 `independent-subagent` 后端保留原生产请求、匿名投影、parser、typed 纠错、
fallback、持久化及精确消费者；13 条新请求均由隔离角色实际回答，原答/角色身份/hash
绑定保存，内部成本与实测 token 用量未知，无 logprobs。

- v3 七个合法 prior 的 accepted state 回答范围/残留均正确，三个消费者处置精确保真。
  13 个独立角色：7 首答、1 次仅修 evidence 形状的 typed 纠错、5 后续 terminal；
  首答结构 6/7，最终机械 7/7；F7 这一冻结范围通过独立审查。
- **旧 v3 F8 未通过**：future_actual 故障注入虽未被 state 采纳，未来实绩摘要仍进入
  final/posthoc/critic，最初 Reflect 请求也可见。正常 F6 校验会拒绝该 timestamp；
  这是绕过 F6 后 serialized/staged result 的模型消费边界缺防线，不是 F6 已证漏放。
- [新确定性边界诊断](../reports/signal-model-pit-boundary-20261019.md)：同一原件在
  Reflect/final/posthoc/critic/直接 Predictor 五入口均 typed 拒绝，负控零 inbox。
  六个合法样本消费者仍保真，合法 forecast 可进入原 Predictor caller 待处理；
  不重调角色，未证明新预测行为。原 v3 原件/结果不变，来源正文可信仍未关闭。
- [旧 v2](../reports/local-role-mvp-stage-acceptance-20261019.md) 固定七分母仍 2 机械通过、
  5 失败，原件/原答/旧结果均保留。新 v3 结果不能改写旧失败，也不能证明所有消费者安全。

最新 1770 项全量离线测试通过；本批 188 聚焦、包装后 117 同源检查通过；
market/旧 SEC 21 项聚焦及独立 27 固定案、
null/alias 反例均通过；H_init 先前 117 项相关检查通过。Lint 通过且已亲读 feedback。
并发预算/cache 原答复核与 F8 本地证据时间守卫已修；这些局部机械边界不能替代
完整运行、模型行为或源码/输入全域语义验收。

## 窄来源准入与下一批次

已实现并实跑[四来源 view](../reports/reviewed-source-snapshot-20261019.md)：2 SEC admitted、
1 污染 news excluded、1 transcript unknown；窄冻结→生产 loader→worker snapshot→resolver
恢复均精确保留集合。完整 48 案 prepare 仍缺 16 个 anchor 而失败，未缩分母/要求。
零新模型调用，原件不变；全库来源可信仍未关闭。下一步核查本地 market 原始请求/响应、
issuer 与调整时点证明；不足则先做可执行 SEC 检索/Signal stage，不造 baseline。
保留本批失败。后续按可信输入→检索阅读→Signal→Reflect
→Slow→后继→恢复推进。

新 [market proof view](../reports/reviewed-market-snapshot-20261019.md) 经独立反例审窄通过：
固定 5 原件，现 3 admitted（2 SEC+原 market 250），1 excluded/1 unknown；旧 view
与原件不变。生产 parser/adapter 全对象重建、issuer/全类型 split ledger、双 clock、
分页/参数/价格/恢复均核，optional 235 不是逐行重复下载门槛。实际 UTC baseline helper
算出 6.494；没有手填价格或新 HTTP/模型调用。12 旧 falsey pagination 漏放已修，
独立 27 固定案与 null/alias 反例通过。
[新确定性依赖修复](../reports/daily-market-consumer-boundaries-20261019.md) 已独立窄验：
同一 aware instant 四个日线入口统一 UTC 日；BasicInfo 两层遗漏保留到实际
Predictor、posthoc 两入口与 critic wire。旧有损 index 可从同轨迹 canonical bundle
恢复已知遗漏，模型仍只见部分 45d，未声称全读。另修 review scope 晚于 source
availability 时 split proof 漏覆盖最早 consumer 的泛化假设；原 BMBL 资格不变，
两个旧 gap 反例新拒，精确/更大覆盖区间合法。local judge+JEV 及 caller 显式禁外部
执行现于 provider 构造前 typed 拒绝；合法 remotejudge/localproposer hybrid 保留。
全部原失败保留，零新角色答/资料请求；这些是守卫而非新模型行为或完整 readiness。
[3 次只读资料取证](../reports/bmbl-market-readonly-proof-review-20261019.md) 与零外部 LLM
分开计数。ENB 新 [候选原材](../reports/enb-source-candidates-20261019.json) 只留后继准备，
未加入这 5 原件或当前 view，未扩大 issuer/期间分母。
[三样本 direct SEC stage](../reports/reviewed-signal-stage-20261019.md) 已实际完成：
7 个新隔离角色，3/3 窄语义通过。customer 正控及实际 full Reflect 保真；早 cutoff
和缺 prior 两例经生产守卫保留 need，零伪 Reflect；guidance categorical 边界仍未决。
[默认 BasicInfo→H_init 双 cutoff](../reports/reviewed-initial-stage-20261019.md) 又有 2 个
独立首答，2/2 经原材/全部 11 needs 独立审查窄通过，零纠错。晚时点 19/24 部分投影、
早时点 6/6 投影和三类 DataGap 均保留；有条件假说不冒称收益/market expectations。
F2 经营背景目标与 generic filing 可执行覆盖脱节仍 open；8-K 本身是合法来源。
两次 completed resume 的 16 产物完整 before/after hash 不变，零新请求/receipt。
本批不加 anchor/label，不进 evaluator/Predictor；94 code/2 原文件绑定及嵌套来源
proof 保持。1744 全量、117 相关检查通过。下一步先补 runtime-owned 停止元数据，
再冻结 execute_information_plan 到 prediction_sink 的真实盲前缀；读标签前专用边界
停止，不依赖 observer 注入，不把前缀称为完成 Fast。

用户已选择[完整公开会议内容时间口径](../reports/transcript-availability-policy-review-20261007.md)，
owning spec 已同步；[26 份原件清单](../reports/transcript-proof-inventory-20261019.json)
全部保留，完整公开时间证明仍 0/26。四条旧 preview 不是已验证替换输入，未写 oracle。
历史新闻 producer 旧发布日期对应后来正文的家族仍未全局修复；只有本次精确版本在
reviewed view 排除，完整来源可信验收未通过。

## 旧运行与未完成能力

v182 Fast/Slow 权威完成指针仍 1/1，已完成，未热改或重启。
[旧终态审计](../reports/v182-terminal-slow-and-source-partition-audit-20261007.md)：
Slow memory failed、0 processed、3518 pending；magnitude 候选/验证/发布为 0，方向
v3 的后继实际使用未验证。48 案内容验收未全完成，不能声明完整 MVP 或独立收益。
[上一轮远程 Reflect 0/2 失败](../reports/v182-answer-scope-stage-acceptance-20261019.md)
保留原结果；本轮独立角色行为不是旧供应商模型已修好的证据。

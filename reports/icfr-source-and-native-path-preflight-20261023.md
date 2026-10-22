# ICFR 历史来源与完整原生路径前提

2026-10-23，承接 `8612172b` 的 S4→S5 证据交接修复。本轮只核下一能力正控的
来源、实际入口与资源归属，未派生产作者或启动完整后继。外部 API/GET/网络、新
业务标签、check/LockedTest、新候选/发布/业务指针均为0。

[独立来源审查](../runs/diagnostics/icfr_native_capability_20261023_v1/source-review/source-review.md)
直接核四份原始申报、SEC submissions cache、三份精确 Archive body cache，及
1768 原 HTTP200/gzip 响应。CIK、accession、primaryDocument、申报类型/期间和
acceptance 均对应；published/available 与 acceptance 相同，且早于各案 cutoff。
[主审反核](../runs/diagnostics/icfr_native_capability_20261023_v1/source-review/root-counterreview.json)
再从 raw DEI 和引用窗口确认对象，未扩大结论。

这是四份**精确历史申报对象的本地来源绑定**，不是独立取得了历史同时点逐字快照。
未观察到正文后来更新的矛盾；2026 抓取不自动构成污染，hash 也不证明时间真实性。
1768 的 Last-Modified 在申报同日，只是额外佐证。来源资格不等于最新 ICFR 真值。

- 1507：明确 ICFR 重大缺陷及本报告期未修复，评估日期不能改成预测 cutoff。
- 1500：明确截至2024-12-31没有构成重大缺陷的控制缺陷，不外推到2025-07-31。
- 1501：风险标题是 may experience；管理层另明确因 transition 未提供评估，不能
  用标题认定已有弱点，也不能从没有肯定句推定没有弱点。
- 1768：原文同时使用 significant deficiencies/material weaknesses，属于原材料
  内的术语冲突，不通过删句或重命名化解。

[原生路径审查](../runs/diagnostics/icfr_native_capability_20261023_v1/path-review/path-review.md)
实际构造双 seed axis/factory/role/transport，保留263来源、exact stable18、完整265
backlog、已接受的记忆与六份来源披露；只复用已验前缀，没有新 source-selection 答案。
八次 request_ready 输入捕获均在 receive/inbox 前停止，作者/receipt为0。

| 首请求逻辑估算（UTF-8 messages bytes + 4000 output allowance） | H | D |
| --- | ---: | ---: |
| 原生 | 86712 | 77904 |
| 加范围指派 | 87249 | 78441 |
| 显式单次262144上限及范围指派 | 87659 | 78851 |

这些是已准备输入的成本，不是实际 host tokens/费用。首屏7/18卡、12/265 needs，
未显示内容仍可寻址。按12项自动 pending 页推进约需23批，是页宽下的估计，不证明
语义工作充分或能在该步数结束。旧98304 fact-module 总额不能支撑这条完整链，旧
超限终态仍保持；以上262144仅是独立预检参数，尚未成为生产实验预算。

可采用的新控制组合已具体到原生函数：`_run_controller_mining_axis` 双seed →
原生 spec/skill/tests 与真实 fixture 执行 → 同一 technical validation/admission/
atomic promotion → 新完整 Registry 的真实 Fast route/apply/Reflect/final context。
不调用完整 `run_cycle` 重跑 S1/S2/update/check，不手写候选替代 Mining。
每个新模块须先核完整实际请求；H1 单次额度不默传给 S5，Fast case 余量另算。
未来候选、skill、tests 数量和尺寸尚未知，审查给出的80/300/8调用与12/16/2MiB
分层资源方案是候选方案，不能写成用户已批准或已冻结的实验合同。

重要限制：S8的未评分诊断 use manifest 不冒充 pointer-reachable committed learning
event。它可以证明精确版本实际消费，不能关闭业务 use-record/评分/完整双环。
`SignalValue.positive` 仍服从现行研究轴方向；不能把它重新定义为任意“谓词出现”。
范围指派仅给 ICFR 源族，不给测量定义、源定位、分类答案或 oracle。候选产生后须
独立检查定义、方向及假设/缺评估/术语冲突的处理，再判断是否忠实实施；接口能表达
这些区别不等于新模型已经做到。独立报告中的 predicate-class 表述不授予改义权限。

预检 harness 的 `Captured` 是普通异常，为抓两个首输入被 axis 记作诊断 failure；
它不是新业务失败或通过。复制旧 active 状态仅用于0作者预检，新实跑必须建合法
独立合同/状态并正常传播 pending/control-flow。原 probe 的 definition 循环没有验证，
后续独立311 binding及[主审直接复核](../runs/diagnostics/icfr_native_capability_20261023_v1/path-review/root-counterreview.json)
补核原件与输入成本；这些补核不篡改原 probe 或其证据层。
[最终主审绑定检查](../runs/diagnostics/icfr_native_capability_20261023_v1/path-review/root-final-bindings-check.json)
确认310项仍同，仅完成预检后的 status 文档更新不同，原冻结记录保留。
[最终lint](../runs/diagnostics/icfr_native_capability_20261023_v1/pre-push-final.log)通过，
已亲读反馈；首次因 status 超100行失败，保原日志后合并现有状态行，未改业务或运行。

本轮排除了“仅因后来抓取就不可用”“只能再做一个 fact endpoint”“旧模块额度
足以覆盖完整候选链”三种解释。无需继续扩大源搜索或补词面规则。下一步写新控制
的 owning spec/driver，冻结分层预算、四个源语义控制和完整链验收，再由 exact
inbox/outbox fresh subagent 串行运行。旧0/2、1/2及工程 MVP open 均保持。

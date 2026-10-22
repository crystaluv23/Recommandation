# Prospective ICFR oracle-v2 review

本次只写新 `oracle-v2/`，未改原 oracle、stage、答案、code 或 spec，未提交。冻结时 `stage-v2` 尚不存在，未读取新候选/消费者输出；旧作者正文只作为文件哈希校验的opaque bytes，不解析或采纳。外部API/网络均0。

## 语义保持

从原 `oracle/acceptance-obligations.json` revision2深拷贝，新freeze_revision=3。仅更新冻结时点、revision和当前contract_bindings，另追加前轮停止/归档绑定及prospective_revision。**除这三个元数据字段外，原文件每一个已有key都deep-equal**，包括source_material、source_scope、research_semantics、novelty_baseline、fixed_denominators、pipeline_positive_control、consumer_controls、counterexample_rejection_rules、stage_spec_review、scope_limits及原prospective_boundary/校准记录。

受保护子集canonical JSON哈希：

| 对象 | SHA256 |
| --- | --- |
| old protected semantics | `4951c16c4d3cb976595e0ca12d16388fb13b85e7096fc34831e728ab55914429` |
| new protected semantics | `4951c16c4d3cb976595e0ca12d16388fb13b85e7096fc34831e728ab55914429` |
| 原oracle完整字节 | `9fec7af60c3b34c8c10139504fae9199286eaf6179cf39ef2d012fbdf2855aa5` |
| 新oracle完整字节 | `e650fb4f73bc5067ee29193328cd3d091dd3b52e4d3c62e5ed095399000ec0d9` |

逐key canonical哈希、完整protected key清单和原字节保持校验见 `equivalence-evidence.json`。来源证据原hash当前实际文件也匹配：source_material `957c97fb081d42120ede3a464da57ab10bcfe1913fb5a7c7f066b76976fce41f`；source_review `951c069e4698e6921274a008bbd4bbc0f7afbf2cb636285dd385e7672f28a01f`。这只固定已审的来源链，未把本地历史filing绑定升级为contemporaneous remote attestation。

## 当前spec具体审查

将当前stage spec与前轮frozen-runtime归档内的精确spec直接diff：只新增stage-v2隔离、父停止收据/旧文件映射/archive/未答h013核对、禁复用旧答案cache、保留旧分母并前瞻冻oracle的段落。`Resources and real roles`及其后native phases全部与归档逐字相同。原global728/56MiB、Mining80/12MiB、每candidate300/16MiB、每Fast12/3MiB、单请求262144+实际output、fixture12及portfolio4/2均未变；263源、stable18、完整265backlog、六披露/dev8/group义务保持。

owning Mining spec新内容是 `narrative_read_evidence` 工作页：只取已执行/同scope/同hash的完整正文单元，按最近读最多12单元/40,000 UTF-8 JSON bytes，保留omission与收费revisit，身份投影与完整请求预算仍生效。**新增可见正文页有明确输入视图空间上限，但未增加单次/累计/调用/源读取额度，也未改变研究对象、candidate/SignalValue/准入语义。** 它修正文被后续action视图替换的接口缺口，不证明新作者会正确使用。两份原对current差异完整保存在 `stage-spec.diff.gz`、`mining-view-spec.diff.gz`；实现/codehash及fresh能力验收仍由新stage另冻另验。

## 前轮绑定与分母

`predecessor_bindings`精确绑定 `parent-control-stop.json` 与其 `frozen-runtime-cbc9f1ab.tar.gz`；archive实际sha与receipt相同。还逐一校验receipt记录的**336**旧stage文件原hash，0不符，未改任何旧文件。收据记录旧stage pending，12实际答/2,001,316逻辑reservation，h013未派未答，非budget-exhausted/非完成；旧candidate1未完成、consumer4未尝试全部保留。此处未解析旧作者语义或重新计算receipt计费，新driver prepare/verify仍须自行执行旧mapping/archive/h013及原12计费检查。

新分母仍独立pipeline1/consumer4；不是清零旧分母、接着旧cache补答或降低要求。不预写候选/枚举映射；允许既定合法binary和reasonable scope，但全unknown不算完整正控。仍需fresh真实Mining→忠实实现→native技术准入→精确新版本真实Fast/Reflect/context诊断消费。无effect/committed round声明，不关闭magnitude、完整双环或全MVP。

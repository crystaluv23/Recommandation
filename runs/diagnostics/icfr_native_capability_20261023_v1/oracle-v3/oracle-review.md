# ICFR oracle-v3 prospective freeze

已在父明确两次“源码稳定可冻”、最终driver pending-progress补充完成后冻结，freeze_revision=4。冻结时stage-v3不存在，无v3作者/消费者答案；未联系actor、未读新标签。只写新oracle-v3目录，未改旧oracle/stage/stop、code/spec或生产答案，未提交。API/网络/GET均0。

## 原语义逐字段保持

original revision2、oracle-v2、oracle-v3受保护原有字段全部deep-equal，canonical SHA256均为：

`4951c16c4d3cb976595e0ca12d16388fb13b85e7096fc34831e728ab55914429`

原v2到v3仅变 `frozen_at_utc, contract_bindings, freeze_revision, predecessor_bindings, prospective_revision`；其余所有旧字段原样保留，包括prospective_boundary、原schema限制、source_material/source_scope、research_semantics、novelty_baseline、固定pipeline1/consumer4、真实链与消费者义务、全部原quote/date/hash/unknown、反例规则和scope_limits。未新增候选、类阈值、强制case005适用、易样本或预写enum答案。原及v2完整字节分别仍为 `9fec7af60c3b34c8c10139504fae9199286eaf6179cf39ef2d012fbdf2855aa5`、`e650fb4f73bc5067ee29193328cd3d091dd3b52e4d3c62e5ed095399000ec0d9`；新oracle完整hash为 `dada4c92bac32c133f4efa7bea523d0b0f05d57d0340d1660cdf7976bf257096`。

## 前轮及当前绑定

实际调用最终driver只读 `_stopped_predecessors()` 通过：旧336+323文件映射及另加v2progress共660rows，两个runtime archive精确匹配；原h013/h012仍pending无答/无completion。实际wire/receipt成本核验分别12答/2,001,316和11答/1,837,419逻辑单位，host tokens/费用仍未测。两旧candidate1未完成/consumer4未尝试各自保留，新分母独立，禁止旧cache/作者答复复用。

两个stop、两个archive、两个actual pending-progress均列入新predecessor_bindings；progress hash分别为`c2fd2104438f94ef44402ec83f42fe4070801edd03b81fb825893006cc1f6081`和`0fd2ba50edbab78744c09deec96a19a44ecf1f22f82e3c773fa1c21f89e1cd80`。原driver即排除transient progress/locks；v1 stop原映射含progress，v2不含，最终driver另外绑定v2progress，并未改旧映射来求通过。

父给定owning spec/controller/role_model/tests四hash全部精确匹配；新contract_bindings也绑定当前stage spec/driver/tests。source_material及source_review当前文件与原hash匹配。所有绑定与逐字段三方canonical hash见equivalence-evidence.json。

## 新view与语义范围

stage spec对v2归档的Resources/native phases逐字相同；人口263源/dev8/group/stable18/full265/六披露以及原single/aggregate/call、portfolio、fixtures上限不变。四scope catalog观测仅保已执行原responses（8条/32,000 UTF-8 JSON bytes），保section/cursor并按真实source snapshot区分历史目录与当前状态；无新查询或免费读。

computed workingpage仅保真实ledger compute与source operands（12条/8,000bytes），不授予单位/期间/namespace可比语义。后fetch/缺失或case不符时保历史结果但撤销当前引用权限，并在candidate/sink前typed拒；只有原价重算可重建当前证据，不自动重算或编值。它增加对既有来源lineage义务的实现核验，未改measurement、SignalValue、研究定义或技术准入/effect-unverified标准。原narrative body工作页仍完整受原request预算约束。实际新模型正确使用、新能力闭环及完整MVP均未由这些文件证明。

## 保留的前置harness错误

prefreeze-harness-failures.json保留两次未写oracle的错误：系统Python3.9不支持UnionType；新oracle harness从深目录启动未加repo root导致scripts导入失败。仅切项目兼容runtime、补新oracle-v3 harness sys.path后真实helper和冻结通过；没有产品变更或语义放宽。未把父独立8组/470关联计划当本agent亲验或能力通过。

## 原diff字节保存

统一diff的空白context行含结构性单空格，未删或改任何context。stage diff原字节已确定性gzip封装，解压后逐字节相同；mining diff没有行尾空格，保留原文件。原始/压缩/解压hash及行号保存在 [diff-byte-preservation.json](diff-byte-preservation.json)。实际文件为 [stage-spec.diff.gz](stage-spec.diff.gz) 和 [mining-view-spec.diff](mining-view-spec.diff)。仅整理新诊断产物，acceptance及产品文件未变。

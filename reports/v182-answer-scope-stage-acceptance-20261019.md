# v182 回答范围修复与真实阶段验收

2026-10-19。**实际验收未通过：两案首答均错误关闭或缩窄问题，两个终止阶段均被拒绝；回答范围阻塞仍开放。** 已完成合同修复候选和新模型诊断，不将本地测试通过写成问题解决。用户本次授权独立的有界工作，没有恢复旧目标或完整重跑。

## 为什么选择这一项

v182 已证明 Q2 指引被用来关闭 Q3/FY 问题，且完整生产校验和 fallback 主动维持错误状态，见[原合同审计](v182-executed-answer-scope-contract-review-20261007.md)。它影响后续研究还会寻找什么，以及反馈会把什么当作已回答，属于当前执行链的关键阻塞。修复接口位置、真实输入和反例已具备，可用两个阶段样本区分原因。

来源正文版本/PIT 仍是有效性与收益实验的更高层前提：当前 producer 把 provider publication time 当 available time，store/resolver 没有由此证明历史正文版本，Bumble 未来业绩问题仍可复现；loader 校验 manifest hash 也不等于只加载其 source 文件。没有把本批当作输入清洗。Slow 来源分组已有离线修复，但其真实后继消费未证实；先修复反馈所依据的回答事实更有信息价值。其他问题没有被重命名或关闭。

## 第一版修复与检查为什么仍不够

冻结修复提交 `8d9105db2a179d525b59e496e9cd8338f03d4d4c`：

- 自上而下修改 owning specs；Routing 保留执行前预期，Reflect 在同次调用声明逐 need occurrence 的实际 full/partial/unanswered、实际 residual 和 exact evidence tuples。
- 永久 ResearchState 仍为八字段；临时 Reflect envelope 经完整校验后写入 AgentStep metadata，再传入 state_deltas、最终上下文和 Posthoc/Critic 投影。
- 缺失处置只授权追加；非法处置不授权删除原 need；合法兄弟不被连带撤销。quarantine 后不能保留无证据 full；terminal 空 selections 不得删除未决需求。
- 检查 producer/prompt、完整 validator、typed repair、机械 fallback、正常与终止调用、保存重载，以及实际 Critic 最终 payload 的第二条组装路径。

旧完整 validator 接受两个实际错误状态；只恢复 Q3 问题会收到 remove_exact_target。新校验在**人为指定 unanswered 的本地反事实**中要求恢复且不再强制删除。这仅证实权限改变，不证明模型会正确声明 unanswered。全量 1679 tests 和仓库 lint 通过后才提交、冻结并发真实请求。

我的遗漏是：把“正确声明能够被保存”当成了足够有希望的闭环修复，却未先用独立原文覆盖标准审查错误 full/partial 也能通过。新协议让模型自报实际范围，仍没有独立证明所问对象、期间和内容已被证据覆盖。结构正确和引用有效没有解决这一点。这个假设被本轮实际结果反驳，不能继续以测试数量或 metadata 落盘掩盖。

## 真实调用与语义结果

[冻结 manifest](../runs/diagnostics/answer_scope_20261019/manifest.json) hash 为 `8e6f42c5ed6bcc6a7f76465c110c109ad64819f737e856294486746487339023`。两份实际原始 initial Reflect 输入的十个关键 payload 块保留；新 prompt/need contract/output envelope 按修复改变，原工具目录被绑定但未提供工具通道。terminal 使用新首答状态、原终止控制上下文和空 selections，未用旧模型答案替代。

调用生产 controller/client，模型注册名 `deepseek-v4-flash`（返回 model 为 `deepseek-flash`），两案各 initial 一次、terminal 首答及一次原生 correction，共 **6 次物理调用**。provider ledger 全部 completed，记录费用 **$0.01605744**；费用按现有注册费率和返回 usage 计算，不是独立账单。上限为 8 次/$0.25，结果失败后没有用剩余额度追加调用。

| 样本 | 新首答及实际状态 | 终止阶段 | 语义验收 |
| --- | --- | --- | --- |
| c01 | 原问 Q3 或 FY2025 指引及关键假设；Q2-only 引文被声明 full。原始 operations 没有删除 need，runtime 根据错误 full 声明物化删除 | 空 selections 却给所有剩余 need 写处置；纠错原样 replace，仍无合法 owner | 失败 |
| c02 | 原问 Q3 revenue/EBITDA outlook 及是否修订；理由承认只提供 Q2，却称已回答 current-level facet，直接把 need 缩成仅询问 Q3 修订 | 同样给所有 need 写处置；纠错重排后仍无合法 owner | 失败 |

两案对应的新原答、原生纠错、请求和状态均完整保留。Q2 数值不是 Q3 数值；保留一个较窄问题也不能掩盖未回答部分被删。只读审查者独立对照原 need、实际 Signal 引文和 raw operations 得出相同结论。两个 initial 的未选中 need occurrences 均保留，但这一局部正确不能抵销语义误关。

[result.json](../runs/diagnostics/answer_scope_20261019/result.json) 的失败类型是 terminal 的 CandidateExecutionRejected；它本身未表达两个已被运行时接受的 initial 的语义错误，需结合本报告和[审查 JSON](v182-answer-scope-stage-acceptance-20261019.json)。没有 accepted terminal，也没有 consumers 产物，因此本次未到达实际消费者组装验收，更没有执行新的 Predictor/Posthoc/Critic 模型。

## 失败后的处置与边界

终止失败另有可机械修复的合同缺口：runtime 知道 allowed target set 为空，但初始请求和逐行纠错没有显式列出这个集合；无 owner row 的 replace/remove/add 权限容易让模型反复替换无论如何都不能合法的行。后续仅补齐 runtime 生成的精确目标集合、空集合规则和无 owner row 的 remove-only 权限；不由代码发明 unanswered，不补写真实成功状态。该补丁只做离线真实响应回放和代表性反例检查，**没有进入新的模型调用**。

补丁的 244 项专项检查及最终 1682 项全量测试通过。真实 terminal 首答保持原 operations，经生产 parser 得到 remove-only 权限后，测试提供显式删除 metadata 行的纠错；仅为匿名快照重绑 base_hash。这证明修复路径可执行，不能证明模型会生成该纠错。完整后继门禁仍按预期拒绝：四项前提 pending、goal 非 active、当前为 stop 且无后继计划。

本批实际语义阻塞未修好。不会增加公司/季度 regex 来把词语相交冒充覆盖证明，也不会增加新调用或调宽 validator 获得 PASS。下一步应先冻结独立的原文覆盖验收表，再决定最小改动：

- 同一个 Q3 问题，Q2-only 材料必须保留原文；同一缺口在 full 和 partial 路径都不得消失。
- 预测时点前公开的 Q3 forecast 若覆盖所问内容，可作为可关闭反例；不能因披露日早于 Q3 就拒绝。
- 若仅覆盖 Q3 revenue，则 EBITDA/修订等未回答部分必须保留；财年、跨期比较、混合期间和关系不清保持未决。

这份表是评估依据，不自动成为生产语义真值，也不授权新运行。两个失败样本保留在分母，后续不能只挑成功变体。新检查须先能识别本轮实际错误响应，再考虑新的有界实测；不完整重跑。

## 新 meta 实际改变了哪些行动

1. **先选择可判伪问题与停止条件。** 没有启动 v183；用两份原始样本检验“区分预期与实际处置是否足够”，得到明确反证。
2. **检查合同和生命周期。** 没有只改 prompt；追查到旧 validator/fallback 的强制删除，并补查通常被遗漏的 terminal 空 selections 和真实 Critic payload 组装。
3. **让真实结果推翻本地通过。** 不因 1679 tests、提交、合法引用和新 metadata 宣布解决；亲读 raw output 后确认两个 initial 也错，修正“问题只是终止阶段”的表面解释。
4. **失败时停止同策略加跑。** 保留 6 次调用，停止该批；仅修复有明确机械依据的终止协议，语义问题与消费者未验收状态继续开放。

因此，本次已经观察到新 meta 改变行动，避免把失败误报为验收关闭；**尚不能证明它已使该研究阻塞收敛**，更不能证明研究收益。

## 证据与未关闭项

[审查 JSON](v182-answer-scope-stage-acceptance-20261019.json) 记录全部 22 个诊断文件的 hash、67 份原始绑定未变、92 份冻结代码与提交一致。v182 的 Fast/Slow 权威完成指针仍为 1/1，原运行未改写。旧目标服务仍为 null；本次没有创建或恢复目标。

content_chain、来源/PIT、Slow 实际消费、magnitude/精确复用、独立收益均未关闭；answer_scope_contract_review 前提仍 pending。诊断降低了不确定性，但没有记录 acceptance advance。当前停止决定见 [convergence.json](../progress/convergence.json)，简短状态见 [status](../progress/status.md)。

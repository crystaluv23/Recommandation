# Fast／Slow 逐环节系统审计

日期：2026-10-02。按用户确认的边界：格式、内容、索引、程序与 prompt 的一致性属于验收；正确输入下的模型预测错误不自动成为程序缺陷。用户允许调整固定、非 Plan 进化的 prompt。Slow 设计另见[因子闭环设计](slow-signal-system-design-20261002.md)。

## 结论与证据范围

**尚不能宣布所有综合事务机制正确无误。**主要缺口在校验误拒、局部失败升级整案、恢复诊断丢失、固定角色边界、历史 experience 的恢复兼容，以及 Slow 的技术准入／效果状态／消费追踪耦合。F1 已满足现有下限，不能据此略过这些系统问题。

实际证据：主目录 v167 冻结 `8c07f38333002db8bcbe639b3a28e3d197c49672`，Fast/Slow 指针 1/1；v168 冻结 `7e6be2e377bcae719f3611bd55e7117473841396`，最终审计复查指针 1/1，runner 退出 0；cycle 完成不代表全部工作成功或有新因子入库。新代码只在附属 worktree，未改变正在运行的冻结代码。

[审计原始结果](fast-slow-system-audit-20261002.json)和[修复后复查](fast-slow-system-audit-recheck-20261002.json)记录文件 hashes、请求阶段、字段、缓存存在性、canonical reload、真实 metric 重算、技术排除与模型视图。复查快照覆盖 v167 的 742 份请求/700 份缓存，v168 的 703 份请求/653 份缓存；**缺少缓存不等于调用失败**，还可能是仅准备或预发送阻止，需要 attempt ledger 判定。

这不是逐句证明每份模型输出真实正确：机器检查覆盖全部上述请求的结构依赖及 96 份保存 trajectory 的 canonical 恢复；实际文本审阅覆盖此前记录的案例、这次两份 Critic/最终 Round、Slow entry memory，以及两个轴 Mining 的最终实际请求/回答，以及三条 Update 初答和纠错。未产生的新 Mining 候选、新准入入库和后继 Fast 消费没有实际内容证据；明确列为待验收。

## 当前逐环节结论

| 环节 | 设计产物/边界 | 实际检查与判断 |
| --- | --- | --- |
| Plan 提案 | 四个可进化字段 B/H_init/H_reflect/H_analyse；运行时绑定 Plan 身份 | 两份提案均进入生产转换与评估；结构可用。H_analyse 同时禁止最终分类，与 Predictor 的固定分类职责存在提示边界冲突，需处理。 |
| Basic Info／anchor | PIT 原文卡、运行时数字、来源/期间 | 已检查真实首例及既有完整 Predictor assembly 审计。不能将有 baseline 的案例说成“无行情”；源期间与单位已沿共享链路披露。 |
| Initialize | 完整 ResearchState 八字段及来源 | v168 首答为八字段对象；有效状态可恢复。首答失败后的 scoped 修复/机械 fallback 真实发生。另有三条语义正确或合理的研究问题被 temporal/runtime-input 校验误拒，详见后文；不能把 fallback 当成研究已回答所有需求。 |
| Signal 检索 | selections、exact refs、理由/角色/need indices/覆盖边界 | 实际卡片/选择结构符合接口；曾将 contextual Signal 当作 answer_need，真实纠错会降为 contextual 并保留 need。市值 context_tags 在缺少明确市值依据时仍是内容风险，不能仅靠枚举合法性认定正确。 |
| Signal 执行 | results，状态/coverage/证据；技术状态独立 | 已保存结果通过 canonical 恢复；技术失败-shaped unavailable 与真实数据不足在代码统计上分离。literal 来源和测量语义要独立核验；新因子的完整真实执行仍待候选出现。 |
| Reflect | snapshot base_hash + operations，合并后完整状态验证 | 真实响应使用 patch；输入包含 need transition、当前 Signal、证据目录与预算。正确独立行保留，未解需求不假装解决。并非每个失败都能程序修复。 |
| Predictor | typed 最终证据拼装 + 固定六字段预测 | 两份 24 案已计分；来源/状态可恢复。Ciena 80 处短品牌漏匿名已有隔离修复，未进入冻结 v168。另有跨价格关系的 arithmetic 校验误拒。预测 FP 和幅度集中不自动归为代码问题。 |
| Posthoc | 不改预测；reflection_items/selected_reflection_refs；runtime source snapshot | 结果轴及 source/member 检查可用；真实权重/充分性解释仍出现 fact 标签。共享窄规则及局部 kind/text 权限已补齐，不自动选择经济权重或编造归因。 |
| Plan Critic | 每 Plan outcome、技术完成、运行时统计、来源闭包 | v168 四个技术排除在实际模型输入中均不携带 synthetic outcome/magnitude research feedback。仍保存了将“Plan 不分类”解释为“系统无幅度区分机制”的 fact 文本；它忽略固定 Predictor，不能作为已证实原因。 |
| Round | 比较 Plan／选择下层 experience，不能冒充 pooled 统计 | v168 初始响应把 c01 的 19 次 positive 描述成两 Plan 合计；最终保存 Round 已删除该统计条目，留下明确 hypothesis/action。需审阅最终产物，不能用首答或有无 correction 代替判断。 |
| experience 索引／恢复 | 完整作者内容、brief 索引、hash/source/scope、原件可读 | 96 份 trajectory canonical 可读。最新 guard 使三份旧 experience 重建索引失败，本轮已修复为保留原文/hash、披露 legacy_proof_policy_unchecked。新作者仍受当前规则约束。 |
| Slow entry reflection | episode_reflections + lesson_additions；slots/source closure；processed/pending | v168 保存 3 episode/3 lesson，processed=3、pending=273；技术排除与 magnitude 诊断没有混成因子效果。结构可恢复。当前“不逐项全部消费”有明确 bounded/deferred 契约，不是丢数据。 |
| Mining | direction/magnitude，已披露工具参数、证据、目录、预算；增量需求处置 | v167 198 份输入缺少今天要求的工具/案例时点/Signal 内容披露；这是旧版本已定位问题，不是今天又发生 198 次失败。v168 最终 116 份 Mining 请求均通过当前输入依赖检查；两个 hypothesis 技术退出、两个 discovery 因重复禁用 light 动作预算延期。实际仍有 heavy/browse 预算，不能称全部研究预算耗尽或没有模式。依赖完整不等于动作内容正确。 |
| Materialization | 单个候选的 spec → skill → tests；已正确模块保存 | 当前两次真实 run 尚无新 Mining 候选，不能实测证明此路径正确。v168 Update 实际物化 revenue_growth_yoy:v3，但未入库。已有生产接口/离线模块恢复测试；保留这一验收缺口。 |
| Update | 一个旧版本→vNext；source-backed diagnostics；typed 局部修复 | v167 三个目标中两个完成物化、效果被拒；cash-burn 曾因引用/描述契约不一致技术失败。真实响应重放证明 literal/diff 机械修复仍保留语义和 fixture 失败；v168 三目标中一条 revenue vNext 物化后被严格效果门拒绝，两条分别因 description 不允许更改、纠错还原成 no effective change 技术终止；不能宣称 Update 已全面通过。 |
| 验证／原子入库 | 技术检查、版本/hash/evaluation、prepared/applied、cycle pointer | 原子恢复接口已有测试，但 v167/v168 Registry hash 均不变、0 入库。现有效果门与用户的新设计不同；不能将已提交 cycle 当成入库成功。 |
| 后继消费／性能追踪 | exact version、committed ledger、target evidence、下一冻结快照 | 方向 learning/profile 链路已有实现；magnitude target-evaluation API 未接生产写入/检索卡披露。新准入→Fast 选择→效果追踪尚未贯通，详见设计。 |

## 技术失败是否被归为 FP

对实际 attempt 中的 authoritative trajectories 重算完整 confusion matrix，并对照实际 Critic 输入：

| run / Plan | 固定计分案例 | 技术排除 | 技术行的计分效果 | Binary F1 |
| --- | ---: | ---: | --- | ---: |
| v167 c01 | 24 | 2 | 1 FN、1 负类占位 | 0.7586 |
| v167 c02 | 24 | 4 | 2 FN、2 负类占位 | 0.7200 |
| v168 c01 | 24 | 0 | 无 | 0.7879 |
| v168 c02 | 24 | 4 | 1 FN、3 负类占位 | 0.7857 |

用户已澄清真正关心的是技术失败造成 FN。**这 10 个技术排除中，4 个计 FN；v168 第二份 4/24 技术排除（16.7%），其中 1 个 FN、3 个负类占位。**第二份总 FN=3，技术排除贡献其中 1 个。16.7% 是这份小样本的实际比例，不能外推为稳定发生概率。技术 FP 为 0。占位预测是 insufficient_information / is_surge=false，不能在二元 confusion 中变成 FP；正类技术排除仍计 FN，以保留评分分母。非暴涨案例的占位在正式 confusion 中记 TN，但模型视图明确标为 technical_negative_abstention_not_true_negative，禁止拿来解释研究成功。实际 10 行 Critic 输入全部只有 technical_exclusion 诊断，不含 fabricated case judgment/self-reflection/magnitude attribution。

这不证明技术失败已经为零。v168 c02 仍有四次有界纠错耗尽；本轮逐条复现显示四次拒绝均涉及检测器的错误语义判定，而非据此已证实的模型数值/时点错误。其余真实 positive 预测产生的 FP 也没有被这次审计自动抹掉；一个 Signal 技术失败后，模型仍可能基于其他有效证据作出 positive 判断，需按实际完整轨迹判断其是否合规，不应把整案失败原因都归到同一个 Signal。

## 已确认的 prompt／机制问题与本轮处理

1. **角色边界冲突，待修。**实际两个 H_analyse 都写了“Do not … classify the final answer … generate the prediction”；固定 Predictor 同时必须输出 candidate_judgment/magnitude。Critic 又将 Plan 的禁令当成没有幅度机制的证据。系统确实有固定分类 shell，因此该归因不成立；这属于提示职责需澄清，尚未证明是幅度集中原因。应明确 Plan 指导证据组织，不能禁止固定输出职责；固定 Critic/Proposer 也必须知道这个边界。
2. **历史 experience 恢复兼容，已隔离修复。**tightened guard 拒绝 v167 两份/v168 一份旧 action。改为保留 provenance/outcome/PIT 与 hash 检查，新增 model-only review 状态，不回写内容；当前重新检查所有 96 份保存案例索引均通过。
3. **fact／hypothesis 边界，已隔离补齐。**共用窄的权重/充分性检测，Fast/Slow 初始提示、typed 权限、canonical ingestion、失败保留 pending 对齐。三个真实初答通过生产 Posthoc adapter 重放：仅新增脚本化 kind delta，其他需要修改的字段只复用原来已付费的 exact correction；正确字段/兄弟/来源保持。不是新的 LLM 合规实测，也不是通用真伪判定。
4. **第一修复前沿完整性，已隔离修复。**Woodward 的解释错误旁还有独立 category/outcome 错误；两者现在同一轮反馈，不由新 guard 遮住旧义务。Slow episode/lesson 局部 kind correction 保留 slots、来源及正确兄弟；canonical 拒绝不会消费 feedback。
5. **Slow 效果门与当前目标冲突，已批准设计、尚未实现。**两个目标都应技术正确后入可调用库，效果持续观察；不能伪造 effectiveness.accepted=true。需要 Registry 记录、原子恢复、consumer 和 target 生产写入一起改。

## 验收边界与下一步

已证：上述固定评分重算与归因隔离、96 份 canonical/索引恢复、特定局部修复的权限/保存、实际 v168 输入披露改善。未证：所有文本的经济真伪、最新代码完整 live、Slow 成功完成全部独立工作、两个目标新因子入库、下一 Fast 实际消费及 magnitude 帮助。

本轮将“幅度集中就是必修 bug”撤出验收。保留真实分布诊断，并优先处理已经确认的角色冲突；是否改善幅度需要同输入对照。后续实施按设计中的独立 admission→原子入库→待观察消费→持续 target 追踪，不继续为每种预测错误添加词语黑名单。

## 四次真实技术排除：为什么纠错没有消除它们

这里的“校验误拒”不同于 confusion matrix 的 FP。每项均读取原始 failure artifact，并用隔离 worktree 当前检测函数复现；原 run、请求、回答、标签和分母未修改。详细原文、request refs、源码及文件 hashes 在复查 JSON 的 `actual_failure_artifact_diagnostics`。

| 案例 / 环节 | 实际文本与拒绝原因 | 审计判断 |
| --- | --- | --- |
| 0000895728 / Initialize | 问截至预测时点披露的三季报发布时间和业务更新预期，结尾明确“without reference to contents or results published after the prediction time”；被判为请求未来内容 | 否定范围没有正确处理。当前 trailing exclusion 只识别特定动词短语，把排除未来资料当成要求未来资料。应保留截止时点和日程契约，不扩展为允许未来结果。 |
| 0001590364 / Initialize / 技术 FN | “当前 adjusted share price 是否已反映 adoption narrative，什么增量证据支持上行”；被判为 runtime-owned input lookup | 问的是市场预期与解释，未索要/重写固定 baseline。应分别判定分析问题是否放对 `open_questions` / `next_information_needs`，不能以价格词语为理由整案拒绝。 |
| 0001869198 / Initialize | 同样问当前股价是否已反映 adoption narrative、什么条件导致大幅上下变化；同类 runtime 拒绝 | 与上一项同一错误家族。可以要求拆出可检索证据需求，但这不是 baseline 查价。 |
| 0001174922 / Predictor | 原答及局部纠错都说明 baseline=109.614，2x threshold≈219.23，recent close=109.53，历史窗口87.17→109.53收益25.651%，距2x所需100%涨幅很远 | 数学叙述正确；正则从“100% gain from baseline”附近抓到历史窗口 `to 109.53`，误认为其终点，算出-0.0766%。跨关系拼接违背检测函数自己的“不连接不同子句”契约。 |

因此本批四项不应据当前错误判据整案排除。不过，修正误拒仅恢复执行机会，不证明该案例最终必然预测正确；不能直接把技术 FN 改成 TP。

已有机制实际执行了错误检测、bounded 局部纠错及 merged revalidation；没有解决“判据自身错误”。纠错后仍受同一判据拒绝。Initialize 的证据 grounding fallback 也不是所有语义 issue 的通用救援，不会自动覆盖这些拒绝。统一修复模块保证了权限、顺序和保存，并不保证任意检测器都准确。

## 降低技术失败与技术 FN：实施优先级

1. **先修检测边界。**截止日程/未来内容、运行时查价/预期分析、价格关系分别按请求对象与否定范围判定；确定性核验只验证已明确绑定的结构。复杂自然语言关系不明确时，不根据关键词或跨句近邻数字认定算错。真实泄漏、错误 anchor、实际计算错误仍硬拒绝。新增测试须同时覆盖合法表达、实际越界及混合句反例，不能只加入这四条原句。
2. **把计算和请求意图结构化。**运行时 baseline/threshold/return 由程序给出；要核验模型新计算时，绑定 denominator/target/window 与来源，不从自由文本猜关系。ResearchState 分开证据请求与分析问题；提示、schema、validator、局部迁移权限一致。属于下一实施设计，不能只改 schema 或增加 prompt 强调。
3. **按最小有依赖的单元隔离失败。**某个非关键信息需求失效时，保留其 pending/诊断、保留有效状态和证据，允许独立工作继续。不能把单条可选问题直接扩大为整案失败；也不能默默删除关键反证或把依赖未解决的机会判断当成功。无有效最终判断时仍标技术失败，不伪造预测。
4. **纠错要检测进展。**区分 parse/结构、工具参数、语义冲突、校验器疑似误拒和 provider 失败；只修 exact frontier，保留正确产物。连续同一拒绝且没有新信息时应回到诊断，不让 LLM 为规避检测器反复改写。加重试次数对错误判据无效。
5. **恢复必须保留失败证据。**v168 c02 attempt 的 `failures=[]`，但有四个 exclusion IDs 和四份 failure artifacts。恢复路径复用 trajectory 未恢复 failures 列表，分类与 Critic 技术状态保留、诊断明细丢失。该缺口待修；“空 failures 列表”不能证明技术失败为零。
6. **验收同时看完成率和预测评分。**正式固定24案 F1及分母保持；另报技术排除率、技术正类排除/FN数、按阶段/错误家族的失败数与恢复率。只报 F1>0.6 会掩盖负类技术占位贡献 TN 的问题。先零网络重放四项，随后完整真实24案，检查该错误家族不再误拒且真实越界仍被阻止；不保证模型自身 FN 为零。

## v168 最终 Slow 审计补充

runner 退出0，提交指针1/1。direction/magnitude 各两种子：hypothesis 为 technical_failure，discovery 为 deferred_budget，整条 Mining 标 partial；0新候选。最后实际回答显示：模型反复选择已禁用的 inspect_catalog，随后 fetch_evidence 缺必需 rationale；两个 hypothesis 因有界纠错耗尽退出。discovery 的终态也来自连续不合预算的 light 动作，而不是全部 heavy/browse 预算耗尽。建议把动作专属 schema、参数及当前可用动作放在纠错的必要上下文，同时保留已有证据/待消费需求；不能程序编造研究理由以“修好”rationale。

Update 三目标：operating_cash_flow_margin 纠错仍改动 immutable description；cash_reserves 修复后无有效变更但仍要求 update；revenue_growth_yoy:v3 已物化，因无 strict paired effectiveness gain 被拒。Registry input/output hash 相同，无入库。逐目标失败隔离在工作，但新技术准入设计尚未实施。没有候选入库和后继消费，因此仍不能证明 magnitude 因子改善幅度预测。

最终本地验证：1399项全量、25项专项通过；lint PASS。验证的是共享修复及恢复兼容改动，不包括上面四类检测误拒修复、新准入实现或其真实效果；这些明确待实施。

# Fast / Slow 共同可靠性机制：设计与实施

日期：2026-10-01。阶段现状以 [context 审计](fast-slow-context-audit-20261001.md)
为依据，约束以 [共同阶段契约](../spec/src/stock_opportunity_agent/research/stage_contracts.md)
为准。本文记录实施内容；真实运行和研究质量验收另有产物，不能由单元测试代替。

## 共同机制的职责

系统运行时拥有数据来源、时间边界、标识、计算结果、预算、状态迁移和提交指针。
LLM 负责提出研究问题、解释已披露证据、形成判断和反思。每个环节的输出先作为
候选，经过所属模块完整校验，才成为可供后续阶段引用的产物。

共同契约统一五件事，领域校验器继续判断各自的内容：

1. **输入依赖**：这个阶段完成哪一个任务，必须读取哪些对象、哪一个版本。
   必要 context 包含任务约束与反证，不以字符最少为目标。
2. **披露规则**：模型当前看到什么、没有看到什么、如何读取遗漏的原件。
3. **检测规则**：结构、出处、PIT、数值、状态迁移，以及预算和运行进度。
4. **修复权限**：哪些错误可唯一确定地修复，剩余问题能改哪些具体路径。
5. **保存与恢复**：已接受产物与未接受候选分别保存，后续按依赖和提交指针恢复。

这五项没有形成另一个代理引擎。小型 `stage_contracts` 模块提供输入审计与完整条目分页；
现有 transport、领域校验器、repair、workspace 和 ledger 分工执行。

## “披露”为什么需要单独设计

披露不等于再加一份总结。它是模型与系统之间的知识可见性协议：

| 层次 | 模型看到什么 | 运行时必须说明什么 |
| --- | --- | --- |
| 目录 | 类型、标题、稳定引用、覆盖数量 | 总数、当前页、前后遗漏数量、下一页游标 |
| 工作视图 | 与任务有关的完整 brief 或精确片段 | 选择范围、截止时间、截短与遗漏情况 |
| 按需原件 | 明确引用的完整原件或 source span | 原件版本/出处、字符范围、读取上限 |

例如有 22 条反思，当前工作视图只给 6 条：它必须告诉模型还有其他条目，并给出
可浏览的引用目录；不能让模型把“没看到”当成“系统没有”。预览明确标记裁切，
不能用它证明逐字引用。读取后仍不足，与未读取、来源不可用分别记录。

本次 Mining 改动保留本地原件，限制初始 brief 页为 6 项/6KB，目录页为 12 项/5KB；
可按已披露 `item_ref` 读取 1–3 个完整条目，总量最多 16KB。超大条目与遗漏显式说明，
不静默切成伪完整证据。已有 source catalog/fetch/provenance、反思索引继续供其他角色使用。

## 各阶段的统一边界

| 阶段 | 工作输入 | 检测与修复重点 | 保存与下游消费 |
| --- | --- | --- | --- |
| Proposer | prior、父 Plan、实验摘要、可读经验目录、约束 | Plan schema、允许的 Basic Info 菜单、身份匿名化、内容去重 | 每个接受的候选 Plan 单独 staging；后续复用 |
| Initialize | 初始研究 skill、Basic Info 投影、程序计算的锚点 | 证据坐标、字面数值、时间边界；禁止把运行时锚点当成待查问题 | 接受初始 state；Basic Info 原始投影保留 |
| Signal retrieval | 未回答需求、适用性 context、Signal cards、调用上限 | 只能选择披露的 ref；区分回答需求与补充研究；不重复未变化的调用 | 选择记录与待重试请求分别保存 |
| Signal execute | 已选 spec/skill、其来源投影、as_of | literal evidence、数值/PIT、分类与 unavailable、既有 Signal schema | 合法结果保留，错误单元隔离；不吞 provider/control 错误 |
| Reflect | prior state、当前 batch、typed need transitions、相关目录 | 增量 patch、引用归属、准确需求残值、resolved/retained 冲突 | 局部合并后完整校验；state delta 与 evidence 一并进入轨迹 |
| Predictor | 运行时拼装的 typed evidence/state evolution/有效 state/baseline | 盲态、固定预测定义、可核验理由与分类 | 先固定 prediction，再揭示 ground truth |
| Posthoc | 原预测、必要 source context、程序真值 | 反思引用闭包；技术失败不得转成研究因果结论 | 原反思不可改写；brief/item/source ref 可向上引用 |
| Critic / Round | 确定性指标、紧凑案例诊断、下层 briefs 与可读原件 | 跨案例/跨 Plan 推论必须有 source；配对条件不满足不能声称指标因果改善 | 原 case/Plan 反思与新作者条目分开保存 |
| Slow reflection | 尚未消费的反馈单元、测量契约、先前方法记录 | 条件/总体/分母、append-only、读原件、失败不消费反馈 | 新反思保存后才推进消费位置 |
| Mining | 本轴标签、证据 manifest、工具结果、相关 memory、预算 | typed action、真实返回内容、来源/时间/测量条件、重试/预算 | ledger 保存每一步；候选/无模式/预算不足分别落盘 |
| Materialization | grounded candidate + cited evidence，再依赖已接受的 spec/skill | spec→skill→tests 分模块校验；分类 fixture 与技能一致 | 已接受模块在重试中复用；合成后完整候选 gate |
| Update / validation / promotion | 一个稳定 Signal、induction 观察、可变字段；独立 check | 不变定义/tests/版本权限、真实来源、fixture/效果门、匿名化 | staged/validated/promoted/used/benefit_confirmed 不混同 |

最终 Predictor 的 context 是前面合法产物的结构化组装：Basic Info 投影、采用及反对证据、
各次 state 变化、最终有效 state 和计算锚点。不能只留最后 state；同时必须标明被移除或
替代的状态，避免把历史判断当作当前有效判断。现有 append-only assembly 的证据闭包保留。

## 程序检测的能力边界

检测分三层：

- **可严格判定**：JSON/schema、必需依赖、引用是否存在、literal quote、精确计算值、
  PIT、枚举/上限、版本一致性、状态迁移、patch 权限。
- **可识别风险或停滞**：重复无变化请求、不可用证据、动作预算耗尽、前置条件不足、
  部分文本边界模式。命中后给出有界纠正机会或显式 defer；不能无限重试。
- **必须作研究判断**：证据能否支持经济推论、反证是否充分、因子是否有效。
  程序规则不宣称解决所有未知 corner case；需要原件审阅及独立测量。

关键词只是第二层启发式。v154 VSAT 的 `expectations` 复数曾被时间词表遗漏，说明
启发式也可能误拒。增加普通词形及真实回归样本，同时保留未来事实限制；不能用
“检测器通过”替代内容正确性。

## 修复与保存的顺序

```text
输入依赖 / 标签 / 身份检查 → 模型原始响应留存 → L0 JSON 候选解析
→ 所属模块校验 → 适用的确定性修复 → 全量再校验
→ 保留机械修复进展与剩余问题 → 有界、typed 权限的 LLM 局部 patch
→ 完整合并校验 → 合法产物 checkpoint → 依赖阶段继续
```

混合错误不再要求“整份输出只包含机械错误”才启动修复。可以先去掉唯一确定的重复项、
恢复运行时已经指定的精确需求，再把剩余证据语义错误交给 LLM。中间候选不是合法 state；
只有完整原校验器通过才接受。LLM 纠错的基线是最新候选，权限也根据新问题重新生成。
visited-state 与最大修复步数阻止固定点死循环。

保留未回答需求但又新增“已解决”的冲突，会暴露需求和 resolved 两个路径。只有领域
校验器明确判定新 resolution 没有本轮直接回答依据，程序才允许删除它。存在直接回答
或多义性时交由有权限的局部纠错，不从错误散文推导写权限。

无法修复的普通局部问题留下诊断并隔离该单元；provider、暂停、取消、成本预算及
其他控制面异常继续传播，避免错误重启或伪造正常产物。

## 当前实施和真实验收

已实现共同阶段输入依赖 metadata、完整工具目录返回、有界可读 Mining memory、
非负动作预算、单份 span、混合错误的机械进展保存、typed need/resolution 权限和
普通时间词形回归。仍需用真实链路观察这些机制是否能收敛，以及修复结果是否保留
研究内容；不能只检查调用成功或 schema。

v155 验收入口替换旧 harness，使用生产角色和 exact-request transport/ledger。
从批准的开发 split 预先选择全局 Label Store 可覆盖、PIT 锚点与叙事来源可用的案例，
冻结全局 Raw Info 原件引用/标签文件/Registry 的身份（不复制全局 oracle）；四档各 1 Anchor + 1 Random，两个真实
Proposed Plans，独立 Discovery 16 案（8 control、4 2–3x、2 3–10x、2 10x+）。
后者同时支持 direction 两侧的类别覆盖和 ge3 两侧各 4 案的既有效果检验下限。Locked Test 不读取。未覆盖日期明确记录，不
通过修改日期或真值填补，也不在看到模型结果后换样本。

验收包括：每种实际阶段的保存请求与响应、目录遗漏可达性、原文引用、状态迁移、
原预测与反思一致性、Signal fixture/候选 gate、Fast/Slow 提交指针，以及固定分母上的
F1/混淆矩阵。合法 no-change/defer 会保留理由；没有执行的分支不能宣称已验收。
该诊断 cohort 与 v154 不同，F1 不作配对提升比较；系统执行、研究分数和收益证据分别报告。

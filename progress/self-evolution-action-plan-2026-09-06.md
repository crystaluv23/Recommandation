# 自进化可靠性与有效进化行动方案

日期：2026-09-06。审计代码：`aa2f57a1196c6f03baf0a79da81974b4cb6436c0`。

本文是可以交给 agent 的实施方案，不是已实施的架构变更。此次没有改变运行逻辑、冻结新运行或发送外部请求；没有访问 Locked Test 内容。已核对当前源码、规范、历史审计、V112/V113/V114/V117/V118 持久化结果，以及 V118 部分实际请求和响应。不是对所有历史运行、所有 provider 和全部源码的逐行认证。

## 1. 结论与成功定义

现有 Fast Plan / Slow Signal 分工、共享 Raw Info、候选隔离、版本化 Signal Registry、预测先落盘后揭示标签、原子提交指针等基础可以保留。现在不能把“能结束一个 cycle”或“测试通过”当成真的自进化。

需要同时满足三个层次：

1. **执行正确**：错误不会污染来源、标签边界、评估总体、版本和提交状态；恢复不会重复计费、重复计样本或丢失已接受结果。
2. **学习发生**：产生实质不同的 Plan 或 Signal；候选完成独立验证；合格 Signal 被精确提交，并被后续 Fast 实际检索、执行、引用。仅生成候选、增加版本号或累计 profile 不够。
3. **收益成立**：在冻结的独立评估协议中，相对基线有可重复的改善，并排除样本变化、数据增量、模型噪声和反复试验选择造成的假提升。

无法保证每轮都会发现有用规律，也不能保证丢掉一个坏 Signal 后每个预测都完全不变。正确目标是：无效信息不进入结论；局部故障尽量被隔离；剩余证据不足时诚实保留不确定或暂停；最终晋升和收益结论仍由独立证据决定。正常的“没有改进”是合法结果，不能为了证明进化而强制晋升。

用户举例的 10 个 Signal 中 1–2 个异常可以作为压力测试强度，不能作为已达到的错误率，也不能只测随机均匀错误。必须覆盖某一 provider、某类 Signal、某组案例集中失败，因为这类错误更容易产生偏差。

## 2. 当前证据基线

| 运行 | 权威状态与结果 | 能证明什么 |
| --- | --- | --- |
| V112 | Fast round=1；cycle=0；24 个有效案例，TP=7、FP=1、TN=9、FN=7，F1=0.63636；Registry v1 | 已有一次完整、合格的 Fast 评估；没有单凭此证明相对基线提升 |
| V113 | round=0、cycle=1；H1 结构纠错失败；无候选、无晋升 | Slow 的失败可被记录和提交，不代表学习成功 |
| V114 | round=0、cycle=1；无候选、无晋升 | 历史 H1/证据匹配问题；后续代码已有修复，不应重复当成未修复项 |
| V117 | round=0、cycle=1；H1 纠错错误地推导出 `e.g` 路径；无候选 | 该路径解析错误已经在当前代码修复，完整进化未验证 |
| V118 | 当前审计代码；round=0、cycle=1；H1 失败后 E1 也失败；无候选、无晋升 | 最新修复仍未完成有效 Slow 闭环，且发现新的通用边界问题 |

这些是不同 workspace 的状态，不能相加成一个连续执行成功的 Fast+Slow cycle。V118 使用 committed-Fast bootstrap 并不意味着其本地 Fast 指针应为 1。

可核对文件：

- [V112 Fast 评估](../runs/cold_start/evolution/deepseek-v7-ordinary-validation-20260904-v112/experiments/round-0001/attempts/plan_r0001_c01.json)
- [V118 cycle 指针](../runs/cold_start/evolution/deepseek-v7-ordinary-validation-20260905-v118/cycle_state.json)
- [V118 Slow 结果](../runs/cold_start/evolution/deepseek-v7-ordinary-validation-20260905-v118/experiments/cycles/cycle-0001/slow_loop_result.json)
- [V118 E1 初始请求](../runs/cold_start/evolution/deepseek-v7-ordinary-validation-20260905-v118/requests/727ed7d1ff97e0606ab24af404e215b592bb99eb6cb594b1d141c3a5efb9c706.json)
- [V118 E1 初始响应](../runs/cold_start/evolution/deepseek-v7-ordinary-validation-20260905-v118/cache/responses/727ed7d1ff97e0606ab24af404e215b592bb99eb6cb594b1d141c3a5efb9c706.json)
- [V118 E1 纠错响应](../runs/cold_start/evolution/deepseek-v7-ordinary-validation-20260905-v118/cache/responses/a6e8e3409d3ee826aaeadc34a4b66d795780a5cf598505a2e97dcd58ec97a745.json)
- 历史背景：[8 月 22 日审计](self-evolution-audit-2026-08-22.md)、[持续真实上下文审计](self-evolution-live-validation-audit-2026-08-23.md)。旧审计的“未修复”必须重新对照当前代码。

实际请求文件计数也说明仍高度依赖纠错：V112 有 24 次 H_init 初始请求和 19 个纠错请求文件、38 次路由初始请求和 21 个纠错请求文件；V118 有 36 次 Signal batch 初始请求和 9 个纠错请求文件。这是**请求文件计数，不是独立错误率**，可能包含多轮纠错、缓存复用，不能直接推断 19/24 的初始失败概率。

本次运行全仓测试：`Ran 578 tests in 18.381s — OK`。通过单元测试与最新 live Slow 仍失败同时成立，说明需要更强的契约与系统验收，而不是只增加历史报错字符串回归。

## 3. 两个库应如何理解

### 信息库

现有真正的库是 `RawInfoStore`；Basic Info 是按 `BasicInfoPolicy.requests` 从共享 `EvidenceResolver` 取回并投影出的视图，不需要另外建一个保存“模型总结事实”的 Basic Info 数据库。

推荐保留的链路：

```text
RawInfoRequest + issuer identity + as_of
  -> source capability routing / local lookup / bounded acquisition
  -> eligible original documents
  -> request-relevant selection and exact projection
  -> BasicInfoBundle or Signal execution inputs
```

接口要区分“找到了文档”“覆盖了所需来源/期间”“模型可见部分包含相关证据”“足以回答问题”。目前 `resolved` 基本只证明有文档，不能当成最后三项。

### 信号库

`SignalRegistry` 保存可复用的分析能力定义、版本、skill、fixtures 和学习 profile；它不应该把某公司的单次 SignalResult 当成稳定 Signal 定义。SignalResult 应继续绑定案例、as-of、输入证据和版本，作为执行记录保存。

推荐保留的链路：

```text
need -> eligible compact cards -> selected exact refs -> full versioned spec
     -> shared resolver -> executor -> validated result + execution outcome

Mining / Update -> isolated candidate -> contract validation
                -> independent effectiveness evaluation -> exact-hash promotion
                -> next Fast frozen snapshot -> actual use
```

现有稳定版本、候选隔离、批量晋升前检查和 transition 恢复设计有价值。需要修的是相关性、错误分类、复评记录和验证强度，不是重写两个库。

## 4. 已确认问题与设计缺口

| ID | 优先级 / 性质 | 当前证据与影响 | 修改方向 |
| --- | --- | --- | --- |
| F1 | P0，确定性缺陷 | `SignalExecutor._resolve_input` 只传 description/source_types，不传 query；`_rank_documents` 只用 query 排序。11 篇合成文档探针中，唯一相关旧文档被最新 10 篇无关文档挤掉，仍返回 resolved | 版本化检索意图；先相关性/来源与期间覆盖选择，再限量；区分 retrieved 与 answerable |
| F2 | P0，已确认边界不一致 | E1 对单案例来源按该案例匿名化，输出却扫描整个 Discovery 身份集合。V118 E1 原始输入不能通过输出的同一身份检查；纠错响应复制来源中的 CHT/Chunghwa Telecom 仍被拒绝 | 同一输入输出匿名化域；匿名投影的引用必须可回映；避免让模型承担身份替换 |
| F3 | P0，确定性缺陷 | `_validation_obligations` 仍从报错 prose 用正则提取写路径；V118 H1 整体数组变化不能被现有索引投影恢复；已有修复只是缩小症状 | 结构化 ValidationIssue 与稳定 item ID；依赖明确的局部 repair，不再解析人类报错控制写权限 |
| F4 | P0，语义分类缺口 | `StructuredLLMSignalRunner.execute_many` 最终失败生成 unavailable；通用 batch adapter 漏项也转 unavailable。学习 profile 只有 unavailable 与 unavailable_with_inputs，不能可靠区分执行错误 | 用执行状态封装领域值；错误不伪装成无数据，不进入方向效用统计 |
| F5 | P0，确定性缺陷 | `_validate_cycle` 会重新评估 provisional；`record_candidate_validation` 却只允许原路径 validation.json 内容完全相同。探针中 provisional→通过报 immutable artifact conflict | 同一候选允许多个不可变 evaluation attempt；晋升绑定具体 attempt 与 candidate hash |
| F6 | P1，已确认语义质量缺口 | V118 Update rationale 写出“positive label suggests a financing action”；parser 只检查 case_ref 等结构，接受了用股价标签推断事件存在的说明。结果是 defer，未污染稳定库，但诊断逻辑错误 | 将 Signal 测量正确性与预测效用分开；先盲证据诊断，再局部关联结果；每个事实回到来源 |
| F7 | P1，已确认表示缺口 | Update 重用了确切输入文档，但 `_signal_update_evidence_packet` 又独立截取每篇 1,200 字窗口，并未优先带上当前结果实际引用。V118 响应明确称引用不在可见 excerpt | 更新包优先携带执行时实际投影与证据、再补上下文；保持匿名映射一致 |
| F8 | P1，设计缺口 | effectiveness 默认最多 8 案例、最少 4 available、最少 2 decisive；新 Signal 只要 correct>wrong 即可。只测 Signal state 与 surge 标签关系，不证明端到端 F1 增益 | 保留为最低可执行性/方向性门槛；补独立、成对、多次评估，单独证明系统收益 |
| F9 | P1，已确认跨轮风险 | Update issue_fingerprint 只 hash target/profile；新 Raw Info 到达但 profile 相同可能继续 unchanged_issue_suppressed；非 provisional validation 也主要按 candidate hash 复用 | 区分问题指纹和输入/评估指纹；只有真正相同的工作才 no-op |
| F10 | P1，确定性边界缺口 | FrozenSignalRegistry 的 skills/profiles、SignalSpec.parameters 是可变字典；本地修改成功但 registry_hash/learning_hash 不变 | 深不可变或隔离副本与入口 hash 复核；消除“hash 没变、实际能力已变” |
| F11 | P1，存储接口缺口 | 同根两个 RawInfoStore 实例中，B 看不到 A 新增的文档；B 重加完全相同文档报错。已用临时目录复现 | 明确快照/刷新语义；并发同内容 append 幂等、不同内容拒绝；全局 oracle 不依赖 workspace 锁 |
| F12 | P1，设计缺口 | E1 样本按 positive/control 分桶后顺序编号和发送。V118 输入顺序为 case-001..004、case-007..010，虽然未显式给 label，顺序/编号仍编码分组 | 标签无关种子打乱呈现顺序并分配 opaque refs；本地保留映射；不宣称已证明模型实际利用了该线索 |

补充限制：`SignalCapabilityAudit` 对 deterministic 会执行 fixtures，对 LLM 主要检查 skill/fixture 存在；它不是软 Signal 语义正确率认证。语义去重目前主要是归一化 description 相等，不能证明“没有重复能力”。后者可在质量验收中补覆盖，不必优先引入向量数据库。

## 5. 实施任务包与依赖顺序

### T0：建立审计基线与执行合同

先阅读 `AGENTS.md`、`spec/vision.md`、`spec/architecture.md` 及本方案涉及的模块 spec；保存 HEAD、dirty 状态、运行指针、数据/Registry/model/limits 哈希。冻结旧工作区为审计证据，不改写既有响应、validation 或 pointer。

把 F1–F12 分为已复现缺陷与待验证设计假设。新增证据索引以 request hash 连接：原请求、原响应、局部验证结果、实际接纳结果、回退动作、模型用量、最终持久化位置。不要把旧测试计数复制成新验收结果。

**验收**：一个离线命令能输出每次运行的 learning funnel：提出→结构有效→可执行→独立验证→provisional/rejected/promoted→后续实际使用；同时输出 agent_failed/no_candidate/no_gain 的不同终态。没有 candidate 不能记为候选验证失败。

### T1：统一通用错误与恢复协议（F3、F4）

修改范围：`research/evolution_runtime.py` 的 `_complete_parsed_role`、`_validation_obligations`、`_project_scoped_correction`、`StructuredRoleClient`、`StructuredLLMSignalRunner`；`signal_library.py` 的 batch/result/learning 接口；各拥有相应 record 的模块 spec。

1. 引入小而明确的结构化 `ValidationIssue`：`code`、`path/item_id`、`severity`、`retryability`、`allowed_repairs`、必要 dependent paths 和 source refs。人类错误文字只用于显示，不能决定纠错权限。
2. 聚合可独立判断的错误；跨字段依赖作为同一 obligation。不能要求“改 query 以匹配 id”，同时又不允许合法的 id/query 联动修复。
3. 用稳定 item ID 定位数组成员。优先让 correction 返回受限 item patch；恢复时保留已验证兄弟项，最终重新跑完整 parser、来源和语义一致性检查。不要把任意大段对象重写当成局部 correction。
4. 定义统一执行封装，至少区分成功、有合法领域空结果、结构/证据错误耗尽、暂时传输错误、永久 provider 错误、预算/授权暂停。Signal 仍保留四种领域值，不通过新增“negative fallback”绕开定义。
5. 技术失败不计作合法 no_match、不计作 unavailable 方向性观察；诊断台账独立保留失败、输入和消耗。模型侧只能看到安全的 coverage 信息，不能把错误文本当研究证据。
6. 每个角色有显式、有界恢复策略：transport 重试；结构纠错；可证明安全的 item quarantine；仍不足则暂停或诊断性结束。禁止 blanket `except Exception: return []`；授权、预算、PIT、身份、hash、提交冲突不能通过内容纠错绕过。
7. 在 adapter 边界统一 missing/extra/duplicate IDs、截断、拒答、空响应和 usage 形状。支持 schema 的 provider 可发由同一模型定义生成的 JSON Schema；不支持时保留本地同一验证器。以 capability 决策，不以公司名、模型名称或某条报错 hard code。
8. 保留精确 wire-body、cache 和调用账本。重试与缓存复用分开计数；多次独立评估必须有显式 replicate 身份，不能被同一 cache key 吞掉。

**验收**：每类失败在路由、Signal、H1/E1、Update、Predictor 适配器上走同一错误类别；混合有效/无效结果保留合法项；重复 ID 明确拒绝；控制面错误不进入领域统计；恢复后的最终对象通过原完整约束。新增措辞/JSON 排序/列表重排不能破坏修复，也不能扩大修复权限。

### T2：修正信息取回与输入表示（F1、F2、F7、F12）

修改范围：`data/resolution.py`、`signal_library.py:SignalSpec/SignalExecutor`、`research/scheme_evolution.py` 的 Basic/Mining/Update projection、`research/evolution_runtime.py` 的 LLM projection；对应 data/resolution、raw_info、signal_library、scheme_evolution/runtime specs 与 catalog。

1. 用一个版本化 retrieval contract 描述信号的测量对象、所需来源、期间/比较基线和 query terms。利用现有 request/selector 机制扩展，不另建跨模块检索框架。硬 Signal 对比较期间和财务单位有确定性要求；软 Signal 的短查询不能等同于长说明文字。
2. 在全部 PIT 合格文档上选择，再限量；去重同源副本，保留所需来源和比较期间的覆盖。通过案例证据测试确定 ranker 是否足够，不能仅把 description 原样塞进 query 就宣布完成。
3. 分开返回来源取回状态、可见证据覆盖、截断情况和缺口。只有无文档才触发 acquisition 的旧逻辑需要扩展为“缺少合同规定的必要来源/期间时，按原授权与预算有界补全”。纯语义无法回答时不无限获取。
4. Basic Info 与 Signal 使用相同来源资格、身份和时间规则，分别拥有消费侧 projection。请求字段不应让 LLM自由发明 provider/source aliases；source capability 用冻结枚举或结构化字段。
5. 建立同一份匿名 projection catalog：opaque document/projection ref、raw hash、范围/offset 映射、可见文本与匿名化策略版本。输入先通过输出同域身份检查；引用复制匿名片段，由运行时映射原文。不能要求模型一边字面引用、一边自行删改名称。
6. 身份检查区分正文实体与单字母/短缩写。用结构化 issuer 身份及明确上下文判定，覆盖 ticker 与普通字母、财务缩写冲突；不要继续添加一串特定股票例外名单。第三方实体如何呈现必须与整组匿名规则一致。
7. Update 必须先带回当前 Signal 真正引用的投影和支持/反证，再分配额外窗口；缺失原投影时明确缺失，不声称复用了相同 context。
8. E1 的呈现顺序和 opaque ref 生成与 outcome 无关、种子可恢复；样本分组与标签只在本地控制器保存。所有来源文本统一作为不可信数据，不能覆盖角色协议。

**验收**：相关旧文档不会被无关新文档挤掉；同义主题、HTML/JSON、长文档、多来源、期间不足、市场 ETF 新闻仅提及发行人、无匹配、provider 回退均有真实形状 fixtures。所有成功投影能回到正确的文档、时间与范围；E1 逐字复制合法片段不会因另一套身份规则失败；输入遗漏不被解释为事件不存在。

### T3：修正信号保存、复评、缓存和不可变性（F5、F9、F10、F11）

修改范围：`signal_library.py` 的 candidate validation/transition/freeze；`scheme_evolution.py` 的 `_validate_cycle`、Update suppression；`data/raw_info.py`。先更新对应 specs，维持既有原子提交不变量。

1. 将“候选定义不可变”与“该定义可以多次评估”拆开。候选目录下按 evaluation key 写独立不可变评估记录；key 绑定 candidate hash、baseline hash、cohort/issuer split、source manifest、projection/validator/model/sampling 协议。单个 validation.json 不再承载所有复评历史。
2. 晋升 transition 指向具体成功评估记录。provisional 后新增证据可形成新评估；精确重放不重复计费或晋升；历史 provisional 和 rejected 完整保留，不能因 status 混用被误当作可任意覆盖的 rejected draft。
3. Update 的 issue identity 与 work identity 分开。只有问题、相关证据、适用案例、模型/协议均未改变才 suppress；不能用整个全局 oracle hash 使每次无关增量都唤醒，也不能在相关证据增加后永久 suppress。
4. 深冻结 spec.parameters、skills、profiles，或返回隔离副本并校验消费快照。调用方修改返回值不能改变冻结执行能力及哈希关系。
5. RawInfoStore 定义显式 snapshot 与 refresh/load 行为。并发 append 遇到已有路径时读回全记录比较，完全相同才幂等，不同内容/来源拒绝；跨路径 document_id 唯一性也要保证。全局 oracle 的并发控制与单 workspace 运行锁分开。
6. 在 promotion 的 prepared、每个 stable 文件写入、Registry 版本更新、output hash、cycle pointer 等位置做故障注入。恢复只能完成同一 transition，不得暴露部分混合快照或跳过失败项。

**验收**：provisional→新证据→通过→晋升→下一 Fast 可见的持久化往返测试必须成功；两候选批次中途崩溃恢复一致；并发相同文档成功/不同文档拒绝；新实例 reload 得到相同稳定定义；修改返回对象无法静默改变 frozen 行为。

### T4：让 Slow 具备持续产生有效候选的能力（F3、F6、F7）

依赖 T1–T3。修改 `LLMSignalMiningModel`、`LLMSignalUpdateModel`、`SignalEvolutionEngine` 及其 specs。

1. H1 把“测量对象、适用范围、比较/预期方向、检索意图、可证伪条件”结构化；不靠 hypothesis_id、自由 prose 与 query 的词语交集判定语义一致。运行时拥有组别、ID、默认时间/限量等机械字段，不让模型反复抄写。
2. 保留需求驱动 Mining 和现有 Exploration fallback，但允许明确的“不具备可测试假设/证据”的结构化结论；backlog 非空不保证一定能提出新的有效 Signal。此结论与 schema failure 分开。
3. H1/E1 按假设或 case 稳定 ID 隔离失败，恢复合法兄弟项。E1 可以有界微批次，防止一项 literal 超长毁掉整批。最终达不到冻结的两组证据门槛时停止该比较，不能换掉失败案例后悄悄报完整通过。
4. 避免在“观察事实”阶段泄露 outcome。Update 先核对当前输出是否被原始证据支持，再解释与 outcome 的关系；positive label 不是融资、临床结果或订单存在的证据。可以先调整 payload 和结构化诊断，不预设必须新增模型调用。
5. 对 schema-valid 但语义错误的诊断建立独立盲审集。事实观察需引用具体证据，统计关联需指明样本，模型不得把统计标签写成来源事实。自由文本规则只应作为弱提示；硬拒绝优先依赖可判定的字段和证据关系。
6. 保存 hypothesis/refinement/no-data/technical-failure 及其输入指纹，下一周期读取已承诺的工作。相同失败需改变证据或策略才重试；设置全局搜索上限与长期无候选诊断，不能无限循环。

**验收**：V118 原始请求/响应能定位到相同问题，但不是要求所有历史响应都“修成通过”；新通用恢复在未见过的坏样本上有效；有可学模式的合成测试能产生可验证候选，无模式/错误标签/缺来源对照不会被强迫产生候选。真实是否产生有用候选由 T7 决定。

### T5：证明“真的进化”，而不只证明状态变化（F8）

依赖 T1–T4。先做独立评估工具与报告，不直接改变现有生产晋升门槛和历史 Archive 排名。

1. 将 contract validity、测量/提取准确性、Signal 与结果的关联、整个 Plan+Registry 的收益分开报告。Signal 的 positive/negative 是某个测量维度的方向，不是该案例未来一定 surge/non-surge。
2. 对新 Signal/更新版本使用独立 issuer、冻结文档与输入协议评估；实际结果保存到 case 级，包含证据与 execution status。模型作者自写 fixtures 只能证明可执行性，应补独立的正例、反例、无关材料、缺数据、时间边界 fixtures。
3. 默认 4–8 案例、2 个 decisive 和 correct>wrong 不足以支持“大概率有效”。确定最小实际收益、样本量/精度目标、容忍退化、重复次数与试验次数上限后再冻结协议；这些参数需明确批准，不在代码里猜。
4. 建立配对对照：基线 Plan+旧库；候选 Plan+旧库；基线 Plan+新库；候选 Plan+新库。预算有限时先固定 Plan 比新旧库，再固定库比新旧 Plan。这是系统级评估工具，不引入 Shapley 或逐轨迹因果归因系统。
5. 配对使用相同案例、相同可用来源 corpus、同模型配置与同 budgets。检索策略本身可变，但其增益需单独报告；不能候选多拿数据而把提升全部归因于 Signal skill。
6. 复用完全相同输入的 response；另设独立重复实验衡量模型方差。固定 temperature=0 不能替代方差评估。按 issuer 分组估计不确定性，报告 paired confusion/F1 差异、覆盖率、失败率和成本，不只挑一次最好分数。
7. 持续尝试会过拟合 Discovery/Validation。建立未进入 proposer/critic 的确认评估批次和使用台账，失败样本不能反馈后仍称独立 holdout；达到预先规定检查点后再申请一次封闭 Locked Test。禁止按结果不断更换 confirmation cohort。
8. 现有累计历史 F1 跨 Registry、跨随机 cohort 排名是**现有明确设计**，不是此次发现的实现 bug。先把它当候选搜索启发式；如要改为可比性分层或重评 champion，必须先改 architecture 再改模块 spec，不能偷偷重排旧 Archive。

**验收**：能明确区分“晋升了一项能力”“能力被实际使用”“有可信系统收益”。无收益的实验必须输出 no_gain；测量准确性提高但尚无 F1 增益可单独报告，不能冒称完成收益目标。

### T6：建立泛化可靠性验收矩阵

测试重点放在组合性质，不能仅复现某只股票、某个数字或某模型报错。

| 维度 | 必测内容 |
| --- | --- |
| 格式/API | 缺字段、额外字段、重复 item ID、乱序、截断 JSON、拒答、空 output、429/5xx/超时、usage 缺失、能力不支持 |
| 证据 | 引用不存在、错文档、错期间、未来信息、单位/币种混淆、字面正确但不支持结论、被截断的反证、第三方/ETF 新闻 |
| 恢复 | 初始失败后纠错成功；一个坏 item 加多个好 item；纠错引入新错误；无改善重复；合法 no_match；来源缺失与程序错误区分 |
| 持久化 | 每个 checkpoint 中断；重复 resume；并发运行拒绝；同文档并发 append；provisional 多次复评；promotion 半途崩溃 |
| 泛化 | 改写公司/时间/数字/语言风格、重排列表/JSON、改变证据位置、换 provider response envelope；不能依赖原报错措辞 |
| 错误分布 | 0%、10%、20% 的注入强度；既测分散也测来源/行业/Signal 聚集故障；损坏反证与损坏支持证据分别测试 |
| 无学习对照 | 无效/重复候选、打乱标签的研究对照、同 Plan 同库重复、只有 source 增量、候选未执行、假 version bump |

不要在 injected failure 后删除案例再算好看 F1。保持评估 cohort 不变，记录完整性与有效性；缺关键证据的结果不能混入可晋升成绩。不能要求错误分布改变后 F1 数值绝对相同；要求可评估性、数据不污染和无虚假晋升，质量变化如实报告。

建议的试运行可靠性目标（待批准，不是当前结果）：每个核心角色的首次技术/结构合格率至少 95%，有界恢复后至少 99%；证明性不变量在所有确定性/故障测试中零违反。语义正确率另建人工或独立评审标注集，不用 schema pass 代替。要报告样本数与置信区间，不能拿十条样本宣布达到 99%。

这些只是起点：假设 200 个必须成功的步骤各自独立且成功率 99%，全部成功约为 `0.99^200 = 13.4%`。因此还必须测试**整轮可恢复完成率**，而不是只盯单次成功率。该算式是示意，真实错误通常有关联。

跨模型验证先用至少两种独立 provider/模型配置做小样本 pilot，以真实错误谱决定扩展数量；外部运行需沿用已批准的目的地、payload、预算边界，若无现成授权则先提供精确待执行合同。离线 mock 不能代替真实 API 行为验证。

### T7：分阶段真实闭环验收

1. 离线 replay 与模拟故障全部通过，保留旧失败的原始证据。
2. 新 code-bound workspace 小规模运行完整 Basic→retrieval→hard/soft execution→reflection→prediction；核对实际 wire 请求与最终消费证据，不仅看控制台。
3. 运行 Slow：分别证明 Mining 和 Update 的触发、候选生成、隔离、fixtures、独立验证、provisional/rejected/promoted。自然运行没有更新目标时不能伪造一个 production Update；该分支先由受控集成测试覆盖。
4. 出现真实合格候选才晋升。没有则报告瓶颈属于候选搜索、信息覆盖、测量准确性还是独立效用，并在同一批准搜索预算内按输入变化推进。
5. 下一 Fast 读取新 registry hash 和新版本：查 request/card、selected ref、执行证据、ResearchState/Predictor 使用路径及 committed learning event。仅 hash 变化不满足此项。
6. 执行 T5 的独立收益验证。运行完成、能力晋升、下游使用、收益确认分别给出证据。
7. 在预先冻结的预算/周期上限内仍未获得可信增益，结论是“当前设计/数据下未证实进化”，不能继续无限消耗或降低验证门槛。

**总完成条件**：执行与恢复正确；至少一次真实、实质的新能力通过独立验证并提交；后续 Fast 确实使用；最终收益评估达到事先批准的标准。只有前三项完成时，应称“闭环可运行”，收益仍未完成。

## 6. 需要明确批准的设计决策

本方案不直接修改以下规范。实施 agent 应准备具体 schema/实验配置供审阅；用户若已明确批准相应设计，不应重复索要许可。

| 决策 | 推荐方案 | 影响与规范位置 |
| --- | --- | --- |
| D1：执行/纠错/检索/复评 record 演进 | 使用结构化 issue、execution envelope、版本化 retrieval、可追加 evaluation attempts；旧记录只读 | 更新 owning specs、序列化与迁移/拒绝策略；不改变四态结果和标签定义 |
| D2：有效进化判据 | 增加独立确认评估；样本量、最小实际收益、容忍退化、重复/检查次数按 pilot 和预算预先冻结 | 任何改变自动晋升 gate/数据所有权，先检查并更新 `spec/architecture.md` 的固定门槛与盲评边界 |
| D3：历史 Plan 排名 | 第一阶段保留历史 Archive；独立报告验证收益。只有证据证明排名失真阻碍搜索后再提可比性分层/重评 | architecture 当前明确禁止旧 Plan 重评/归一化；修改此项必须得到明确批准并自顶向下更新 |

不建议当前增加：新的大规模向量数据库、知识图谱、复杂 agent 通信、自动改 validator/gate、无界重试、通过定向提示强迫某候选通过。源码文件很大，但只应在通用错误/投影边界落地后按已有职责做小范围提取，不能把本次修复扩大成全项目重构。

## 7. 给实施 agent 的执行指令

```text
目标：按 progress/self-evolution-action-plan-2026-09-06.md 修复通用边界，
使 Fast/Slow 可恢复执行，并通过独立证据验证实际进化收益。

先检查当前 HEAD、AGENTS.md、spec、dirty state 和最新 committed pointers；
本文审计基线为 aa2f57a，若代码已变，先确认每个 F 项是否仍成立。
不要把报告当作改变固定研究语义或外部执行的自动授权。

顺序：T0 -> T1 -> T2 -> T3 -> T4 -> T5/T6 -> T7。
T6 的确定性和故障测试随 T1 起逐包增加，不能留到最后才补。
T3 的纯存储修复可独立提前，但涉及新执行 record 的部分须等 T1 定稿。

每包先更新 owning spec，再按依赖实现；每包提供具体变更、验证和未解决风险。
不修改标签、Binary F1、PIT、稳定版本、授权、提交指针等固定语义来促成通过。
遇到 ancestor spec 冲突先报告 exact conflict；遵循 D1-D3 的批准范围。
旧运行和 candidate/response 是不可变审计证据；新代码执行使用新合同。
不要修改、stage 或 commit unrelated user files。

验收既要复现已确认缺陷，也要有未见输入、重排/改写、故障组合和无增益对照。
重点证实 provisional 可跨周期复评、错误不污染 profile、合法兄弟项被保留、
新 Signal 能晋升并在下一 Fast 实际执行，最终独立对照有可信收益。

每次项目变更结束同步 progress/status.md、追加 changelog，运行相关测试与 lint，
只提交当前任务文件，创建 git checkpoint。
不把 tests pass、cycle committed、candidate created 或 registry bumped 单独报为目标完成。
```

验证命令（使用项目当前可用的 Python 3.11+，本次如下）：

```sh
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests
bash scripts/lint_repo.sh
git diff --check
```

## 8. 本次本地探针与审计边界

均只在临时目录或内存运行，无外部访问：

- RawInfoStore 同根双实例：新增记录后旧实例 search 返回 0；相同记录再次 append 报已有路径。未观察到 live 数据损坏，确认的是接口行为缺口。
- Signal 当前 request 形状：11 篇同来源、不同日期文档，最旧唯一含目标证据；max_documents=10 且 query 为空时返回 resolved，却排除目标文档。
- Candidate validation：同 hash 先写 provisional，再写 accepted，第二次得到 `conflicting immutable JSON artifact`。
- Frozen registry：修改 skills、parameters 和嵌套 profile 成功，冻结哈希字符串未变。未声称 live 已发生这种修改。
- V118 E1：用批准的 development Discovery 构造当前 `_slow_role_identity_guard_inventory`，原始 E1 input 在 `cases[0].evidence[0].content_excerpt` 即被同域 guard 拒绝；初始输出还命中 CHT 和 L/E/S 等短 ticker，纠错输出命中 CHT/Chunghwa Telecom。必须修边界，不能简单放行全部身份检查。
- 所有 probes 只验证局部行为，不等于新的 live 运行或最终收益证明。

# Slow Round Signal Mining 重构行动方案 v2（2026-09-17）

> 本方案替代 2026-09-16 版的执行顺序和中段架构建议，但不覆盖旧方案及其
> 历史结论。它是设计/实施方案，不代表任何新的 live run 已执行。

## 0. 结论与目标

### 0.1 核心结论

当前 H1/H2/H3 与 E1/E2 的主要问题不是每个环节单独错误，而是它们形成了多层
有损交接：Raw Info 被重复筛选、截断、抽取和再投影，潜在的关系型 Signal 可能
在进入候选验证前丢失。

因此本次不再把 H1/H2/H3/E1/E2 作为生产挖掘链路，而是：

- 保留已有 Signal Update 管线及其独立契约；
- 保留统一的 fixture、issuer-disjoint holdout、paired effectiveness 和原子晋升门；
- 用一个受控、特化的 `LabelAwareMiningController` 替代生产 H/E 中段；
- 让 hypothesis validation 和 open-ended discovery 共用同一套 PIT Evidence Graph；
- 将 E1/E2 降为可选 shadow baseline，不再作为发现新 Signal 的必要路径。

这里的 open-ended discovery 使用 positive/control 标签，因此正式称为
`label-aware discovery` 或“监督式 Signal 挖掘”，不称为无监督挖掘。

### 0.2 第一性原理目标

Slow round 只需要完成四件事：

1. 根据 trajectory、meta-memory、Signal 统计和失败记录，更新已有 Signal 或提出新的研究方向；
2. 在固定的开发集和 PIT Raw Info 上验证方向，允许跨文档、跨期间和多事实组合；
3. 生成带完整证据接地的 candidate；
4. 用不参与生成的独立 holdout 验证，只有通过全部门槛才进入 Signal Registry。

### 0.3 非目标

- 不建设通用 Agent framework；
- 不改变固定 Discovery 标签、预测目标、评分、holdout 门或 promotion 门；
- 不把标签传给 Fast Predictor、SignalExecutor 或 Locked Test；
- 不以降低调用次数换取更低的证据覆盖；
- 不引入新的供应商、在线队列或周期中途刷新语料；
- 不因追求非零 candidate 而放松任何验证门。

## 1. 目标架构

```text
冻结的 Slow 输入
  ├─ trajectory / meta-memory / Signal stats / failure records
  ├─ issuer-disjoint dev/check sampling manifest
  ├─ PIT Raw Info
  └─ stable Signal catalog + measurable evidence manifest
                    │
          共享 Evidence Graph 基座
  ├─ Fact：concept/unit/period/value/source span
  ├─ Relation：period change / ratio / co-occurrence / before-after
  ├─ narrative event + bounded context
  └─ content hash / available_at / query coverage / omitted coverage
                    │
       LabelAwareMiningController
          ├─ hypothesis validation seed
          └─ open-ended discovery seed
                    │
        candidate / no-pattern / deferred
                    │
       统一 candidate validation
  fixture → issuer-disjoint holdout → paired effectiveness → promotion
                    │
       mining ledger → reflection → 下一 Slow cycle
```

生产链路不再是：

```text
H1 → H2 → H3 或 E1 → E2
```

而是：

```text
共同证据基座 → 受控挖掘器 → 统一验证出口
```

## 2. 共享 Evidence Graph

这是本次最重要的基础设施。Agent 不应直接面对若干互相不兼容的 excerpt，而应
通过同一套结构化证据接口逐步读取信息。

### 2.1 Fact 节点

每个确定性事实至少包含：

```json
{
  "fact_ref": "fact-opaque-001",
  "case_ref": "case-opaque-001",
  "concept": "source-owned concept",
  "unit": "USD",
  "period": {"start": "...", "end": "..."},
  "value": "runtime-visible value",
  "document_ref": "document-opaque-001",
  "exact_span": "verbatim source literal",
  "content_hash": "...",
  "available_at": "..."
}
```

概念、单位、期间和值必须保持绑定，不能再通过“某个数字附近的字符窗口”让模型
自行推断它们的关系。

### 2.2 Relation 节点

为支持关系型 Signal，基座还要表达：

- latest 与 comparable prior；
- 同概念的期间变化；
- numerator / denominator；
- 同一案例内的事件共现；
- before / after；
- 多文档之间的互补支持；
- 观察到但未满足完整证据条件的关系。

关系必须由确定性代码根据来源记录构造。LLM 可以提出待检验关系，但不能伪造
事实、期间或计算结果。

### 2.3 Evidence fetch 的边界

`fetch_case_evidence` 可以有界，但不能只把 Agent 的 query 当成完整搜索范围。
每次返回必须同时记录：

- 请求的来源族、query、时间窗和 case refs；
- 选中的文档/事实/关系；
- 被限额排除的文档或概念；
- query coverage；
- 是否存在尚未读取的同源证据；
- 每个输出项的内容哈希和 PIT 判断。

Agent 可以请求更深的证据，但 no-pattern 只能在账本覆盖范围内成立，不能把“我没有
请求到”写成“数据中没有”。

### 2.4 工具最小集合

第一版只需要三个 runtime-owned 工具：

1. `fetch_evidence`：读取有界的文档、Fact 和 Relation；
2. `compute_statistic`：按冻结规则计算数值和比较关系；
3. `read_span`：对已引用文档做一次有界上下文扩展。

不加入通用搜索、任意代码执行、任意文件读取或任意候选修改工具。

## 3. LabelAwareMiningController

这不是通用自主 Agent，而是固定状态机中的受限模型决策器。

### 3.1 两个入口

#### Seed A：hypothesis validation

输入：

- trajectory 和 Slow feedback；
- meta-memory；
- 现有 Signal 统计与失败类型；
- `measurable_evidence_manifest`；
- stable Signal catalog；
- dev positive/control 案例索引。

模型提出或选择一个有限 hypothesis，然后直接请求 Evidence Graph 验证，不再经过
独立 H2 ranker 或 E1 observation 压缩。

Hypothesis 准入条件：

- 在 manifest 中有对应可测证据族；
- dev 数据中存在实际可用的证据路径；
- 不重复已有 Signal；
- 测量对象和固定 positive/control 对比明确；
- 不使用未来数据或新造预测目标；
- 能写出至少一个可执行 falsifier。

“manifest 可测”只是必要条件，不是实际数据充分的证明。实际证据 readiness 必须
在工具调用后再次确认。

#### Seed B：open-ended label-aware discovery

输入同一 Evidence Graph，但不要求先有 H1 hypothesis。模型可以在 dev positive/control
案例之间寻找重复的 Fact/Relation 组合，并提出候选测量。

该模式的标签边界是：

- 可以读取 dev 标签，用于发现跨组差异；
- 不能读取 check/holdout 标签或其证据；
- 不能使用身份、文件位置、抓取状态等伪特征；
- 发现候选后，必须由本地代码重算测量和核对证据。

### 3.2 固定 action enum

Agent 每一步只能返回以下动作之一：

```text
inspect_manifest
inspect_catalog
fetch_evidence
compute_statistic
read_span
compare_groups
propose_candidate
record_deferred
record_no_pattern
```

runtime 决定：

- 动作是否允许；
- 输入是否越界；
- 工具如何执行；
- 结果如何写账本；
- 何时终止；
- 是否可以进入 candidate validation。

模型不得直接写入 ledger、改变样本、改写标签、修改预算或修改候选验证门。

### 3.3 循环状态

每个 seed 的状态只允许在以下状态之间转换：

```text
ready
→ exploring
→ evidence_ready
→ candidate_proposed
→ locally_validated
→ terminal
```

异常或数据不足使用独立状态：

```text
technical_failure
evidence_unavailable
deferred_budget
no_pattern_with_coverage
```

这些状态不能互相混淆，也不能把技术失败计成领域上的 no-pattern。

建议第一版使用固定的小步数上限，由 contract 冻结；初始建议每个 seed 最多 12
个逻辑动作、每周期总动作数不超过既有 Slow 预算。实际数值在离线回放后确定，
不得由模型自行决定，也不得因为“多试几次”无限扩张。

不持久化自由形式 thought。若需要可审计理由，只保存结构化的 action rationale、
evidence refs 和终局 disposition。

## 4. 三类业务路径

### 4.1 Update 已有 Signal

保持现有 Update 语义和验证边界：

```text
执行统计/失败诊断
→ 选定已有 Signal
→ 提出最小变更
→ fixture
→ paired holdout
→ promotion 或 rejected/deferred
```

Update 可以使用 `compute_statistic` 的确定性输出，但不随本次挖掘重构改变其
candidate contract、定义不可变项或晋升门。

### 4.2 Hypothesis validation

Seed A 的终局只能是：

- `candidate_proposed`：有完整测量、适用性、falsifier 和证据；
- `evidence_unavailable`：方向合理但 PIT 证据不足；
- `refined`：证据显示定义不完整，但可以明确修改；
- `rejected`：dev 证据直接反驳；
- `no_pattern_with_coverage`：在实际覆盖的证据范围内没有形成稳定关系。

### 4.3 Open-ended discovery

Seed B 的终局只能是：

- 一个或多个去重后的 candidate proposal；
- `no_pattern_with_coverage`；
- `evidence_unavailable`；
- `technical_failure`。

它不再要求先把每个案例压缩成最多六条 observation。可以保留多个精确 spans、多个
文档 refs 以及确定性 Relation，但仍受 Evidence Graph 和 transport budget 限制。

## 5. 标签、PIT 和反过拟合边界

### 5.1 标签边界

Slow Mining 使用后验标签是允许的；这不是 Predictor 泄漏。边界是：

```text
dev labels → 可以用于发现和提出 candidate
holdout labels → 只能用于最终验证
Fast Predictor → 永远不能接收后验标签或 Mining rationale
```

### 5.2 证据边界

- 所有 Fact/Relation 必须满足 `available_at <= prediction_time`；
- post-outcome 文档和实现结果不能成为候选发现输入；
- source coverage 的差异不能直接被当作业务特征；
- excerpt 不足只能产生 evidence-unavailable，不能产生事实不存在；
- 公司 identity、ticker、文件顺序和抓取成功状态不是可接受 Signal，除非 Signal
  定义明确研究这些对象且通过独立验证。

### 5.3 Dev/check 分离

- Agent 只能在冻结的 dev cohort 上生成候选；
- check/holdout issuer 与 dev issuer 保持不相交；
- check/holdout 的原始 evidence 不进入 Agent 生成上下文；
- 候选生成后由本地 runtime 执行 fixture 和独立效果评估；
- 不能因 holdout 失败而回头修改候选，再把修改后的结果算作同一次验证。

## 6. Mining Ledger

账本由 runtime 拥有，Agent 只能提供结构化 rationale。

每条记录至少包含：

```text
cycle_id / seed_id / action_id
action / input_hash / output_hash
case_refs / evidence_refs / source_types
PIT status / coverage / omitted coverage
usage / cost / terminal disposition
```

终局一致性要求：

- candidate 的每个证据 ref 都存在于账本；
- 每个 promising 分支必须进入 candidate 或有明确 abandonment 原因；
- no-pattern 必须引用实际探索过的 evidence family、concept/relation 数量和未覆盖范围；
- technical failure、quota pause、evidence unavailable 不得进入领域 no-pattern 统计；
- 账本 append-only，恢复时依据已提交 checkpoint 重放，不重复消费已完成动作。

账本反馈进入下一周期 reflection，但反思只能改变下一周期的搜索策略，不能改变已经
冻结的 dev/check 样本或历史验证结果。

## 7. 实施阶段

### Phase 0：更新方案与权威规格

先修改本方案和相关 spec，再实施代码：

1. 新建 `spec/src/stock_opportunity_agent/research/signal_mining_agent.md`；
2. 更新 `signal_evolution.md` 的挖掘契约；
3. 更新 `evolution_signal_roles.md`，将 H/E 标为兼容/对照路径；
4. 检查 `spec/architecture.md` 是否需要祖先层措辞调整；
5. 明确 Seed B 为 label-aware discovery；
6. 明确 no-pattern 的覆盖标准和 candidate 非零不属于成功门槛。

验收：用户确认 spec；不执行 live 调用。

### Phase 1：Evidence Graph 最小实现

优先实现共享事实和关系表示，复用现有：

- `documents_as_of`；
- `RawInfoRequest` 和 resolver；
- `_company_facts_context`；
- V88 market calculation anchors；
- `_mask_identity_values`；
- 现有 request trace 和 cost ledger。

实现 `mining_agent_tools.py` 或等价模块，但先固定数据模型，再写工具函数。

验收：

- concept/unit/period/value/source span 始终绑定；
- PIT、content hash 和 identity mask 可验证；
- 多期间、分子/分母和多文档 Relation 可重放；
- 工具返回 omitted coverage；
- 不向 manifest 泄露具体值；
- focused tests、full tests、lint 通过。

### Phase 2：受控 Mining Controller

实现特化 controller，而不是通用 Agent framework：

1. 固定状态机和 action enum；
2. 实现 Seed A/B；
3. runtime 执行工具和 ledger；
4. 保留现有 structured request trace；
5. 生成 candidate 后调用现有 validation pipeline；
6. 不持久化自由 thought；
7. 现有 H/E 代码暂时不删除，仅作为 shadow 对照。

验收：使用 fixture caller 完成：seed → action → tool → ledger → terminal → validation。

### Phase 3：零调用历史回放

在 V87/V89 等历史 workspace 上做确定性 replay：

- 不重写历史 artifact；
- 不调用外部模型；
- 对既有 Raw Info 做本地工具重放；
- 检查 candidate evidence 是否可回溯；
- 检查 no-pattern 是否真实覆盖；
- 比较旧 H/E 和新 controller 的信息到达率，而不是只比较 candidate 数量。

验收：零身份/标签泄漏、零越界工具调用、零虚构 evidence、恢复可重放。

### Phase 4：受控候选闭环

增加固定 fixture，覆盖至少：

- 单事实 Signal；
- 多期间 Signal；
- 分子/分母 Signal；
- 跨文档组合 Signal；
- narrative event Signal；
- 证据不足；
- 技术失败；
- no-pattern with coverage。

至少有一个候选能够在本地受控数据中完成：

```text
discovery → candidate → fixture → holdout simulation → rejection/promotion decision
```

这里不要求生产 live 一定产生 candidate，但必须证明候选路径不是结构上不可达。

### Phase 5：一次 live shadow cycle

只有 Phase 0–4 完成后才进行一次 live shadow：

- Agent 轨和旧对照轨使用相同冻结输入和相同 dev/check 边界；
- 两轨结果分开保存；
- 新轨不修改旧轨历史；
- 审计实际请求、工具调用、证据和终局账本；
- 失败时保留旧轨，不切换生产路径。

切换条件不能只看 candidate 数量。必须同时满足：

- evidence 接地率达到 contract 要求；
- 无标签/身份泄漏；
- no-pattern coverage 完整可审计；
- 技术失败和 evidence-unavailable 分类正确；
- 至少一个受控候选通过 fixture；
- holdout 执行和 paired gate 仍然生效；
- 成本、步数和数据请求没有越过冻结上限；
- Update 质量和既有 Signal 执行没有回归。

### Phase 6：生产切换

只有 shadow 验收通过后：

1. 将 controller 接入生产 Mining 入口；
2. 保留 H/E 的只读历史解析和 replay 能力；
3. 新周期不再调用旧 H/E 生产路径；
4. 观察至少一个完整提交周期；
5. 再按 AGENTS.md 将旧生产模块归档/删除，并同步 spec、status、changelog。

不要在 shadow 只有一轮、只有 candidate 数量优势、或只有模型输出非零时删除旧路径。

### Phase 7：扩大 cohort

只有候选证据链和验证闭环稳定后，才扩大 dev/check cohort。扩大顺序：

1. 保持相同 PIT 和 issuer-disjoint 规则；
2. 逐步增加 dev evidence coverage；
3. 单独观察 cost、technical failure、evidence unavailable 和 holdout eligible rate；
4. 不同时改变标签、评分、门槛和 Signal 定义。

在线语料版本接口继续单独立项，刷新只能发生在周期边界。

## 8. 正确的验收标准

### 必须满足

- 共享证据模型可表达单事实、组合事实、跨期间和跨文档关系；
- Agent action、工具输入输出和 ledger 可完全重放；
- dev 标签和 holdout 标签边界正确；
- 所有 candidate evidence 可回溯到 PIT 原文或确定性计算行；
- technical failure、evidence unavailable、no-pattern 和 rejected 分开；
- 任何 candidate 都进入现有 fixture/holdout/promotion 门；
- 反思能够消费本轮真实账本并影响下一轮搜索策略。

### 不作为硬条件

- 每个 Slow cycle 必须有新 candidate；
- 每个 Slow cycle 必须有 Update candidate；
- candidate 必须 promotion；
- Agent candidate 数必须大于旧链路；
- no-pattern 必须被解释成 Signal 不存在。

### 可接受的零结果

```text
no-pattern-with-coverage
evidence-unavailable-with-recovery-condition
technical-failure-with-preserved-sibling-work
deferred-budget-with-resumable-ledger
```

这些结果只有在账本、来源范围、未覆盖范围和恢复条件完整时才算正确完成。

## 9. 风险与处理原则

| 风险 | 处理 |
|---|---|
| Agent query 造成搜索偏差 | 保留 evidence inventory 和 omitted coverage，不能只记录 query 结果 |
| 给标签后模型过拟合 | 只允许 dev 生成，holdout 隔离，严格 evidence/fixture/paired gate |
| 组合 Signal 被压碎 | 使用多 span、Fact 和 Relation，不强制单文档单 literal |
| Agent 循环失控 | 固定 action enum、状态机、步数、工具和 cost 上限 |
| no-pattern 被误报 | 必须引用 ledger coverage，技术失败不得进入 no-pattern |
| 追求非零污染结果 | 移除 Mining>0 硬验收，候选质量由后端门决定 |
| 新旧路径同时演化 | shadow 期间旧轨只读，切换后明确停用旧生产路径 |
| 反思再次扩大上下文 | 使用完整可寻址 ledger units 和预算内的确定性投影，不复制原始全文 |

## 10. 执行前检查

执行任何代码或 live run 前必须重新核对：

1. 当前 `git rev-parse --short HEAD` 与本方案引用是否一致；
2. 工作区是否有无关未跟踪文件；
3. 当前 authoritative round/cycle pointers；
4. V89/V90 是否只是历史证据，不被覆盖；
5. 相关 spec 是否已经更新并通过用户确认；
6. 当前预算、外部授权、Raw Info root 和 Locked Test 状态。

测试使用项目兼容 runtime：

```sh
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests
bash scripts/lint_repo.sh
```

本方案不授权新的 live 外部调用；新端点、新数据供应商或超出现有预算的执行仍需
单独确认。

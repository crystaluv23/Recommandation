# 叙事/非结构化因子挖掘行动方案 v2

状态：设计方案，尚未实施。基于
`reports/narrative-factor-mining-design-2026-09-17.md` 的审阅结果整理。

## 0. 执行结论

当前问题不是 LLM 不会发现叙事因子，而是现有挖掘接口让结构化证据更容易被
发现、比较和证明：`NarrativeEvent` 已经存在，但 controller 主要向模型暴露
事件引用和数量，事件正文不可直接读取，`read_span` 也只能读取 fact。

本方案不重写现有 Slow Controller，也不降低现有验证门。实施顺序是：

```text
spec/contract
  -> 原始叙事证据可读
  -> 模态探索机会义务
  -> 叙事 candidate contract
  -> 可选 AttributeProjection
  -> materialization/fixture/holdout
  -> 离线 replay
  -> shadow
  -> 生产观察
```

核心原则：不强制每轮产出叙事 candidate，但必须保证叙事证据获得真实、可审计
的探索机会。

## 1. 目标与边界

### 目标

- 结构化与叙事因子在发现、比较、验证、执行阶段拥有对称的能力；
- 叙事证据可以从目录、原文 span、candidate、Signal skill 一直回溯到 PIT
  Raw Info 文档；
- 模型可以基于原始叙事文本提出新语义，而不是只能从预定义事件词表中选择；
- 模态偏差进入 ledger 和 reflection，并能被跨周期观察；
- 现有 Signal Apply、Update、fixture、holdout、paired gate、promotion 和
  next-cycle Registry visibility 不回归。

### 非目标

- 不把 LLM 变成可以任意搜索、读文件或修改 candidate 的通用 Agent；
- 不改变 PIT、身份掩码、dev/check 隔离、固定标签、验证门和 Locked Test 边界；
- 不要求每个 Slow cycle 都产出叙事 candidate 或 promotion；
- 不用“每轮必须有叙事 candidate”的硬配额制造假探索；
- 不修改 V98 已冻结的 workspace、contract 或历史结果。

## 2. 必须先锁定的设计决策

### 2.1 原始叙事文本是权威证据

新增或扩展 `NarrativeSpan`，至少保留：

```json
{
  "event_ref": "event-...",
  "case_ref": "case-...",
  "document_ref": "document-...",
  "source_family": "news",
  "title": "masked title",
  "excerpt": "masked bounded excerpt",
  "exact_span": "verbatim source span",
  "content_hash": "...",
  "available_at": "...",
  "published_at": "..."
}
```

任何 AttributeProjection 只能作为索引、聚合、排序和 reflection 输入，不能
成为叙事 candidate 的唯一证据，也不能把投影未命中解释成事件不存在。

### 2.2 用探索机会义务替代 candidate 配额

当 manifest 显示叙事数据可用时，每个 mining seed 必须满足以下之一：

- 完成至少一次 narrative catalog/read；
- 记录 `narrative_evidence_unavailable`；
- 记录 `deferred_budget`、`technical_failure` 等控制面终态。

runtime 不强迫模型提出 candidate，也不强迫 candidate 通过验证。探索机会是
硬义务，candidate 结果不是硬义务。

### 2.3 先打通 raw narrative path，再实现 projection

正确顺序是：

```text
原始文档目录 -> 原始文本读取 -> LLM 语义发现 -> 证据接地
                                      -> 可选 AttributeProjection 聚合
```

不能先用 K=24 或最小支持度过滤叙事，再让 LLM 从过滤后的事件中发现因子。

### 2.4 新增 run contract 和 successor workspace

本方案涉及 action surface、budget、evidence schema、projection hash 和
modality obligation，必须创建新的 contract/workspace。V98 保持只读，不在原
workspace 内追加不兼容字段，也不把新方案的结果写入 V98 的历史链。

## 3. Phase 0：更新 spec 与运行契约

### 修改范围

- `spec/src/stock_opportunity_agent/research/signal_mining_agent.md`
- `spec/src/stock_opportunity_agent/research/signal_evolution.md`
- 必要时同步 `spec/src/stock_opportunity_agent/research/evolution_runtime.md`
- 更新 `progress/status.md` 和 `progress/changelog.md`

### 必须定义的契约

1. `NarrativeSpan` 的字段、生命周期和 evidence ref 语义；
2. catalog、fetch、read 的输入输出与 ledger 行为；
3. `discovery_only` 和 `evidence_usable` 的区别；
4. narrative exploration obligation 和可接受终态；
5. modality coverage、projection status 和 source-family coverage 字段；
6. candidate 的 narrative semantic predicate；
7. raw span、AttributeProjection、LLM skill 的证据优先级；
8. 新 contract/workspace 的迁移和回滚边界。

### 推荐的第一版 action 设计

暂不一次性增加三个新 action，优先复用现有闭合集合：

- `inspect_catalog`：返回 family、时间窗、文档数量、masked 摘要和 opaque
  `doc_ref`；
- `fetch_evidence`：继续负责批量选择、PIT 过滤和 coverage accounting；
- `read_span`：从只能读取 `fact_ref` 扩展为可读取 `fact_ref`、`event_ref`、
  `document_ref`，并接受 bounded offset/length。

这样可以减少状态机、纠错、预算和 replay 的新增面。若后续证明需要独立的
`browse_sources`、`browse_documents`、`read_document`，再作为新的 contract
版本增加。

### Phase 0 验收

- spec 明确结构化与叙事证据的对称边界；
- candidate、fixture、Signal execution 的字段可以表达叙事语义；
- run contract 可以绑定 modality 配置、projection hash 和 browse budget；
- V98 contract 和历史 artifact 不变；
- 没有开始新的 live 外部调用。

## 4. Phase 1：打通叙事证据读取

### 主要文件

- `src/stock_opportunity_agent/research/mining_agent_tools.py`
- `src/stock_opportunity_agent/research/mining_controller.py`
- `src/stock_opportunity_agent/research/mining_role_model.py`

### 实施内容

1. `fetch_evidence` 返回 narrative event refs、source family、时间和最小可读
   摘要，而不是只返回事件数量；
2. `inspect_catalog` 返回按 `family -> window -> doc_ref` 组织的 bounded
   文档目录；
3. `read_span` 支持读取 event/document，并返回 masked bounded text；
4. 每次读取都执行 `available_at <= prediction_time`；
5. 每次读取都写入 append-only ledger，并保存输入/输出 hash；
6. catalog 摘要标记为 `discovery_only`，不能直接作为 candidate evidence；
7. 仍然保持“无匹配不等于 negative”，只允许 unavailable 或 coverage 不足。

### 身份与文本边界

- title、summary、excerpt、exact span 都经过同一套身份掩码；
- mask 后执行完整 identity scan，而不是只依赖少量 alias 替换；
- 复用现有 visible-text projection，避免 SEC SGML/XBRL 样板占用事件槽；
- `historical_price`、provider envelope 等非叙事族不得投影成 NarrativeEvent；
- source family coverage 按归一化 family 统计，不按原始 source_type 重复计数。

### Phase 1 验收 fixture

- news、filing、transcript 各至少一个正例；
- 同义改写仍可读且可被 LLM 理解；
- 词面相似但语义不同的文本不会自动成为正例；
- 文档晚于 prediction time 只能返回 unavailable；
- 无可见文档、部分文档和超过 limit 的文档分别记录；
- HTML/XBRL 样板、provider envelope、历史行情不会成为叙事事件；
- action、ledger、read result 可以零调用 replay。

## 5. Phase 2：加入模态探索机会义务

### Runtime 状态

在 controller view 和 ledger 中增加：

```json
{
  "modality_coverage": {
    "structured": {"available": true, "explored": true},
    "narrative": {
      "available": true,
      "explored": false,
      "status": "required"
    }
  }
}
```

### 行为规则

- narrative 可用时，seed 不能在完全未读取 narrative 的情况下正常结束；
- runtime 可以要求一次 catalog/read，但不要求 candidate；
- narrative 不可用时记录 typed `narrative_evidence_unavailable`；
- budget 不足时记录 `deferred_budget`，不能伪装成 no-pattern；
- browse/read 预算独立于 heavy budget，但总 token、字节和外部 attempt 仍受
  contract 限制。

### 初始预算策略

- heavy：先保持现有 12；
- light：先保持现有 4；
- browse：24 只作为 shadow 上限，不立即冻结为生产常数；
- 每一步设置目录、摘要、正文的字节上限；
- shadow 后按 p50/p95 wire token、实际读取深度和 case coverage 冻结参数。

### Phase 2 验收指标

- `eligible_narrative_seed_count`；
- `narrative_exploration_completed`；
- `narrative_unavailable_count`；
- `narrative_read_count`；
- `narrative_candidate_count`；
- `narrative_materialization_count`；
- `narrative_validation_count`。

## 6. Phase 3：定义叙事 candidate contract

当前 `measurement` 需要扩展为可表达语义谓词：

```json
{
  "measurement": {
    "observable": "large_order_confirmation_event",
    "value_kind": "boolean",
    "normalization": "window-level existence predicate",
    "predicate": {
      "modality": "narrative",
      "source_families": ["news", "filing"],
      "lookback_days": 90,
      "semantic_condition": "confirmed commercial order or purchase commitment",
      "threshold": {
        "field": "amount_usd",
        "operator": ">=",
        "value": 50000000
      }
    }
  },
  "evidence_refs": ["event-..."],
  "falsifiers": [
    {
      "condition": "The text describes only a proposal or memorandum.",
      "expected_observation": "The signal is unavailable or negative."
    }
  ]
}
```

### Runtime 校验

- semantic predicate 必须有 raw narrative evidence；
- predicate 的 source family 必须与 cited evidence 相交；
- amount、date、window 等确定字段必须逐字可回溯；
- 不能引用 check/holdout 标签或 post-outcome 文档；
- query 未命中不能直接等价于 negative；
- candidate 的 evidence refs 必须同时通过存在性和语义接地校验。

## 7. Phase 4：将 AttributeProjection 降为可选索引层

### 实施约束

1. 只读取当前 dev cohort 的 PIT 文档；
2. 不读取 check/holdout；
3. 词表、排序、规则和输入 corpus hash 全部进入 contract；
4. 低频事件不能被 projection 过滤掉；
5. projection 没有结果时，raw narrative path 仍然可提出 candidate；
6. `attribute_ref` 必须保留 exact span、document ref、content hash 和
   available_at；
7. projection 不能把 coverage 差异直接当成业务特征。

### Projection 状态

不要只记录命中/未命中，至少区分：

- `projected_positive`；
- `projected_counter`；
- `projected_unresolved`；
- `projection_unavailable`。

### 特别检查

- 支持度低于阈值的事件仍可由原始文本路径发现；
- 新主题不需要修改核心 controller；
- 新 kind 若需要 projector，必须作为明确 spec/contract 扩展记录，不能继续
  宣称完全零代码。

## 8. Phase 5：接入 materialization 与 Signal 执行

### 主要文件

- `src/stock_opportunity_agent/research/signal_evolution.py`
- `src/stock_opportunity_agent/research/evolution_signal_roles.py`
- 必要时才修改 `src/stock_opportunity_agent/signal_library.py`

### materialization 输入

materialization prompt 必须同时获得：

- candidate predicate；
- cited narrative spans；
- source family；
- prediction/as-of 时间；
- exact span；
- content hash；
- unavailable 条件；
- retrieval policy 和 lookback window。

生成后的 LLM Signal 必须能表达：

- narrative source family；
- lookback window；
- query/retrieval intent；
- LLM 语义判断；
- supporting evidence；
- counter evidence；
- evidence 不足时的 `unavailable`。

### Narrative fixture 族

至少覆盖：

1. 正确订单确认；
2. 仅意向、合作备忘录或未确认协议；
3. 订单取消或延期；
4. 金额低于阈值；
5. 同义改写；
6. 词面相似但语义不满足；
7. 文档晚于 prediction time；
8. 文档存在但证据不足。

这些 fixture 仍然进入原有的 fixture、issuer-disjoint holdout、paired
effectiveness 和 promotion pipeline，不为叙事 Signal 单独放宽门槛。

## 9. Phase 6：离线闭环与 replay

先不发起新的 live 外部调用，执行：

- mining controller focused tests；
- mining agent tool tests；
- narrative closure tests；
- candidate materialization tests；
- Signal execution tests；
- 现有全量 unittest；
- `scripts/lint_repo.sh`；
- V92/V98 Raw Info 的本地 replay。

### 对比维度

| 维度 | 验收要求 |
|---|---|
| Structured candidate | 现有 fixture 和结果不回归 |
| Narrative evidence | 能从文档到 span 再到 candidate |
| PIT | 未来文档只能 unavailable |
| Semantic boundary | 相似词面不能自动视为正例 |
| Ledger | browse/read/action 可完整重放 |
| Validation | 叙事 candidate 走原 validation pipeline |
| Promotion | 不因 modality 放宽 promotion 门 |
| Cost | 不超过冻结的 request/token/byte 上限 |

## 10. Phase 7：Shadow 运行

使用新的 contract 和 successor workspace，不修改 V98。

必须保存：

- 实际 system prompt；
- 每个 model view；
- 每次 action；
- catalog/read/fetch 输入输出；
- exact evidence span；
- candidate predicate；
- materialization request/response；
- fixture、holdout、paired gate 结果；
- modality footprint；
- provider usage、token 和 cost；
- terminal ledger。

第一轮 shadow 只验证结构可达性，不据此宣称叙事 Signal 质量提升。第二轮重点
验证 reflection 是否消费 modality footprint 并改变下一轮搜索策略。

## 11. Phase 8：生产切换与观察

### 切换条件

- narrative-capable seed 都正确完成探索义务或记录 typed unavailable；
- 无身份、标签和 PIT 泄漏；
- 至少一条叙事 candidate 进入标准 validation pipeline；
- structured candidate 无回归；
- candidate evidence 全部可回溯；
- technical failure、evidence unavailable、no-pattern、rejected 分离；
- cost、step、byte 和 attempt 不越界；
- Apply、Update、promotion、next-cycle Registry visibility 均通过。

### 切换后

1. 旧 H/E 路径保留为只读 replay；
2. 新路径观察至少一个完整提交周期；
3. 持续记录 modality exposure、candidate、validation、promotion 和
   availability；
4. 观察周期结束后，再按项目规则归档旧生产代码；
5. 同步 spec、status、changelog，并创建 Git checkpoint。

## 12. 最终验收标准

### 必须满足

- 每个叙事可用 seed 都有实际探索机会；
- 不要求产生叙事 candidate，但不能静默跳过叙事证据；
- 叙事 candidate 可以从 raw span 独立重放；
- positive、counter、unavailable 三类语义均可执行；
- 结构化 Signal 能力无回归；
- 叙事 candidate 仍经过原有全部验证和 promotion 门；
- reflection 能消费真实 modality footprint；
- 下一周期能看到上一周期的叙事探索结果。

### 不作为硬条件

- 每个周期必须有叙事 candidate；
- 每个周期必须 promotion；
- 叙事 candidate 数必须超过结构化 candidate；
- 两个周期就证明长期不坍缩。

## 13. 停止、回滚与异常分类

- narrative read 无法满足 PIT 或 masking：停止该阶段，不降级为结构化-only；
- projection 结果与 raw span 不一致：保留 raw evidence，禁用 projection，
  不删除 candidate；
- candidate materialization 失败：记录 materialization failure，不伪造
  no-pattern；
- provider/client failure：按现有 control-flow 传播，保留 checkpoint；
- evidence unavailable：不进入 negative/no-pattern 统计；
- structured regression：回滚 successor workspace 的 feature flag，不修改
  V98 历史。

## 14. 下一步

下一步只做 Phase 0：更新 spec 和 contract，明确 NarrativeSpan、read 语义、
exploration obligation、candidate predicate 和 migration boundary。Phase 0
完成并通过 focused contract tests 后，才开始 Phase 1 的代码实现。

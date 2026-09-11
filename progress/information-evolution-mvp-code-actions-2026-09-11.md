# 可直接执行的 MVP 函数级施工单

状态：方案，未实现。对应[行为审计与验收要求](information-evolution-semantic-repair-plan-2026-09-11.md)。
基线 `63057b5`；所有路径相对于 `/Users/l/Project/Recommandation`。
下面按 6 个实现批次执行，每批先同步列出的 spec，再修改代码、运行定向测试、提交。
代码块是目标逻辑/伪代码，不是可以跳过现有契约直接粘贴的补丁；“新增”标记的是尚不存在的接口。

MVP 约束：不实现自动分页、新调度/队列平台、JSON Patch 引擎、向量检索、多代理挖掘、
全局配额服务或新数据供应商。保留现有固定数据集、PIT、标签隔离、预算及晋升门槛。
优先修有真实失败证据的代码，不顺带重构整个模块。

## 批次 1：供应商响应验证必须发生在成功缓存之前

**修改 4 处：**

1. `data/sources/alpha_vantage.py`：从 `AlphaVantageClient._query()` 提取
   **新增** `alpha_vantage_json_error(body) -> str | None`，检测该供应商既有错误
   envelope，返回稳定、脱敏的错误原因。未知错误仍失败，不按某公司/某句话补丁。
   `_query()` 调用同一函数，保留裸 transport 情形的兜底。
2. `research/evolution_control.py`：创建数据服务的内部 `managed(source, capability)`
   工厂，给 Alpha Vantage 接入已有 `json_error_detector` 参数。一次覆盖 earnings、
   transcripts、news、prices；不能只修电话会 endpoint。
3. `data/sources/state.py`：`ManagedHttpTransport.get_json()` 和 `post_json()`
   的缓存读取、网络结果写入都经过 detector。已有 text detector 的读取分支也保持
   相同语义。仅有效结果记 `CACHE_HIT`/`FETCHED`。
4. `RawDataCache` **新增** `invalidate(key: RawCacheKey) -> bool`，只撤销指定
   键。失效事件只存 key 和脱敏原因，不存错误正文，不清空正常缓存或 Raw Info。

```python
# ManagedHttpTransport：目标控制流
cached = cache.get_json(key)
if cached is not None:
    problem = validate_provider_response(cached)  # 复用已配置 detector
    if problem is None:
        record_cache_hit()
        return cached
    cache.invalidate(key)
    record_cache_invalidated(key, safe_reason=problem)

require_existing_budget()
body = inner.get_json(url, headers)
problem = validate_provider_response(body)
if problem is not None:
    record_network_error(safe_reason=problem)
    raise_existing_typed_or_generic_error(problem)
cache.set_json(key, body, now)
record_fetched()
return body
```

失效事件如加入 `RequestStatus`，不得算联网消耗；真实失败请求仍计额度。
保留 `DataSourceError` 通用兜底，明确额度失败使用已有 `DataQuotaDeferred`。
若供应商未给可靠重置时刻，允许该类型的 `next_retry_at=None` 并核对所有消费者，
不能伪造时间。所有待写 ledger 的错误按当前请求敏感参数脱敏；伪密钥测试须覆盖
供应商正文回显及底层异常回显。

`data/resolution.py::EvidenceResolver.resolve()` 配套改两点：

- 用 `isinstance(exc, DataQuotaDeferred)` 保留额度原因，不依赖异常类名字字符串。
- `_acquisition_failures` 不再只有 `reason`；用小型私有记录存 reason、retryable、
  next_retry_at。reset 前复用，明确恢复后在现有预算内再试；未知 provider 错误不能
  永久复用。单次 resolve 不循环重试，额度恢复时间未知则等待显式恢复。

**规格：** `data/sources.md`、`data/resolution.md`。
**测试：** `test_data.py::SourceStateTests/AlphaVantageClientTests`，
`test_evolution_control.py::RunControlTests`，`test_data_resolution.py::EvidenceResolverTests`。
重点是生产 builder 真接入 detector、旧污染缓存恢复、有效空数据、未知错误、额度延迟、
脱敏、失效不消耗额度。不能只沿用手工传 lambda 的原有单测。

## 批次 2：修 SEC 历史及表单选择，不新增供应商

**`data/sources/sec_edgar.py`**

从 `recent_filings_as_of()` 抽出一个 **新增私有函数**
`_filings_from_arrays(cik, arrays, as_of_date) -> list[FilingMetadata]`。
保留现有 accession、URL、accepted_at 的解析。recent 和历史分片复用它；
不改 `recent_filings_as_of()` 的含义。

**`data/acquisition.py::SecFilingAdapter.acquire()`**

```python
submissions = client.submissions(cik)
filings = parse_recent(submissions)
pages = overlapping_official_history_files(submissions, lower, as_of)
for page in newest_first(pages)[:3]:
    history = client.historical_submissions(page['name'])  # 已有安全 API
    filings.extend(parse_history(history))
filings = deduplicate_by_accession(filings)
# 再执行既有 form、lookback、available_at 和正文获取规则
```

首批每次 acquisition 最多 3 个相关历史分片，沿用来源请求预算；不加通用爬虫。
分页需来自官方当前 manifest，复用现有 basename 校验。单页失败保留其他页成果。
达到上限而仍有相关分片时记 `history_truncated`；若未拿到所需正文，用已有
`AcquisitionFailure(DataGapReason.REQUIRED_COVERAGE_INCOMPLETE, ...)`，
不能报“无历史数据”。若已有正文，审计仍保留扫描不完整。

**表单路由：** 同一处 SEC 表单分类补齐 `20-F/40-F/6-K`；
`SecFilingAdapter.source_types`、`resolution.py` 的 source family/exact-form
判断保持一致。generic filing 优先周期/当前经营报告；exact 10-K 仍只接受 10-K。
修改 `LLMInformationPlanProposer` 的提案说明及未来 seed 模板：跨公司风险需求用
generic filing，并写清研究用途，不默认所有美国上市公司都有 10-K/10-Q。
不改 V18 原 Plan，不用 40-F 假装满足 exact 10-K。

**规格：** `data/sources.md`、`data/resolution.md`、`research/evolution_plan_roles.md`。
**测试：** `test_data.py::SecEdgarClientTests`、`test_data_resolution.py::EvidenceResolverTests`：
recent 全未来但 history 有目标、无关分片不请求、accession 去重、分页失败/上限、
外国发行人 generic 匹配、exact 表单不偷换、未来文件拒绝。

## 批次 3：让模型看懂已存在的财务数据，并修有界软执行恢复

**`research/evolution_core.py::_agent_raw_document_view()` / `_query_relevant_excerpt()`**

首批只补项目已经支持的 SEC Company Facts 结构，不造通用 JSON 平台。
**新增私有 helper** `_company_facts_context(document, *, max_content_chars, query)`：
读取 `facts[taxonomy][concept].label/units[unit]`，按需求选最新及必要比较期，
以完整原文记录和 offset 绑定；同一期不同申报不能冒充两期。

```text
structured_context:
  concept、label、unit          ← 原始父字段，说明数值含义
  records[].exact_span         ← 完整原文记录，可作为引用
  records[].start/end          ← 原文 offset
  omitted_concept_count        ← 预算内未展示的覆盖信息
```

增加的是 prompt 视图，不修改 RawInfoDocument、确定性 Signal 的计算或原始内容。
原文 offset 必须可验证；匹配不唯一或未知结构时标 partial，不猜父指标。
总预算包括父字段与记录；至少让 V19 case001–003 不再只看到没有指标名的孤立数字。
已识别格式之外继续现有有界 excerpt，并保留 partial。

沿 `_agent_raw_document_view → _model_evidence_view → E1` 的实际调用链传递该字段，
保留原身份掩码。更新 E1 的可见 literal 验证：每条引用必须位于一个允许的
`exact_span` 内并匹配原文，不能跨记录拼接；包装字段不充当独立事实引用。

**`research/evolution_signal_roles.py::StructuredLLMSignalRunner`**

在 `_batch_payload()`、`_fit_projection_to_budget()`、`execute_many()` 的原流程修复：

- 每个 Signal 明确自己的 eligible projection refs；纠正仅带失败项的证据与错误。
- 文本窗口若截断高排名命中的完整句子/记录，沿原文有界扩展一次；每个失败项只
  重新执行一次、仍受原 correction 上限和硬预算约束。
- 必须先做新增请求预算估算；不能多加一套重试。无变化输入不反复执行，成功兄弟项保留。
- 若语义 unavailable 且明显缺比较期/窗口截断，消费者允许一次有界补查；仍无依据
  保留 unavailable。不要把任意已检索文档解释为测量所需信息已足够。

**规格：** `research/evolution_core.md`、`research/evolution_signal_roles.md`、
`data/resolution.md`、`signal_library.md`。
**测试：** 原 `test_queryless_json_excerpt_reaches_recent_dated_records` 增加指标/单位/期间
断言；增加相同数值不同指标、未来记录、比较期、预算遗漏、跨记录引用拒绝。
`SignalExecutionAndInitializeRoleTests` 验证遗漏 batch 项、跨 Signal 引用、窗口末端、
预算耗尽及成功兄弟项不重跑。按 V18 35 个 unavailable 审计表定向复验，不要求全部转成功。

## 批次 4：普通 Fast → Slow 反馈和完整 meta

**`data/resolution.py` 新增一个纯函数：**

```python
def extract_unresolved_signal_needs(sources):
    # sources 由 research 层完成准入检查，本函数不 import research
    # 读取每条 trajectory.final_state.next_information_needs
    # need_ref = hash(规范化文本)，精确去重并保留每个 original_need/source_ref
    # 终止原因保留 no-match/budget/round-limit，不统称缺新 Signal
    return stable_sorted_items
```

`aggregate_capability_gaps()` 保留这些 needs 的来源字段；同时读取
`signal_round.batch.results[].execution.status`，将技术故障加入独立诊断列表，
不纳入领域学习。backlog 升级一个版本，增加 `source_round/source_fingerprint`、
每项 `need_ref/sources`；对 H1 只输出 opaque refs 和脱敏文字，本地路径/身份不外发。

**`plan_evolution.py::EvolutionWorkspace.refresh_capability_backlog()`**

正式需求从 `restore_archive()` 沿完成指针和 checkpoint 取完整 PlanRecord，
不要从所有 attempts 取正式学习，也不要用有默认100条上限的记录摘要 API。
bootstrap 继续原有资格检查；诊断 attempts 可以单独提供无标签技术问题。
根据实际成功 resolution 更新数据缺口，不以 source 名称存在来宣告 resolved。

**调用点必须一起加：**

```text
PlanEvolutionEngine.run_round():
  commit_round()                   ← 现有完成指针，不改原子性
  archive/learning/meta 发布        ← 保留现有逻辑
  refresh_capability_backlog()      ← 新增提交后刷新

SignalEvolutionEngine.run_cycle():
  如果没有 staged_slow_validation：
    refresh_capability_backlog()    ← 中断恢复补齐；核对 source_round
    _validate_cycle()
  如果已有 staged validation：按原冻结结果恢复，不能改写其输入
```

**`evolution_core.py::PlanMetaMemory.model_view()`**

用当前序列化替换抽样实现：

```python
return tuple(entry.to_dict() for entry in self._entries)
```

同步 `LLMInformationPlanProposer.propose()` 与 `SignalEvolutionEngine._mining_context()`
的说明、测试及调用参数。保留 `_validate_additive_meta_payload()` 和掩码。
少量 audit 元数据记录全文 hash、round IDs、case 数；不新增记忆对象或分页系统。
用 `StructuredRoleClient.estimate_json_request_tokens()` 核对完整实际请求预算；
超预算沿现有 `ExternalBudgetExhausted` 控制流暂停，不能触发内容纠正或转无假设。
不得将完整后验 meta 给 E1、SignalExecutor、Predictor。

**规格：** `research/plan_evolution.md`、`research/evolution_core.md`、
`research/evolution_plan_roles.md`、`research/signal_evolution.md`、`data/resolution.md`。
**测试：** `PlanArchiveAndWorkspaceTests`、`PlanEvolutionEngineTests`、`DualLoopTests`、
`RoutingAndPlanRoleTests`：118 条需求全部可溯源；提交后/刷新前中断恢复；幂等；
原来不被选中的案例独有线索进入实际请求；预算阻塞不假完成；盲角色无标签泄漏。

## 批次 5：Mining 的空结果必须有依据，恢复必须看数据变化

**H1：** `evolution_signal_roles.py::_SIGNAL_MINING_HYPOTHESES_V2_OUTPUT`、
`LLMSignalMiningModel._propose_hypotheses_v2()` 升级为 v3 单一新生产契约。
在原 `conclusion/hypotheses/no_hypothesis` 之外只加 `need_dispositions`：

```json
{
  "need_refs": ["need-a", "need-b"],
  "disposition": "new_measurement",
  "signal_refs": [],
  "rationale": ["简短说明"]
}
```

允许 new_measurement/update_existing/repair_dependency/already_covered/not_testable。
所有输入 needs 都有去向，允许归并；引用 existing Signal 必须是真实 stable ref。
假设仍用原槽位与总数限制，纯供应商错误不强迫生成假设。能定义测量但数据缺失时
保留假设，H2/H3 数据准备结果记受阻。meta 新方向不强迫绑定不存在的 need_ref。
通过已有 `AgentStep.metadata` 保留逐假设 need_refs 映射和分流，写入 H1 stage audit。

**E2：** `discover_exploration()` / `_decisions()` 仅在 E2 分支增补：

```json
{
  "decisions": [],
  "no_candidate": {
    "reason_code": "insufficient_evidence",
    "rationale": ["简短依据"],
    "considered_case_refs": ["本次实际E2归纳组"]
  }
}
```

非空 decisions 时 no_candidate 为 null。空结果原因限定为无可测模式、证据不足、
已有 Signal 覆盖等小集合；considered refs 必须匹配真正输入，runtime 计算组别基数。
E2 只接收 runtime 选定的 `selected_grounded_signatures`；未入选项及独立 holdout
不传入，允许冻结 E1 池内按原规则合法选择归纳项。不改变 H3 原有 decision 接口。

**`signal_evolution.py`：** 把 `_search_input_fingerprint()` 已有的相关 PIT 文档选择
抽成小 helper，并在 `_run_hypothesis_mining()` 的 H1 指纹中复用；加入全文 meta hash、
backlog、投影/角色协议和现有 `_role_work_identity()`。不含 cycle_id/临时 proposal IDs。
H1 仅复用相同输入的实质 no-hypothesis；technical failure 不作语义穷尽。
数据/模型/协议恢复后允许受现有次数和费用约束的再执行，不立即无限重试。

**规格：** `research/evolution_signal_roles.md`、`research/signal_evolution.md`。
**测试：** `SignalRoleAdapterTests`、`SignalEvolutionTests`：遗漏 need/ref 纠正；
纯错误合法零假设；可定义测量但数据延迟；E2零候选原因及真实样本refs；
同源类型补齐电话会可重新触发 H1；无关公司文档不触发；相同实质空结果继续去重。

## 批次 6：Update 先修契约，再验证实际改动

**第一处：`signal_evolution.py::_candidate_arguments_schema()`**

把 `raw_retrieval.properties` 与现有 `signal_library.py::SignalRetrievalPolicy`
对齐，支持：source_types、query_terms、lookback_days、comparison_requirement、
required_source_groups、minimum_distinct_periods、minimum_period_span_days、
minimum_observations。约束与 `__post_init__()` 一致；新输出不再引入旧 query alias。
这处同时修 Mining 新 Signal 的检索契约，不只修 Update。

**第二处：`_run_one_signal_update()` / `validate_signal_update_candidate()`**

已有 payload 提供 stable_spec/stable_skill；在 candidate_contract 提供 runtime
生成的完整 vNext 模板，只变版本，其余保留。不让模型凭记忆重写所有可选字段。
在 `SignalUpdateDecision` 增加 `changed_paths` 作为意图声明，不做 JSON Patch API。

```python
# 目标：先保留基线，再解析默认值，顺序不可反
retrieval = copy(stable.to_dict()['raw_retrieval'])
retrieval.update(candidate['spec']['raw_retrieval'])
candidate['spec']['raw_retrieval'] = retrieval
# 显式不同值/清空值必须声明 changed_paths；遗漏不是删除
updated = parse_and_validate_using_existing_contract(candidate)
effective_diff = compare_execution_fields(stable, updated, stable_skill, new_skill)
# 忽略 version、tests。空diff应返回no_change，不staging
```

这两个 compare/copy 步骤是待实现的私有小函数，不引入 patch 库。
`LLMSignalUpdateModel._update_v2()` 和 `_stage_update_candidate()` 必须调用同一
共享验证逻辑；不得在 staging 才第一次发现问题。传入 registry 的 stable_skill。
未知 changed path、声明与实际差异不符、空差异都走现有有限 correction。
历史存档可读，新模型输出统一新契约，不运行两套更新引擎。

**第三处：诊断与取样。**

- `_run_one_signal_update()` 在按 value 分桶前只接受 SUCCESS/DOMAIN_UNAVAILABLE；
  技术失败进 audit，成本保留，不能进 unavailable 归纳/效果计数。
- repeated_explicit_misleading 不再只选 wrong：优先当前允许 Discovery 内有来源的
  问题案例，wrong 不足时可从 domain_unavailable 做适用性/检索诊断。不能将 Fast
  的 Evolution Validation 案例偷偷挪进 Discovery。issuer-disjoint holdout、下限不变。
- 使用已有 case_diagnostics.evidence_verdict/outcome_relation 分别计算事实支持与
  关联统计；不从 rationale 的“错三例”提取机器计数。不编写自然语言真假词表。
  fixture 关联来源诊断并验证实际行为。回放不变的 V18 候选时保留 V19 原测试，
  验证三通过、一拒绝；新候选按自己的明确测量定义验证，不能把有争议的旧期望
  当成所有新版本必须满足的黄金标准，也不能只为得到通过而修改答案。
- work fingerprint 改用 `self._role_work_identity(self.update_model)`，替换类名。
  `_prior_signal_update()` 的 defer/技术受阻保留恢复资格；实质 no_change 继续去重。

**规格：** `research/signal_evolution.md`、`research/evolution_signal_roles.md`。
**测试：** `SignalEvolutionTests`、`SignalRoleAdapterTests`：完整 retrieval schema；
v1 → 候选 → v2 roundtrip 不丢字段；显式修改生效；version/tests-only 不 staging；
shared validator 在 correction 与 staging 一致；技术失败不进归纳；0 wrong/11 unavailable
能够进入合格的诊断或给出真正样本不足原因；改模型后不被旧结果抑制。

## 最后的执行验收

每批定向测试通过才进入下一批。源码改完后运行完整 unittest 和 lint，命令见主方案。
新增精简集成测试覆盖受控候选从挖掘、fixtures、独立效果验证、晋升到下一 Fast
实际调用的完整链路；不放松任何原判据。另覆盖无候选、真实失败、未知坏响应、
提交后中断恢复，避免只测正向样例。

随后在新冻结工作区进行已授权的有界真实验证：先定向数据/Signal，再普通 Fast→Slow，
最后下一 Fast 的真实反馈消费。原 V18/V19 只读。真实无候选仍合法，但必须有依据；
仍受数据/预算阻塞的阶段不能声称验收完成。没有真实晋升则清楚说明晋升分支只由
受控测试验证，不承诺一定产出有效新 Signal 或提高 F1。

若后续实施受限，完成前面可独立验证的批次并如实交付 checkpoint，不用建设更大平台
作为继续工作的前提。自动分页、实时新闻监控、新供应商、复杂语义裁判均不在首批。

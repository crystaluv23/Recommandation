# Round16 最终报告：所有列表路径统一"按成员、按操作"权限 + V119 原始全量复放

基线 c0a5bc2 + 未提交的 round14/15 改动。无生产调用、无 commit/push（按本轮
brief）。全部既有工作/审计文件原样保留。

## A. 诊断（brief 反例 + 独立评审 + 源码复读确认）

生产反例：`ScriptedRoleCaller([{'rows':['invalid','keep1','keep2']},
{'rows':['keep1','keep2']}])`，parser 当且仅当 `invalid` 仍在时以
`paths=('rows[0]',), allowed_repairs=('replace',)` 拒绝。
`_complete_parsed_role(reflect 生产旗标)` 接受了该未授权删除。

根因是三处**并行且不一致**的成员检查，共享两个过宽假设：

1. `_scoped_correction_drift_paths` 的不同长度列表分支把 `allowed_indices`
   （整成员路径覆盖槽）全部排除在 protected 外 ⇒ 整成员路径被隐式当作"可删除"；
   基数上界 `len(old)+len(allowed_indices)+budget` 还隐式允许拆分/追加。反例
   在 RAW 层即通过（drift 为空 ⇒ 直接解析原始对象并接受）。
2. `_authorized_membership_edit`（投影快速路径）同样把 covered 槽当作任意
   成员操作，且完全不接收移除授权。
3. `_reconcile_authorized_member_list` 的 `removal_authority is None` 缺省把
   covered 全部当作可删除（生产路径总传 dict，但直连调用缺省过宽）。

## B. 修复（spec 先行；最小源改动）

spec（evolution_output_validation.md）先改：整成员路径 `root[i]` 仅授权"以
恰好一行替换该成员"；删除该成员另需该槽自己的显式移除授权；把一个成员拆成
多行属于追加、需显式有界 add 授权；compaction 的 `required_compaction_remove_paths`
即是显式逐成员移除授权；raw drift、投影快速路径与 reconciler 通过**同一个
共享成员检查**执行同一规则——无移除授权的整成员槽必须仍由恰好一行代表。

源改动（evolution_output_validation.py）：

- `_authorized_membership_edit` 重写为唯一共享检查并新增
  `removal_authority` 参数：covered 槽必须被恰好一行替换（`len(covered -
  removal_slots) <= unmatched`），删除需槽级移除授权，超出替换的行受
  `unmatched <= len(covered) + append_budget` 约束；仅有移除授权而无整成员
  路径的成员作为可选匹配（可保留/消失，内容不可变）；三方向皆无授权时拒绝。
  raw 候选与投影候选由此服从同一操作权限。
- `_scoped_correction_drift_paths` 的不同长度列表分支删除内联平行算法，改为
  调用该共享检查（`allowances.get(path)` 缺根即零删除）。
- `_reconcile_authorized_member_list`：`removal_authority` 缺省/为空 ⇒ 零
  删除（删除旧的 covered 默认）；`_project_scoped_correction` 对两个受检路径
  统一传 `(member_removal_allowances or {}).get(list_path, ())`。
- `_complete_parsed_role`：obligation 的 `required_compaction_remove_paths`
  计入显式移除授权，合法 compaction 驱逐（如 open_questions[3] 案）在新规则
  下照常通过。
- evolution_research_validation.py：`_raw_research_evaluation_boundary_issues`
  的 runtime-owned 输入 issue 转为类型化 ValidationIssue（消息文本逐字不变，
  `StructuredValidationError` 的渲染文本因此不变），携带
  `allowed_repairs=("remove",)`——该验证器明示"Remove this item"的删除现在有
  显式机器可读授权，而非依赖旧的 covered 隐式默认（否则正例
  `test_initialize_rejects_runtime_baseline_need_above_summary_target` 的合法
  纯删除会被新规则误拒）。

保留：显式删除/有界追加、compaction 与有界扩展、稳定 id 行修复、c01 未提及
成员恢复、occurrence-aware need 契约/回退、round13 参照守卫、round10 反馈
前进——899 全量测试无回归。

## C. 测试（tests/test_evolution_output_validation.py）

新增 `test_replace_only_member_path_never_deletes_or_splits`：原序纯删除
（反例本身）、拆分为两行、无授权追加三负例（均经生产 reflect 旗标断言
CandidateExecutionRejected + 反馈只含 replace 授权），加授权替换正例。
新增 `test_explicit_member_removal_and_bounded_add_stay_authorized`：整成员
remove 授权纯删除正例；`add` + missing_quantity_literals 的有界追加正例与
超预算负例。既有 mixed-drift 恢复反例（duplicate-content、短 run、无授权
消失、歧义插入等）全部保留未削弱。一个直连 `_project_scoped_correction`
正例（need[3] 移除）改为显式声明 `member_removal_allowances`，与新契约一致
（该处旧行为依赖"covered 隐式可删"，正是本轮废除的语义）。

## D. 原始 V119 全量复放（round-16/replay.py，生产代码重建，无模型调用）

- **c02（Wynn case2，reflect）**：从 request202 载荷重建 prior
  ResearchState、canonical SignalBatchResult（证据 exact_span 取存储的
  model_evidence_text；确定性行 revenue_growth_yoy 的 interpretation 取
  exact_claim_if_adopted——数值校验器对这类行正是查询该 interpretation）与
  selection intents，经生产 `LLMResearchController.reflect` + ScriptedRoleCaller
  喂入原始 output202/output203：
  - raw202 need transition 独立校验 0 错误（重复 targeted+untargeted 有效）；
  - 生产 parser 对 202 的失败恰好是真实 signal 数值缺陷：
    `claim_quantity_not_supported`，`supporting_evidence[8].claim`，缺
    "2025"（由重建 batch 的真实 `_validate_signal_claim_quantities` 产生，
    非工件字符串转述）；无 research_need_transition_invalid；
  - 203 修复该 claim 后 2 次 llm_calls 即通过完整 parser/scoped correction，
    最终 needs[2]=精确残余、needs[3]=未靶向重复 catalyst 逐字保留，其余行与
    beliefs 与 203 一致。工件记录的旧运行反馈含 transition 误报并打到 204
    仍被拒——本轮复放不再需要 204。
- **c01（Newmont case11，initialize177→178→179）**：工件只存
  feedback/output 线缆快照，不含原始请求，故 basic_info 由 177 自身的证据行
  重建（每个 projection_id+exact_text 被快照逐字佐证；真实运行也确实通过了
  这些引用的 grounding——其失败是 belief 数值问题），evaluation_context 取
  同运行的 prediction_time，skill 文案只进 prompt 不进校验。经生产
  `LLMResearchController.initialize`：3 次 llm_calls 返回安全状态——179 的
  整列表漂移被投影丢弃（`structured_correction_projection_retained` 事件，
  copied=beliefs[2]/[4]+evidence[3]，discarded=current_beliefs），最终 beliefs
  = 179 基线行 [0,1,3,5,7]：显式授权删除 {2,4} + 确定性 fallback 依据自身
  remove 授权移除的 linked 断言（基线行 6）；每行都是基线原字原序，无发明
  内容；supporting_evidence 仅移除 fallback 授权行；其余字段与基线逐字一致。
- **反例复放**：brief 的原始反例经 `_complete_parsed_role` 现为
  CandidateExecutionRejected。

## 实际命令与结果（exit code）

- focused：`PYTHONPATH=src …python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v` → exit 0，Ran 34 tests OK。
- full：`…python3 -m unittest discover -s tests -v` → exit 0，Ran 899 tests OK。
- lint：`sh scripts/lint_repo.sh` → exit 0，Lint result: PASS。
- replay：`…python3 .delegation/…/round-16/replay.py` → exit 0，ALL ROUND-16
  REPLAY CHECKS PASSED。
- `git status --short` / `git diff --check` → 无空白错误；改动仅限允许文件
  （两源码、两 spec、tests/test_evolution_output_validation.py、progress 两
  文件、round-16 目录）；round-14/15 与 v119 审计文件原样保留。

## 局限

- c01 重建：工件不含 initialize 原始请求，basic_info 由 177 证据行重构、
  skill/evaluation_context 为等价重建（skill 不参与校验；被引用 projection
  的 grounding 结论与真实运行一致）。未被引用的 basic_info 内容不可得，若
  其含有会导致不同 initialize 期诊断的内容，复放的中间反馈可能与旧运行不同
  （最终断言只针对成员操作权限，不依赖该差异）。
- c02 确定性信号行的底层 exact_span 不可得（模型视图按设计省略），以
  exact_claim_if_adopted 代替；对 202/203 引用该行的唯一 claim（逐字复制
  canonical interpretation）无影响，但不排除其他假设引用底层数字的情形。
- 模型视图证据文本来自有界压缩；数值 token 逐字保留，极端情况下被省略中段
  的数字在真实 canonical span 中存在而复放中缺失（对本工件两输出无影响）。
- round-10 高级反馈行为与 round-13 参照守卫未单独复放，由 899 全量测试覆盖。
- 消耗约 20 个模型轮次（advisory 预算边缘）。未运行生产、未 commit/push。

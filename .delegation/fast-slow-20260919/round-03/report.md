# Round 03 报告:修复普通 ResearchState 作用域纠错

- round_id: fast-slow-20260919/round-03
- status: completed(本地修复+回归全绿;live run 按本 brief 禁止,未执行)
- changed files(均为允许清单内;按 brief 未 commit/push):
  src/stock_opportunity_agent/research/evolution_output_validation.py、
  spec/src/stock_opportunity_agent/research/evolution_output_validation.md、
  tests/test_evolution_output_validation.py、progress/status.md、
  progress/changelog.md、本报告与三份日志。

## 根因与修复

1. 根因确认(round-02 诊断成立):`_complete_parsed_role` 在 `exact_compaction_scope=True`、失败无真实压缩义务且 issue 未声明 `write_scope_complete` 时仍进入 `_authorized_correction_paths`;该助手无压缩义务必返回 `[]`,空授权使 `_scoped_correction_drift_paths` 直接放行——未点名字段漂移(含回退仅存在于最新被拒输出中的修复,V117 c01 attempt 10→12)完全不受检,整段重写被原样全量复检,纠错预算耗尽后 `CandidateExecutionRejected`。
2. 实现(最小分层):该场景改走义务路径并集(must_change_paths + must_change_any_of_paths + permitted_dependency_paths)做漂移检测+投影,基线=最新无效输出;投影对象须整体复检通过才采纳,否则复检模型完整对象。加此回退的原因:首轮全量套件 9 个既有 H_init/H_reflect 真实流程测试(exit 1)证明合法联动编辑常超出 issue 点名路径,硬拒会误杀。真实压缩义务的 closed-scope 解析与 scope-failure、`write_scope_complete` 声明完备分支、普通(非 exact)控制器的严格行为均未改动。
3. spec 同步:补写"纠错基线=最新无效输出,后续纠错不得静默回退仅存在于该输出的修复;exact 压缩模式下未声明 write_scope_complete 的普通投影须整体复检通过,否则复检完整对象,合法普通修复不因未点名联动编辑被拒"。

## 回归测试(全部经真实 `_complete_parsed_role`,非 helper 孤立测试)

- `test_exact_compaction_scope_correction_cannot_undo_prior_need_repair`:两连纠错——第一轮修复 temporal need(含"2027")同时在授权路径引入新错,第二轮修复新错并回退已修 need;断言最终 needs 保留修复值且 parser 通过;断言审计事件 `structured_correction_projection_applied`(stage/request_stage/correction_count=2/copied_paths/discarded_paths);断言第二轮 feedback 的 invalid_output=第一轮被拒输出(基线语义)且 required_change_paths 不含 needs。旧代码该场景必 `CandidateExecutionRejected`,测试构成真回归。
- `test_exact_compaction_scope_keeps_permitted_dependency_edits`:permitted_dependency_paths 依赖编辑(修改/保持)两方向均放行。
- `test_exact_compaction_scope_keeps_indexed_compaction_removal` 与 `..._still_rejects_drift_beside_indexed_removal`:压缩授权的整项列表删除保留、伴随未点名漂移仍按 scope-failure 拒绝(压缩行为不变)。
- 既有 12 项(write_scope_complete 分支、launder、稳定 id 重排等)全部保留并通过。

## 测试与退出码(允许命令,日志均在本目录)

- focused:最终 exit 0,12/12 通过(focused.log;期间两次 exit 1——本人 fixture 误改 exact_text、以及首轮纯并集实现的 9 例联动编辑误拒——均已按上述分层修复)。
- full:exit 0,Ran 856 tests ... OK(full-tests.log)。
- lint:exit 0,Lint result: PASS(lint.log,已读)。
- `git diff --check` 干净;`git status --short` 仅本轮允许文件+既有 delegation 工件(state.md/skill-update.md/v117-evidence.json 非本轮所写,原样保留)。

## 继任 live run 入口(未新增调查,未运行)

- CLI(spec/src/stock_opportunity_agent/research/evolution_control.md:5-18):freeze-run 传 `--cycle-mode fast_then_slow --slow-history-from <manifest>`(可用 `--max-cycles` 缩减单次调用);具体脚本路径本轮未重新定位,V117 实际命令见 reports/fast-round-correction-regression-20260919.md。
- 冻结前置:src/scripts/configs 须全部已提交(evolution_transport.py:54-106 `current_code_revision` 逐项校验)——本轮改动未提交,继任轮须先 checkpoint。
- 预算授权:`EvolutionRunContract.max_external_attempts/max_total_cost` 进入 `ExternalAttemptLedger`(reserve/finalize,evolution_transport.py:195-311);`StructuredRoleClient(allow_external=True, acknowledged_contract_hash=contract.contract_hash)`;未授权时抛 `ExternalRequestPending(request_hash, workspace/requests/<hash>.json)`;API key 按 `registration.api_key_env_var` 检查。

## 剩余验收

- live run 与原始工件未验证:修复对 V117 型 H_reflect 纠错链的实际存活效果,需继任轮冻结运行确认;V117 工件未动。

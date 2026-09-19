# Round 02 报告:有界纠错回退诊断

- round_id: fast-slow-20260919/round-02
- status: completed(仅诊断,按 brief 不做实现)
- changed files: 仅本报告;`git status --short` 显示改动只有 .delegation 状态/轮次文件。

## 核心发现(精确引用)

1. **最新无效输出确实逐字在纠错请求里**:`_complete_parsed_role`(evolution_output_validation.py:2584)在第 2655-2659 行把 `validation_feedback.invalid_output = dict(failed_output)` 放入请求;`failed_output` 在 2835/2839 行取自最新被拒输出(`echo_invalid_output_on_correction` 默认 True)。缺口不在"缺输出",而在反馈只点名该输出中检出的缺陷。
2. **漂移守卫对非压缩类失效(根因)**:同函数 2748-2769 行:H_reflect 传 `exact_compaction_scope=True`(evolution_plan_roles.py:332-333);当失败无压缩义务(minimum_removed_items)且 issue 无 `write_scope_complete` 时,走 `_authorized_correction_paths`(:1985),而它在无压缩义务时必返回 `[]`(:1994-2001)→ `_scoped_correction_drift_paths`(:2089)在 allowed 为空时直接返回空(:2098-2100)→ 整段重写输出被原样接受 → 全量复检捕获回退字段但纠错预算(≤2)耗尽 → `CandidateExecutionRejected`(:2945)。完整复现 V117 c01 attempt 10→12:第 2 轮纠错只携带 3 个新缺陷,未点名的 `next_information_needs[0]` 回退为初始违规表述。
3. **规约-代码背离已存在**:spec/src/stock_opportunity_agent/research/evolution_output_validation.md:15-19 明言"absence of compaction must never disable ordinary sibling preservation";现码违背此句。修复方向因此无需新规约决策:无压缩义务时改走 else 分支(2760-2769 的义务路径并集),使漂移检测 + `_project_scoped_correction`(:2170)对未点名字段强制逐字保留(以最新无效输出为基线,链式保住 N-1 修复)。
4. **既有保护为何无效**:`_restore_inherited_need_cutoffs`(evolution_research_validation.py:905)只对照 reflect 的输入 `previous_state`,attempt 11 的修复仅存在于被拒中间输出,不可见;`_research_state_evidence_grounding_fallback`(:2306)遇 `future_information_unavailable` 返回 None,确定性兜底不救。
5. **H_reflect 输出→下一轮检索**:`LLMResearchController.reflect`(evolution_plan_roles.py:207-336)返回 AgentStep[ResearchState];其 `next_information_needs` 作为 `information_needs` 进入 `LLMSignalRetrievalAgent.select`(:468,含 `_signal_routing_research_context` :408 投影 research_context),并在下一次 reflect 经 `_reflection_need_transition_contract`(evolution_research_validation.py:1400)绑定 need 所有权。验收测试应断言:接受态 needs 即检索输入。

## 建议写入集(下一轮,spec-first)

- src/stock_opportunity_agent/research/evolution_output_validation.py:`_complete_parsed_role` 2748-2769,无压缩义务时用义务路径并集(删去该场景下对 `_authorized_correction_paths` 的强制);必要时在 spec 中补一句"未点名字段以最新无效输出为基线逐字保留"。
- 回归测试(tests 镜像 src):构造 N-1 输出(已修 needs[0]+3 点名缺陷)与 N 输出(needs[0] 回退),断言投影后保留修复值且通过 parser;另测必要依赖编辑(permitted_dependency_paths)仍放行。命令:`python -m pytest tests -k "scoped_correction or research_state_correction"`(本轮未运行任何测试)。

## 证据缺口与决策

- 未读 `_validate_research_state_refs` 全体(evolution_research_validation.py:1681+)与 transport 层 `_complete_json_with_invalid_value`;V117 工件未打开(不可变);审计提及的 H1/v56 先例未在本轮定位。
- 决策:推荐运行时投影修复(确定性、与现行 spec 一致),而非审计备选的"每轮重携约束清单"(依赖模型服从,弱保证)。

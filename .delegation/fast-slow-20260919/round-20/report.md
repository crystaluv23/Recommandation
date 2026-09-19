# Round20 report: bounded future schedule plural vocabulary false rejection

- round_id: round-20
- status: completed locally, awaiting Codex acceptance + orchestrator checkpoint (per brief, no commit/push by executor)
- baseline: 6ea4b57 (917 tests / lint accepted); HEAD unchanged; no subagents, no paid calls, no frozen-run edits

## Changes

1. `src/stock_opportunity_agent/research/evolution_research_validation.py`
   `_FUTURE_EXPECTATION_OR_SCHEDULE` 只把已有可数名词增加显式复数形（`dates?|schedules?|timelines?|milestones?|forecasts?|targets?|goals?|releases?|reports?|openings?|construction\s+plans?`），词边界保持 `\b`，无词干化/子串匹配，词汇表未新增词条。允许分支的其余条件不变：仍需 `_has_prediction_bounded_as_of_clause`（显式 as-of 截止 ≤ prediction），且 `_FUTURE_REALIZED_RESULT`（results/actuals/realized/how much/how many）仍否决。未改 `_EXPECTATION_TRANSMISSION`、未做整体 temporal guard 重设计、未动 retry/scoring/PIT/promotion/schema。
2. `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`
   Spec-first：新增 invariant——as-of 有界披露的未来 schedule/expectation 允许项对语法单复数不敏感（逐词显式复数、全词边界、无 stemming），其余边界（显式 as-of ≤ prediction、realized results/actuals 拒绝）不变。
3. `tests/test_evolution_output_validation.py`
   新增 `TemporalSchedulePluralVocabularyTests`（5 个用例）：V122 case12 原句（复数 milestones 通过、单数对照通过）；14 个单/复数变体共享允许项；复数 results/actuals 仍拒绝；无 as-of 界与晚于 cutoff 的 as-of 界仍拒绝（返回 `["2025-06-30","2025-09-30"]`）；混合 past-as-of/future-forecast 正/负对。
4. `.delegation/fast-slow-20260919/round-20/replay.py` + `replay.log`：下述验证。

## Actual commands (verbatim allowlist)

- `PYTHONPATH=src ...python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v > .delegation/fast-slow-20260919/round-20/focused.log 2>&1`
- `PYTHONPATH=src ...python3 -m unittest discover -s tests -v > .delegation/fast-slow-20260919/round-20/full-tests.log 2>&1`
- `sh scripts/lint_repo.sh > .delegation/fast-slow-20260919/round-20/lint.log 2>&1`
- `PYTHONPATH=src ...python3 .delegation/fast-slow-20260919/round-20/replay.py > .delegation/fast-slow-20260919/round-20/replay.log 2>&1`
- `git status --short`、`git diff --check`

## Results

- focused：57 tests OK（52 既有 + 5 新增）。full：**922 tests OK**（917 既有全保留 + 5 新增）。lint：PASS。`git diff --check` 干净；改动仅 spec/src/tests 三文件（另 state.md 为 launcher 所改）。
- 独立 guard 探针（replay.log）：确认的假阳性原句（复数 milestones，by 2025-03-31 / through 2025-09-30）现返回 `[]`；单数对照仍 `[]`；复数 results、actuals 仍拒绝；无 as-of 界仍拒绝；as-of 晚于 prediction 仍拒绝；混合正/负对符合预期。未引入无界未来接受。
- 冻结输入保真：208/209 hash 与 attempts.json 账本一致；`requests/<hash>.json` 与 `cache/responses/<hash>.json` 均在；wire payload 的 basic_info 9 个唯一 projection_id 全部链接进冻结请求、evaluation_context 三值与 initial_research_skill 全文嵌入冻结请求（长投影在模型视图中按既有 compaction 呈现，5/12 行 verbatim——wire basic_info 才是校验用的 canonical 输入）。
- 208/209 生产 initialize 全流程重放（ScriptedRoleCaller[raw208, raw209]，ORIGINIAL basic_info/evaluation/skill）：raw208 归一化不再有 `future_information_unavailable`（0 temporal issues），诚实保留数值缺陷 `claim_quantity_not_supported`×4 + `assertion_without_support`×1 进入首轮聚合反馈；raw209 归一化无 issue 但完整校验/漂移仍触发既有 owner-authorized fallback；最终状态：decision=continue，6 条 needs 与 raw208 需求列表逐字节一致（含复数 milestones 原句），4 条 beliefs，4 条 basic_info 证据（非空证据接受），llm_calls=2。无 forced acceptance、无空证据接受。
- 207 属前一 case 的 posthoc reflect，仅登记未重放。

## Limitations

- 重放为离线 wire 重放（与 round16-19 同法）：persisted response 输出直接作为 caller 脚本，不重发付费请求；208/209 的真实生产接受仍需下一个冻结 live 后继验证。
- raw209 的 evidence 8→7 重排在重放中经既有 scoped-correction/fallback 语义处理；最终 4 行证据来自 fallback 的窄化（现有授权路径），未逐行审计其与 live 行为的一致性（沿用已接受的 round17-19 fallback 契约）。
- 按本轮 brief 未 commit/push、未改 progress/status.md 与 changelog（沿用 round03-19 惯例，由 orchestrator 验收后统一 checkpoint）；AGENTS.md 的 session-end checkpoint 由验收方执行。
- 复数化仅覆盖既有词汇表内可数名词；未触及 `_EXPECTATION_TRANSMISSION`（无确认假阳性，避免范围扩张）。

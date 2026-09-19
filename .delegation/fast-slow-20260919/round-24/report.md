# Round 24 最终报告：等价有界预测语言误拒修复（V124 c01）

日期 2026-09-20。仅 round-24 范围；未用子代理/付费调用，未 commit/push，未改任何 frozen run。

## 结论
两处确认的时间词法误拒已修复并通过全部实际检查：943 测试（936 存量 + 7 新增）全过、lint PASS、V124 c01 原始 wire 全量 initialize 重放 0 失败。守卫语义未放宽：晚于预测时间的截止不授界、after/since 开放窗照拒、realized results/actuals 压过 projected 措辞、无界 projection 照拒。

## 代码修改（spec 先行）
- `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`：同步两条不变量（as-of 界接受等价更严格的 before/prior-to 拼写；期望词表含 projected/projections/anticipated，且 projected 措辞绝不把已实现未来结果变为可采信证据；可继承名词表加 projections）。
- `src/stock_opportunity_agent/research/evolution_research_validation.py`（最小词法改动，4 处）：
  1. `_EXPLICIT_AS_OF_BOUND` 与 `_SYMBOLIC_AS_OF_BOUND` 介词集 `by|as of|through` → 追加 `before|prior to`（符号形态如 "before/prior to the prediction time"；显式形态仍经 `_has_prediction_bounded_as_of_clause` 要求日期 ≤ prediction）。
  2. `_FUTURE_EXPECTATION_OR_SCHEDULE` 追加 `anticipated|projected|projections?`。
  3. `_INHERITABLE_EXPECTATION_CONTEXT` 同步追加名词 `projections?`（与期望词表一致）。
- `tests/test_evolution_output_validation.py`：新增 `PriorBoundAndProjectedExpectationTests` 7 条正/反测试（raw3 need1 原文及 prior-to 变体、符号/显式 before 正例、raw5 need3 原文及 expected/anticipated/projections 变体、截止晚于预测拒、after 开放窗拒、projected realized/actuals 拒、无界 projection 拒、before 界父句残差继承 clause+guidance 框架）。
- `.delegation/fast-slow-20260919/round-24/replay.py`：仿 round-20，载入 v124/c01-case1-rejection.json 的 attempt 3（initialize）/4/5（corrections）与冻结 basic_info/initial_research_skill/evaluation_context，经 `_complete_parsed_role`（research_controller_initialize + scoped correction + grounding fallback）复放。

## 实际执行的命令与结果（均用允许清单原命令）
1. focused：`PYTHONPATH=src .../python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v` → exit 0，Ran 71 tests, OK（含 7 条新测试）。
2. full：`... -m unittest discover -s tests -v` → exit 0，Ran 943 tests in 21.239s, OK（936 存量全保留）。
3. lint：`sh scripts/lint_repo.sh` → exit 0，Lint result: PASS（7 项全 PASS）。
4. replay：`... python3 .delegation/fast-slow-20260919/round-24/replay.py` → 最终 exit 0，0 failures（21 项检查全 PASS：冻结输入保真 15 项含 attempts 3/4/5 哈希对账 attempts.json；独立守卫探针 9 项）。首次运行 exit 1 的唯一 FAIL 是 replay 脚本自身把 need1/need3 误设为索引 0/2（wire 实为 1/3），改为按内容定位后复跑全过；两次运行中守卫行为均正确。
5. `git status --short` / `git diff --check` → 本任务改动仅 spec/src/tests 三文件与 round-24/ 产物；无空白错误。未提交（按 brief，commit 属 Codex 评审后）。

## 重放关键结果（prediction_time=2025-09-30）
- raw3（6 needs）：时间问题仅剩 `next_information_needs[3]`（真无界 projection，仍拒，refs=['2027']）；need[1]（"forward guidance ... 2025 and 2026 ... available before the prediction time"）误拒消失（refs=[]）。
- raw3 normalize codes：future_information_unavailable×1 + claim_quantity_not_supported×3 —— 数值类 issue 独立且仍被强制执行。
- raw4 仍含 1 个时间 + 1 个数量问题；其对 need[1] 删 2026 的新改写因该路径未被标记而被 scoped projection 作为漂移丢弃。
- raw5 单独即合规（codes 空）；控制器第 3 次调用接受。最终态：decision=CONTINUE，6 needs / 8 current_beliefs / 8 supporting_evidence（全 basic_info，投影 id 与冻结请求一致），llm_calls=3。
- need[1] 含合法 2026 范围逐字保留；除被标记的 need[3] 外全部兄弟 need 逐字保留（missing=[]）；raw5 的有界 projected reserve 需求（"as of the prediction time ... projected ... 2025 and 2027"）进入最终态。

## 负例确认（探针+单测）
before/prior-to 截止晚于预测（before December 31, 2025 / prior to March 2026）拒；after March 2026 开放窗拒；projected 2027 results / projected actuals 拒；无界 projection 拒。

## 局限
- 仅本地静态验证与冻结 wire 重放；无生产模型调用。V124 c02（已达 reflection、无完整 joint cycle）与 Fast+Slow 真实联合完成仍待 Codex 独立评审后的生产重跑。
- replay 的冻结请求校验中长 exact_text 以紧凑模型视图呈现（verbatim 1/16），按 round-20 同一口径以 projection_id 链接校验。
- 本轮按 brief 不 commit；progress/status.md 与 changelog.md 已更新。

# Fast 轮纠错回退缺陷审计(V117,2026-09-19)

## 运行背景

- V117(`information-evolution-dual-self-evolution-20260919-v117`,合约
  `9f2eeebc…`)是首个在 v8 运行时下 live 执行的 `fast_then_slow` 双循环:
  经 d002c2b 支持后,`--cycle-mode fast_then_slow --slow-history-from V115`
  冻结,初始 Registry v6(V115 链末端,含已晋升叙事因子),1 轮 × 2 候选,
  3000 次尝试 / $20 / 6 周期上限。
- 前置特性本身工作正常:双循环模式、v6 注册表继承、案件级研究流
  (init → reflect → routing → signal batch)全部按设计执行。
- 终态:262 次尝试 / $0.790,round-0001 被拒(`no_fitness_eligible_candidates`),
  cycle/round 指针 0/0,工作区保留为不可变诊断证据。c01 完成 0/24 案,
  c02 完成 12/24 案(TP=4、预测正类 10、证据覆盖 12)后双双死亡。

## 缺陷证据链(c01 案 1 `cik_0000701818:20250930`,H_reflect)

1. **初始反思(attempt 10)**:`next_information_needs[0]` = "Cost per ounce
   guidance for the remainder of 2025 and 2026 is not covered by this card."
   无 as-of 限定,含未来年份 → `future_information_unavailable`。
2. **纠错 1(attempt 11,反馈=时间边界错误)**:模型改写为
   "What cost per ounce guidance had Kinross Gold disclosed by 2025-09-30 for
   the remainder of 2025?" —— 用 `_future_source_date_refs` 实测**通过**
   (as-of 子句 ✓、expectation 词 ✓、无 realized 词 ✓)。但同一输出引入
   2 × `claim_quantity_not_supported` + 1 × `research_need_transition_invalid`。
3. **纠错 2(attempt 12,反馈=仅上述 3 个新缺陷,不含时间边界问题)**:
   模型修复 3 个点名问题的同时,把 `next_information_needs[0]` 整段重写
   **回退**为第 1 步的原始违规表述(逐字一致)→ 全量复检再次触发时间
   边界 → 纠错耗尽 → `CandidateExecutionRejected`。

c02 案 13(`cik_0002023554:20250930`)同一模式死亡(`needs[1]` 的
"Q4 2025 and Q1 2026 guidance" 类表述)。两个独立候选撞同一堵墙。

## 根因

H_reflect 的 ResearchState 纠错传输**没有"未点名合规字段逐字保留"保护**:
第 N 轮纠错反馈只携带第 N-1 轮输出中检出的缺陷,模型整段重写状态时可以
静默撤销此前已修复的约束;全量复检随后 fail-closed。H1 已有同型规则
(item-local correction,v56 教训),H_reflect 缺失。判别模型温度为 0,
回退形态在同类案件上可复现,resume 只会重复消耗预算。

## 建议修复(下一会话,需按 spec-first 走)

- 纠错契约要求:未被 `must_change_paths` 点名的 `next_information_needs`
  条目(及 claim/belief 等可逐字比对字段)必须逐字保留;运行时在接受
  纠错输出前校验该不变量,违反即视为该次纠错失败并携带精确差异反馈。
- 或等价地:每轮纠错反馈重新携带此前轮次已满足的全部时间边界约束清单
  (约束而非缺陷),使模型重写时有持续在场的边界。

## 关联工件

- 失败轨迹:`…/v117/experiments/trajectories/plan_r0001_c01/cik_0000701818:20250930.failure.json`
- 三次请求/响应:`…/v117/requests/{attempt 10,11,12 request_hash}.json` +
  `…/v117/cache/responses/…`
- 轮次拒绝:`…/v117/experiments/round-0001/rejected.json`
- 运行日志:`reports/cold_start/v117-run.log`

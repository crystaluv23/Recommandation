# Fast／Slow Magnitude 进化 — P0–P4／P6（部分）实施记录

日期：2026-09-20。对应行动计划：[`fast-slow-magnitude-evolution-action-plan-20260920.md`](fast-slow-magnitude-evolution-action-plan-20260920.md)（含同日评审修订）。
本记录只陈述已完成并验证的事实；未完成项在 §5 明确列出。全程未发起任何模型／数据调用，未触碰 V130 workspace（只读）。

## 1. 阶段完成情况

| 阶段 | 状态 | 提交 |
| --- | --- | --- |
| 行动计划评审修订（4 项约束落档） | 完成 | `bfb98fc` |
| P0 基线审计（重算＋三方对齐＋回归矩阵＋冻结命令） | 完成 | `fc1a385`，见 [`fast-slow-magnitude-baseline-audit-20260920.md`](fast-slow-magnitude-baseline-audit-20260920.md) |
| P1 规格自上而下更新（5 个 spec 文件） | 完成 | `6b99892` |
| P2 确定性 magnitude 反馈与诊断 | 完成 | `9350848` |
| P3 反思四层接入（post-hoc／critic／round／proposer） | 完成 | `b9a9def` |
| P4 双目标选择排序 | 完成 | `ad9f572` |
| P5 Slow 接入（第一阶段） | 完成（2026-09-20 追加）：`magnitude_feedback` 反馈单元进入既有 `_committed_slow_feedback` source view（`magnitude:<plan_id>` 稳定引用、全角色可见、诊断性标注、legacy 无诊断则零行、导入负轮号排除）；`fast_plan_action` 档位路由沿用既有代码；`SlowLoopResult` 新增 `magnitude_contribution`（第一版恒为 assessed:false 并给出原因） | 见本轮提交 |
| P6 恢复与回归 | **完成（离线矩阵）**：真实引擎 12 场景故障注入矩阵全绿（见 §4a）；全量 1006 测试＋lint；V130 离线重放与 legacy meta 零行验证 | `tests/test_p6_fault_injection_matrix.py` |
| P7 实机试验 | **未实施**（需单独授权模型、数据与预算） | — |

## 2. P4 选择入口盘点（应用／保留及原因）

统一比较规则：eligibility → 有理数 Binary F1（`binary_f1_fraction`，混淆计数直比，杜绝 0.7999999999999999 式假差异）→ magnitude macro-F1 → 稳定 plan_id。

| 入口 | 位置 | 决定 | 原因 |
| --- | --- | --- | --- |
| 父代选择（archive Top-K） | `evolution_core.py` `PlanArchive.select_parents` | **应用新规则** | 主选择入口 |
| 历史 seed 主排序 | `evolution_control.py` `_seed_candidate_quality_key` | **应用新规则** | seed 的 cohort metrics 恒含 magnitude（PlanMetrics 非可选），无 legacy 缺失分支；已冻结 seed pool 序列化不变，新 pool 构建时生效 |
| 历史 seed 第二席（边际覆盖排序） | `evolution_control.py` second-seed tuple | **应用新规则**（F1 与 magnitude 插入 coverage／similarity 之后） | 覆盖优先目标保留，同分时规则一致 |
| dashboard 轮内 Top-K 与 archive_best | `evolution_dashboard.py` `_dashboard_selection_key` | **应用新规则**；legacy 无 magnitude 的序列化记录**不填零**，同 F1 时排在携带该指标的记录之后 | 展示与引擎排序一致 |
| round_committed 审计事件 | `plan_evolution.py` candidate_scores／top_k | **增加 magnitude_macro_f1 字段** | 每次选择的决定因素可审计 |
| 历史 seed 质量下限 | `HISTORICAL_PLAN_SEED_QUALITY_RATIO` 两处 gate | **保留现行语义** | Binary F1 质量下限是 F1 保护，非排序 |
| benefit 双臂判定 | `evolution_benefit.py` | **保留现行语义**（Binary F1 门） | 行动计划 §4：效果判据为"幅度改善且 F1 不下降"，F1 门即保护；magnitude 差值进入 P7 效果报告而非 gate |
| Signal 晋升门槛 | `signal_evolution.py` | **保留现行语义** | P5 第一版不放松晋升；纯幅度通道为后续独立决策包 |

## 3. P2／P3 落地要点（与评审修订一致）

- **`candidate_judgment_feedback` 未被原地扩展**：新字段全部位于旁路派生块 `magnitude_feedback`（逐案六字段，含 `error_kind` 五态与 `ordinal_distance`，FN 不虚构档位）与 `magnitude_diagnostics`（错分矩阵、分档 support、低估／高估、条件准确率及分母、TP=0 显式 undefined）。旧工件三处严格校验路径字节兼容（旧 meta／record 重载已实测）。
- **`prediction_outcome.correct` 语义不变**：post-hoc 提示词明确"复制混合确定性值"，`binary_correct`／`magnitude_feedback` 为并列诊断，先分方向错／档位错再归因。
- meta 持久化：`CaseReflectionEvidence.magnitude_feedback`（可选，legacy 缺省 None）、`PlanMetaReflection.magnitude_diagnostics`（可选，from_dict 容忍缺失）；`from_record` 自动派生，走同一条 additive FIFO。
- 父子比较：同一快照时新增 `magnitude_metric_delta`（accuracy＋macro-F1）；跨快照为 null。逐案转移汇总未实现（ParentPlanReflectionEvidence 为匿名聚合，扩宽契代价高，critic 已获子代逐案块＋父代聚合的等效证据）——记为有意缩小范围。
- proposer 侧未新增输出 schema（adopted/deferred/rejected 以提示词要求落在四字段实际改动中），避免触碰 correction 死端区——记为有意缩小范围，结构化 disposition 旁路留待需要时单独实现。

## 4. 验证证据

- 新增测试 50 个（`tests/test_magnitude_feedback.py` 23＋`tests/test_magnitude_reflection_wiring.py` 4＋`tests/test_magnitude_slow_wiring.py` 9＋`tests/test_p6_fault_injection_matrix.py` 14），覆盖五类 error_kind、边界倍数（2x／3x／10x）、V130 形状矩阵复现、TP=0 undefined、legacy 双层兼容、篡改拒绝、同分／反超／浮点噪声／稳定 ID 排序、slow source view 投影（legacy 零行、未提交轮与导入负轮排除、`validate_slow_input` 接受新 kind、引擎接线、`magnitude_contribution` 默认与往返）。
- 全量套件：`PYTHONPATH=src:tests uv run --no-project --with pytest -m pytest tests/ -q` → **1006 passed, 205 subtests**（P5 后 992＋P6 矩阵 14）。
- 仓库 lint：`scripts/lint_repo.sh` → **PASS**。
- V130 离线重放（新代码、只读）：legacy `meta/round-0001.json` 加载成功且新字段为 None；由 `record.json` 重建 24 轨迹后 `score_predictions` 与存储指标逐位一致（F1／magnitude acc／macro／confusion）；`magnitude_diagnostics` 得 under=7／over=0／missed=2、supports {2-3x:7, 3-10x:5, 10x+:2}、条件准确率 5/12；逐案 error_kind 分布 {not_applicable:10, correct:5, missed_surge:2, underestimate:7} 与 P0 审计矩阵一致。旧二分类数值与 eligibility 未变。P5 后追加：V130 legacy meta 在 `magnitude_feedback_rows` 下产出 0 行（legacy 无诊断不替代、不崩溃）。

## 4a. P6 故障注入矩阵结果（`tests/test_p6_fault_injection_matrix.py`，14 测试全绿）

真实 `PlanEvolutionEngine`／`SignalEvolutionEngine`／Predictor 适配器 + 脚本化 LLM 角色；崩溃经一次性 monkeypatch 注入，随后按生产恢复序列（重建引擎→引擎构造重放已提交 stats→控制层 `stage_slow_result`＋`complete_cycle`）验证。未使用 V130 工件本体（矩阵用临时 workspace 同构复现其状态；V130 只读约束保持）。

| # | 场景 | 注入方式 | 验证结果 |
| --- | --- | --- | --- |
| 1 | 逐案标签揭示 | 真实 `LLMBlindPredictor` 两段调用 | blind 请求 payload 无 truth／无 `magnitude_feedback`／无 `realized_max_multiple`；post-hoc 才出现 `magnitude_feedback`（FN 案例判 `missed_surge`） |
| 2 | 单有效候选 | 1 候选轮 + 真实 `LLMRoundReflector`（ScriptedRoleCaller 空脚本） | Round LLM 零调用；meta 仍持久化 plan 级 diagnostics 与逐案 magnitude 块；第 2 轮 proposer 的 meta_info 携带它们 |
| 3 | 不同快照 | 第 2 轮换池（内容变化→新 snapshot id） | critic 收到的父子比较全部 `same_evaluation_snapshot=false`，`metric_delta` 与 `magnitude_metric_delta` 均为 null（无非法配对差值、不重评历史） |
| 4 | 导入历史+本地三轮 | `_rebased_history_meta_entries` 负前缀 + 三轮提交重启 | proposer 视图轮号 -1→(-1,1,2)→本地 [1,2,3]，无碰撞；每轮 meta 均含 magnitude diagnostics |
| 5 | round commit 后崩溃 | `_record_signal_statistics` 提交后一次性 raise | 指针=1 保持；引擎两次重建 stats/learning 完全幂等（事件数不变、event_id 无重复）；第 2 轮正常提交，[1,2] meta 完整 |
| 6 | Slow staged validation 中崩溃 | `stage_slow_validation` 一次性 raise | 无晋升（registry 版本不变）、cycle 指针 0；恢复后单次完成，slow_input 恰含 1 条 `magnitude:plan_mag_r1` 行，报告 `assessed:false` |
| 7 | 晋升后、cycle commit 前 | run_cycle 完成转换后停在该中断态（引擎不推 cycle 指针的真实边界） | registry 已 v2、指针仍 0、staged validation 存在；提交前重跑幂等（无二次晋升、spec 版本稳定）；控制层 `stage_slow_result`+`complete_cycle` 后指针=1，版本不再跳 |
| 8 | malformed reflection/proposal | 空 post-hoc 反思 + 篡改 magnitude 块 | 一次有界修正通过（两次 payload 均含 `magnitude_feedback`）；篡改 `ordinal_distance` 被 `CaseReflectionEvidence` fail-closed 拒绝 |
| 9 | magnitude 缺字段/旧版本 | legacy 序列化记录（无 `magnitude_macro_f1`） | 同有理数 F1 时携带指标者排前，缺失者不填零、不算改善；全负样本 F1 分数=0（与 `score_predictions` 一致） |
| 10 | 失败传播不伪装 | post-hoc 调用抛 `CandidateExecutionRejected`（传输不可用） | fallback 保留框架确定性 `correct` 值（FN+档位错→False），`plan_issues` 明示 `posthoc_reflection_validation_failed`，未伪装成内容反思 |
| 11 | 空 Mining no-op cycle | `EmptyMiningModel` 完整 slow cycle | promoted=()、cycle 指针推进到 1、`magnitude_contribution.assessed=false`；round-1 meta（含 diagnostics）完整保留供下一轮学习 |
| 12 | 有效晋升下一 Fast 可见 | 引擎 fast round1 → 晋升 slow cycle → fast round2 | round2 evaluator 实际收到的 registry refs 含 `discovery_growth_quality`；round1 `record.json` 字节不变（旧预测与 metrics 不重写） |

矩阵外的补充说明：场景 5 的"引擎构造重放 stats"即 V126 崩溃点的生产恢复机制；场景 7/11/12 的 `stage_slow_result`＋`complete_cycle` 序列与 `evolution_control` 双循环层逐行一致。仍属 P7 范畴、未在本矩阵覆盖：真实付费模型的流程 smoke 与效果配对实验。

## 5. 未完成与后续

1. **P5 第二阶段**：受控 Plan 消费观察实验（同 Plan、同快照、仅改变候选 Signal 可用性的双臂盲预测）未实施；`magnitude_contribution` 目前恒为未评估，待该实验产出证据。
2. **P7**：全部实机试验待单独授权（模型、数据范围、attempts／费用预算）；V130 仍暂停于 slow_loop，恢复须 checkout 匹配 revision（`af5966b`），本日 HEAD 已前移。
3. 两个未修复缺陷仍然开放：第三类缓存重放死端、SIGINT 吞信号（见 P0 审计 §4 #11/#12）；本轮改动刻意避开了 correction 反馈结构本体。
4. 第一版同分优先的实际强度（真实历史候选中会改变多少次选择）待有 ≥2 个已提交候选的 workspace 后统计——V130 仅 1 个已提交 Plan，无从统计。
5. P6 矩阵为离线脚本化角色验证；真实付费模型下的流程 smoke 属 P7。

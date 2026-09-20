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
| P6 恢复与回归 | **部分完成**（全量单测＋lint＋V130 离线重放＋V130 legacy meta 零行验证；多轮故障注入与真实引擎跨轮验证未做） | — |
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

- 新增测试 36 个（`tests/test_magnitude_feedback.py` 23＋`tests/test_magnitude_reflection_wiring.py` 4＋`tests/test_magnitude_slow_wiring.py` 9），覆盖五类 error_kind、边界倍数（2x／3x／10x）、V130 形状矩阵复现、TP=0 undefined、legacy 双层兼容、篡改拒绝、同分／反超／浮点噪声／稳定 ID 排序、slow source view 投影（legacy 零行、未提交轮与导入负轮排除、`validate_slow_input` 接受新 kind、引擎接线、`magnitude_contribution` 默认与往返）。
- 全量套件：`PYTHONPATH=src:tests uv run --no-project --with pytest -m pytest tests/ -q` → **992 passed, 205 subtests**（P4 后 983＋P5 新增 9）。
- 仓库 lint：`scripts/lint_repo.sh` → **PASS**。
- V130 离线重放（新代码、只读）：legacy `meta/round-0001.json` 加载成功且新字段为 None；由 `record.json` 重建 24 轨迹后 `score_predictions` 与存储指标逐位一致（F1／magnitude acc／macro／confusion）；`magnitude_diagnostics` 得 under=7／over=0／missed=2、supports {2-3x:7, 3-10x:5, 10x+:2}、条件准确率 5/12；逐案 error_kind 分布 {not_applicable:10, correct:5, missed_surge:2, underestimate:7} 与 P0 审计矩阵一致。旧二分类数值与 eligibility 未变。P5 后追加：V130 legacy meta 在 `magnitude_feedback_rows` 下产出 0 行（legacy 无诊断不替代、不崩溃）。

## 5. 未完成与后续

1. **P5 第二阶段**：受控 Plan 消费观察实验（同 Plan、同快照、仅改变候选 Signal 可用性的双臂盲预测）未实施；`magnitude_contribution` 目前恒为未评估，待该实验产出证据。
2. **P6 剩余**：真实引擎多轮故障注入矩阵（行动计划 §P6 表格的 12 个场景中，已覆盖确定性单测、角色序列化、V130 重放、V130 legacy meta 零行验证；崩溃恢复、导入历史三轮、Slow staged 崩溃等未跑）。
3. **P7**：全部实机试验待单独授权（模型、数据范围、attempts／费用预算）；V130 仍暂停于 slow_loop，恢复须 checkout 匹配 revision（`af5966b`），本日 HEAD 已前移。
4. 两个未修复缺陷仍然开放：第三类缓存重放死端、SIGINT 吞信号（见 P0 审计 §4 #11/#12）；本轮改动刻意避开了 correction 反馈结构本体。
5. 第一版同分优先的实际强度（真实历史候选中会改变多少次选择）待有 ≥2 个已提交候选的 workspace 后统计——V130 仅 1 个已提交 Plan，无从统计。

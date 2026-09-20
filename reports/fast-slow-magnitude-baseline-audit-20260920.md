# Fast／Slow Magnitude 进化 — P0 基线审计

日期：2026-09-20。对应行动计划：[`fast-slow-magnitude-evolution-action-plan-20260920.md`](fast-slow-magnitude-evolution-action-plan-20260920.md)。
机器可读版本（含全部工件哈希）：[`fast-slow-magnitude-baseline-audit-20260920.json`](fast-slow-magnitude-baseline-audit-20260920.json)。

**性质：只读审计。** 本审计未改写 V130 workspace 的任何文件；全部数值由独立代码从 `record.json` 的原始轨迹重算，再与三处已存证据对齐。基线代码 revision `af5966b`（V130 冻结点），审计时 HEAD 已含两个文档 commit（`735edff`、`bfb98fc`），均不触及运行代码。

## 1. 重算结果与三方对齐

V130 已提交 Plan `plan_r0001_c01`（24 案）：

| 指标 | 重算值 | 与 record.json 一致 | 与 meta/round-0001.json 一致 | 与实际 critic wire 一致 |
| --- | --- | --- | --- | --- |
| Binary F1 | 0.800000（浮点存储为 0.7999999999999999） | 是 | 是 | 是 |
| Precision / Recall | 0.750000 / 0.857143 | 是 | — | — |
| Confusion | TP=12 FP=4 TN=6 FN=2 | 是 | — | — |
| Magnitude accuracy | 5/14 = 0.357143 | 是 | 是 | — |
| Magnitude macro-F1 | 0.175439 | 是 | 是 | 是 |
| 条件幅度准确率（TP=12 为分母） | 5/12 = 0.416667 | 派生一致 | — | — |

实际 plan critic wire payload（请求 `6c58…ba50`）确认：metrics 内含 `magnitude_accuracy`/`magnitude_macro_f1`，24 条压缩轨迹各含预测与真实档位；`candidate_judgment_feedback` 为纯二元六字段（`assessment`、`binary_correct`、`candidate_judgment`、`predicted_binary_label`、`reflection_guidance`、`true_binary_label`）——行动计划 §2.1 的"指标可见、结构化反馈缺失"诊断在 wire 层面成立。

## 2. 幅度错分矩阵（独立重算）

| 真实 \ 预测 | 负向（无档位） | 2–3x | 3–10x | 10x+ |
| --- | --- | --- | --- | --- |
| non_surge | 6 | 4 | 0 | 0 |
| 2–3x | 2 | 5 | 0 | 0 |
| 3–10x | 0 | 5 | 0 | 0 |
| 10x+ | 0 | 2 | 0 | 0 |

- 16 个正向预测全部为 `2–3x`；低估 7 例（3–10x×5、10x+×2）、高估 0 例；2 个 FN 与 7 个低估已分开统计。
- 各档 support：2–3x=7、3–10x=5、10x+=2（全集口径含 FN）。
- 浮点 F1 存储为 `0.7999999999999999`：行动计划 §4"用混淆计数构成的有理数比较"的担忧有实证依据。

## 3. 标签分母与 prediction_baseline 链路审计

`prediction_baseline` 由 `_prediction_baseline_from_market_documents`（`src/stock_opportunity_agent/research/evolution_core.py:2455`）从完整 PIT 市场文档计算：仅取 `as_of_date` 严格早于预测日的 `adjusted_close`，且文档 `available_at` 晚于预测时间即报错（PIT 内建校验）。链条与固定分母定义一致，**未发现需要更换分母的依据**。

6 条案例反思含 baseline／price-reference 措辞（case 8、10、11、17、19、20，见 JSON `review_pending_reflections`），按行动计划 §2.2 全部标为**待审核模型建议**，不采纳为学习规则。

## 4. 正确性回归矩阵（源头：campaign state.md 与联合正确性审计）

三态标注：**已修复（实机）**＝真实运行验证过；**仅离线验证**＝单测／重放验证、未实机；**未修复**＝开放缺陷。

| # | 缺陷类别 | 源头 | 状态 |
| --- | --- | --- | --- |
| 1 | 时点无效的 exact partial residual、路由丢失父代 cutoff、exact-transition 与 temporal guard 矛盾 | V117／rounds01–09 | 已修复（V121／V125／V126 实机） |
| 2 | 整对象旁路、membership projection 捷径、需显式逐操作成员权限 | rounds14–16 | 已修复（V126 实机） |
| 3 | 隐藏 Basic 字面值同一性突变、过早暴露 ValidationError | V120／rounds17–18 | 已修复（V126 实机） |
| 4 | 聚合证据反馈不可行动、空 prior Basic 反馈遗漏 | round17 | 已修复 |
| 5 | 重复需求保留的 occurrence-aware 校验（Wynn 202/203） | rounds14–16 | 已修复（离线重放验证） |
| 6 | 提案否定式所有权误拒（not/never 非发行人自述） | V125／rounds25–26 | 已修复（V126／V127 实机） |
| 7 | round 提交后 `load_stats` 缺 stats.json 崩溃 | V126／round27 | 已修复（V129／V130 实机） |
| 8 | 导入历史 meta 轮号与本地轮号碰撞 | V129／round29 | 已修复（V130 实机 meta append 存活） |
| 9 | 漂移重试不带诊断（字节同一重试→缓存重放） | V128／round28 | 已修复（V129 实机触发并生效） |
| 10 | Signal 数量摩擦、H_reflect 引用计算比值 | round30（`2e1b7c3`） | 已修复（离线；V130 运行于其上） |
| 11 | **第三类缓存重放死端：full-revert projection + identical revalidation 重放同一缓存请求** | round28 记录 | **未修复**（需通用 same-request guard；P2／P3 改动区域最易触发） |
| 12 | **SIGINT 中途吞信号，被迫 SIGTERM 硬杀** | V127、V130 两次复现 | **未修复**（graceful interrupt 需 check-window） |
| 13 | Slow 阶段完整实机执行 | round32 离线重放完成；V130 首入 slow 即暂停 | 仅离线验证（实机完成待预算授权） |
| 14 | SSL 瞬时抖动 | V130 四次 | 已缓解（bounded supervisor） |
| 15 | 路由纠偏摩擦（80%／159% corrections） | V126 审计 | 部分缓解（round26／30），残留为摩擦而非正确性缺陷 |

## 5. 冻结的验证命令

- 全量测试：`PYTHONPATH=src uv run --no-project --with pytest -m pytest tests/ -q`（uv 托管 CPython 3.13.13；`requires-python >=3.11`，系统 `/usr/bin/python3` 3.9 不可用）。
- 仓库 lint：`scripts/lint_repo.sh`。
- 焦点测试：同命令替换具体测试文件。
- 历史测试计数（953／956 等）仅作参考，不作为当前验证结果；每次以当次输出为准。

## 6. P0 验收对照

- 重算 F1=0.8、幅度准确率 5/14、macro-F1≈0.1754385965：**通过**（三方对齐全绿）。
- 七个幅度低估与两个 FN 分开：**通过**（§2 矩阵）。
- 源 workspace 零改写：**通过**（仅读取；产物写入 `reports/`）。
- 回归矩阵含三态标注并点名两个未修复项：**通过**（§4 #11、#12）。

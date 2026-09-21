# C5 全池逐案 PIT 证据覆盖审计（2026-09-21）

对应方案：[`signal-magnitude-and-fast-parallel-action-plan-20260921.md`](signal-magnitude-and-fast-parallel-action-plan-20260921.md) §A0 硬准入门控中经用户确认的挖掘前准入项（全池逐案 PIT 覆盖 ≥90%，失败计入）。
机器可读结果（含全部失败 case id）：[`signal-magnitude-c5-pit-coverage-audit-20260921.json`](signal-magnitude-c5-pit-coverage-audit-20260921.json)。

## 结论：**不通过** —— magnitude_ge3 实施回到 blocked（PIT 前置项未达）

| 数据集 | 案例数 | any-PIT 覆盖 | 180 天窗口覆盖 | 失败案例数 |
| --- | --- | --- | --- | --- |
| Discovery | 8,755 | **49.32%** | 41.63% | 4,437 |
| Evolution validation | 3,623 | **4.86%** | 4.64% | 3,447 |

审计口径：对全局 oracle（`raw-info-8421e3b2…`，11,402 份文档、1,325 家公司）逐文档读取 `available_at`；案例覆盖＝该公司存在至少一份 `available_at ≤ prediction_time` 的文档。独立复核（仅按公司目录存在性）与上表一致（validation 244/3,623 有目录，discovery 5,026/8,755）。

## 原因解读（非数据错误，是物化范围差异）

- oracle 只包含历次运行实际物化过的发行人证据（v13 评估快照的 24 案、历史 seed 案例、慢环挖掘对象等），从未覆盖全池。
- validation 池 875 发行人中绝大多数从未被任何运行触达——此前的"24 案全有 PIT news"是**快照级**结论，不能外推到全池（C0 记录中已标注此风险，本次审计证实）。
- 离线优先约束下，缺失证据无法凭空补齐；补齐需要外部 provider 调用（属需另行授权的真实执行）。

## 用户决策（2026-09-21，路径 a′）

- **口径变更已确认**：PIT 覆盖准入项的审计口径从"全池"改为 **ge3 研究总体（真实 ≥2x 案例）**。按该口径现状：discovery 高/低组 99.4%／97.3%（达标），validation 高/低组 53.8%／29.2%（不达标）——短板明确收敛到 validation 池的 162 案 + discovery 的 17 案。
- **一次性补齐已授权（原则）**：冻结补采清单见 [`signal-magnitude-c5-backfill-manifest-20260921.json`](signal-magnitude-c5-backfill-manifest-20260921.json)（179 案／115 发行人；SEC 免费源优先，AV 新闻按 25/天配额分批；建议上限 500 次调用／$5）。执行走既有 `scripts/backfill_historical_data.py` 的 preview→plan→run 管线（preview 离线先行）；完成后按研究总体口径重跑本审计。

## 按方案处置

1. **ge3 专属 schema、投影、挖掘执行、晋升实现一律不启动**（A1：门未过不得实施；门失败记录 blocked/insufficient_support）。
2. 发行人/月份簇两项此前已达标，本次失败项仅 PIT 覆盖——解锁路径（需你选择/授权，二选一或组合）：
   - **路径 a（授权补采）**：授权对两池全部发行人做一次预测时点前的证据回填（外部调用，需预算），完成后重跑本审计；
   - **路径 b（缩总体）**：把 ge3 研究总体限定为"已覆盖子集"——这是研究总体定义变化，需要重新确认（且 validation 已覆盖子集极小，可能使独立验证不可行，等价于 ge3 仍不可实施）；
   - **路径 c（维持 blocked）**：保留审计，转而继续不依赖该目标的工程工作（B 工作流已闭环；C8 中非 ge3 部分的集成验收可先行）。
3. ge10／extremes 维持原 blocked（发行人支持不足）。

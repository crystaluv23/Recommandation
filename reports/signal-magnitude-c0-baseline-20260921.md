# C0 基线：A0 数据支持 + B0 共享状态与耗时（2026-09-21）

对应方案：[`signal-magnitude-and-fast-parallel-action-plan-20260921.md`](signal-magnitude-and-fast-parallel-action-plan-20260921.md)（2026-09-21 评审修订版，代码基线 `9f85f46`）。
机器可读数据表：[`signal-magnitude-a0-data-support-20260921.json`](signal-magnitude-a0-data-support-20260921.json)。全部为离线只读盘点；未发起任何外部调用，未打开 Locked Test。

## A0.1 数据支持表（原始计数，未扣隔离约束）

| 数据集 | 档位 | 案例数 | 独立发行人 | 月份覆盖 |
| --- | --- | --- | --- | --- |
| Discovery | 2–3x | 406 | 270 | 见 JSON `by_class` |
| Discovery | 3–10x | 157 | 99 | 见 JSON |
| Discovery | 10x+ | 2 | 2 | 见 JSON |
| Evolution validation | 2–3x | 171 | 109 | 见 JSON |
| Evolution validation | 3–10x | 62 | 42 | 见 JSON |
| Evolution validation | 10x+ | 3 | 2 | 见 JSON |

**ge3 投影（真实 ≥2x 总体）**：Discovery 高组（≥3x）159 案／102 发行人、低组（[2x,3x)）406 案／270 发行人、两组发行人交集 62；Evolution validation 高组 65 案／44 发行人、低组 171 案／109 发行人、交集 22。validation 高组月份分布：2025-01×2、03×15、05×22、07×21、09×5（5 个月份簇，无单一月份主导）。

**ge10／extremes**：Discovery 10x+ 仅 2 案／2 发行人，validation 3 案／2 发行人（AXTI/HYMC）。任何合理最小支持门槛都不可能通过——按方案 A1 硬门控记 **blocked/insufficient_support（永久，除非独立数据扩容后重新过门）**，首版不铺任何专属代码。

## A0.2 magnitude_ge3 gate 记录（状态：门槛已提出，待用户确认）

| 项 | 值 |
| --- | --- |
| 目标 | magnitude_ge3（真实 ≥2x 总体；高组 ≥3x vs 低组 [2x,3x)） |
| 数据版本 | v13 approved（`dataset_manifest.approved.json`；数字见上表与 JSON） |
| 归纳池（Discovery）各组独立发行人 | 高 102／低 270（交集 62——同一发行人可有不同结局的两次事件，属对比研究内的自然配对，须在混杂审计中按"预测时可得的行业／时期／规模／流动性"匹配） |
| 验证池各组独立发行人 | 高 44／低 109（交集 22） |
| 时段覆盖 | validation 高组 5 个月份簇（2025-01 至 09），最大簇 22 案 |
| 发行人与日期隔离 | 跨 split 发行人重叠 **0**（discovery∩validation、discovery∩locked、validation∩locked 均为 0；locked 2,181 案未读内容仅用 id 集合核对重叠）；Slow 侧 dev/check 由既有 `build_slow_sampling_manifest` 强制发行人隔离 |
| 预测时证据覆盖 | 快照级已验证（v13 round-1 24 案全部有 PIT news）；**全池逐案覆盖审计延后到 C5 挖掘前**执行，gate 记录保留该未闭环项 |
| 已确认最低支持要求 | **未确认**（方案修订明确数值门槛不在本次批准内）|
| 结论 | 数据面无硬阻塞，但 gate 未通过——"门槛尚未确认"本身即不通过；ge3 专属实现继续禁止 |

**建议门槛（供确认，非已批准）**：每个数据集每分组 ≥30 独立发行人、≥3 个不同月份簇、dev/check 发行人隔离可行（既有机制）、全池逐案 PIT 证据覆盖 ≥90% 且失败计入。按此门槛 ge3 在两池均满足前两条；证据覆盖项待 C5 前审计。

## A0.3 signal_library 接口清单（多目标统计必改面）

| 接口 | 位置 | 目标维度现状 |
| --- | --- | --- |
| `SignalStats`（state→计数，含二元 surge 计数） | `signal_library.py:977`（`record_result`:996、`surge_rate`:1035→1047） | 仅方向（`is_surge`） |
| `SignalRegistry.record_result`／`record_observation`／`record_learning_events` | `signal_library.py:1555/1567/1637` | 无 target 维度；observation 幂等键不含 target |
| learned profile 聚合／检索卡读取 | `signal_library.py:3836` 一带（`positive_surge_rate` 等） | 方向语义 |
| Fast 侧统计写入 | `plan_evolution.py:2292/2297`（`_record_signal_statistics`） | registry 外部唯一 `record_observation` 调用链 |
| Slow 侧 learning 导入 | `evolution_control.py:1874/2418` | 方向语义 |
| Mining 有效性 | `signal_evolution.py` 内 per-cycle paired-effectiveness 记录（存 slow 工件，非 SignalStats） | 方向 positive/control 分组 |
| 观察去重 vs 目标评估去重 | 上述两组入口 | 现为同一身份；A3 要求物理执行观察与目标评估记录分别幂等且费用单记 |

结论：与方案 §8 修订一致——`signal_library` 为必改接口面；实施顺序在 C5（gate 通过后），先 owning spec 后代码。

## A0.4 泄漏／重叠审计

1. 跨 split 发行人重叠为 0（实测，见 A0.2）。
2. 同发行人跨档位（交集 62/22）不是跨集泄漏，但构成组间相关——ge3 对比的配对与不确定性分析必须按发行人成组，方案 §9 已有此要求，C5 实施时落在采样 manifest 与分析协议里。
3. V130 的 24 案已用于幅度反思，只作回归证据，不作为 ge3 独立验证（方案 §9 约束重申）。
4. Locked Test 仅做 id 重叠核对，内容未读。

## B0.1 V130 实测耗时表（权威口径 attempts.json + trajectory 事件）

运行段：cycle start 11:26:35 → 就绪+提案 → **c01 评估 11:31:42–13:31（24 案全程）→ c02 槽位提案+评估 13:31:56–13:33:36（15 案，绝大多数命中 c01 热缓存，case_trajectory_reused=110）→ 拒绝 → round commit 13:33:51 → slow 开始 13:33:53 → 暂停**。

| 量 | 值 |
| --- | --- |
| 外部 attempt | 759（752 完成／7 失败），费用 $2.5239 |
| 单次 attempt 墙钟 | p50 4.6s／p90 11.2s／p99 28.1s／max 85s／合计 4,915s |
| 单案例墙钟 | n=38 完成案例，p50 139s／p90 195s／max 222s／合计 5,015s |
| 结构修正 | fallback 40 次、projection applied 34／retained 25（摩擦但未死端） |

**吞吐潜力结论（不承诺倍数）**：c01→c02 完全串行（0 重叠）；案例级工作合计 5,015s 占 fast 阶段墙钟大头。并行 2 worker 的收益取决于跨候选相同请求的比重——V130 里 c02 的 15 案几乎全部复用 c01 缓存，说明**两候选请求高度重叠**：串行时第二次评估近乎免费但必须等第一次完成；并行时若配 B2 in-flight 去重，两 worker 共享同一物理响应（时间重叠、费用≈1×）。潜在收益成立，量级待 C4 离线等价+固定响应压测后按 B5 冻结。

## B0.2 可变对象所有权与共享写入清单

| 对象 | 今日所有权 | 并行所需 |
| --- | --- | --- |
| `RuntimePlanEvaluator` 的 controller／signal_agent／predictor（`plan_evolution.py:113-115`） | 单实例，靠顺序执行安全 | 每 worker 独立实例（工厂） |
| workspace execution lock（fcntl，`plan_evolution.py:544`） | 整 run 单持有 | 保持：仅协调者持有 |
| `AttemptLedger.reserve/finalize`（JSON 读改写，`evolution_transport.py:233/270`；attempt_id=len+1） | 单线程安全 | 同进程互斥 + 公平准入 |
| 请求缓存 `store(request_hash,…)`（哈希寻址+原子写） | 幂等 | 只读共享；in-flight 去重单记费 |
| Raw Info append（flock，`raw_info.py:418`） | 跨进程安全 | 沿用 |
| `data_requests.jsonl`／`data_acquisition_requests.jsonl` append | **无锁**（B2 修订点名） | 协调写入或受保护完整 append |
| experiments/trajectory.jsonl 事件序号 | 引擎单线程分配 | 协调者队列分配 |
| stats／learning／meta 写入 | 仅 commit 后（协调阶段） | 保持 commit 阶段单写者 |
| evaluation attempt staging（`stage_evaluation_attempt`，循环内逐个调用 `plan_evolution.py:2014`） | 逐候选 | worker 写各自 plan/case staging；checkpoint/rejected 等协调者文件不动 |

## B0.3 缺陷前置清单（升级为实施门槛）

- **#11 第三类缓存重放死端**：round28 记录 unfixed；触发面＝correction 链内 full-revert projection + identical revalidation。C2 准入：通用 same-request guard 先实现并以三语义测试验收（同链同请求拒绝／跨链合法共享放行／传输重试不混判），guard 作用域绑定逻辑 correction 链，不做全局 hash 黑名单；之后才允许 in-flight 去重接线。
- **#12 SIGINT 中途吞信号**：V127/V130 两次实锤（SIGINT 无效→SIGTERM 硬杀）。C3/B4 准入：信号只由协调者主线程处理并置取消标志；worker 不装处理器、在安全边界查标志；主线程对 worker 的等待必须有界可中断；urllib 阻塞调用显式超时；对"主线程等待 future／worker 阻塞传输／线程池关闭"三条路径复现停止场景后才允许 C4 并发度 2。

## C0 验收对照

- 数据 gate 状态、统计接口清单、两份采集 ledger、#11/#12 前置清单：齐全（§A0.2/A0.3/B0.2/B0.3）。
- ge10／extremes：硬门控记 blocked；ge3：门槛待确认，专属实现继续禁止。
- 耗时基线：V130 实测（§B0.1）；串行重放基线以现有 1006 测试套件+P6 矩阵为并发度 1 等价的对照基线（C2 将新增显式等价测试）。

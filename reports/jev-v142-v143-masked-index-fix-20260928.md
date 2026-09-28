# V142/V143 自进化 live 验证：增量纠错与可溯源反思内存 + 入口脱敏缺陷修复

日期：2026-09-28。运行目录：`.delegation/fast-slow-20260919/v142`、`v143`；workspace 见 `runs/cold_start/evolution/information-evolution-jev-dual-self-evolution-2026092{8-v142,8-v143}`。

## 概要

按用户要求对最新代码（4de815b：增量纠错 + 可溯源反思内存）执行 fast+slow round 测试门槛，通过后启动新的自进化 live 流程并全程监控内容正确性、信息流动与入库行为。期间发现并修复了一个阻断 Slow 挖掘管线的真实代码缺陷（入口脱敏破坏内容哈希），修复经真实状态离线验证与 1,146 项测试后以 V143 续跑验证：

- **V142**（4de815b）：2 个 round 提交（F1 .667/.690 → .720），cycle 1 Slow 挖掘管线死于哈希校验；$3.85/948 attempts。
- **修复**（ebf1d83）：四个站点改为"权威未脱敏构建 index + 模型可见出口脱敏"。
- **V143**（ebf1d83，导入 V142 历史）：cycle 1 Slow 挖掘管线零失败，**挖出 4 个新因子并完整走完 入库→验证→判定**，全部为诚实研究性判定；registry 维持 v6（零晋级）。

## 一、测试门槛（离线）

- `python -m unittest discover -s tests`：**1,144 通过**（修复后 1,146）。
- `scripts/lint_repo.sh`：PASS。
- `scripts/replay_incremental_reflection_memory.py`：零外呼重放通过；proposer 首屏 55,765 B（对照全量保留 meta 341,321 B，-83.66%）。

## 二、V142：新代码的线上表现

冻结与 V141 完全同构（同 dataset/seed pool[V126 winner]/slow-history[v115]/registry v6/模型组/预算 4800/$16），唯一变量是代码。

**Fast 循环内容审计（wire 级，60 条轨迹 + 568 个请求）：**

- 增量纠错全面生效：**201/201 个 reflect 纠错响应为 delta patch**（870 条操作，单次 1-11 条），无整体重写。
- needs 传递链 44/44 一致（reflect→下一轮信息需求，容许每轮 ≤2 条新增）。
- jev explain 不可变载荷 47/47；jev/magnitude 反馈进入轨迹 42/48（6 条为技术排除/弃权，正确不参与研究归因）。
- posthoc 反思采用新格式（reflection_items 带 brief/detail/refs + no_findings_reason），其纠错率 92%——新合同较严，但全部收敛。
- round 级反思两次纠错仍未通过验证（"success/failure reflection requires canonical outcome claims"），引擎诚实记录 no_findings_reason，未伪造经验——验证器按设计拒绝无 canonical 结果支撑的结论，初始 prompt 确实携带 canonical metrics。
- 提交后链路（V126 崩溃点 stats 记录、V129 崩溃点 meta append）live 存活：18 个 stats.json、round meta 落盘。
- V141 的阻塞点未复现：cycle 2 proposal 上下文 ~65KB（含导入历史），远低于 256K 冻结上限。

**指标：** cycle 1 c01 F1 .667/P .625/R .714、c02 F1 .690（magAcc .286/magF1 .157）；cycle 2 c02 F1 .720/P .818、magAcc .357/magF1 .208（c01 两轮均被评估门截断：19/24、9/24）。

## 三、缺陷：入口脱敏破坏反思哈希（cycle 1 Slow 挖掘空转的根因）

**现象：** V142 cycle 1 slow_loop_started 后 4 分钟 `slow_pipeline_failed`，agent_audits 记录 `ValidationError: reflection item content hash mismatch`；H1 挖掘管线死亡，仅 H2 更新管线继续，最终 validated={}/promoted=[]。cycle 2 同样注定空转。

**复现：** 用全量身份 guard（discovery+anchor+evolution_validation 共 26,937 个别名）对 119 个已落盘反思条目做入口脱敏后加载，**13 条哈希断裂**（`detail` 内嵌population内其它公司名，如同行对比语句）；窄 guard（仅 24 个 round case）则 0 条——这解释了为何 fast 路径（窄别名集）幸存而 mining（全量 guard）必死。

**根因：** `item_ref`/`source_ref` 是**内容哈希**。四处站点在 `ReflectionMemoryIndex` 构造**之前**对条目做 `_mask_identity_values`，脱敏改写内容后重算哈希必然不等于存储 ref。次要危害：经脱敏 index 授权写作的条目会绑定"脱敏内容哈希"的 source ref，持久化后在任何权威视图永远无法解析。

**修复（ebf1d83）：** index 一律用权威未脱敏条目构建（哈希校验严格保留）；身份只在模型可见出口移除——

1. `signal_evolution.py` mining 上下文：meta_view/meta_catalog/预读原件全部出口脱敏（与文件内 prior_slow_work 等字段同款惯例）。
2. `evolution_plan_roles.py` proposer：删除入口脱敏（出口脱敏本就存在）。
3. plan critic：删除入口脱敏，catalog/briefs/trajectories 出口脱敏。
4. round reflector：删除入口脱敏（整体 payload 出口脱敏本就存在）。
5. `_ReflectionMemoryCaller` disclosure：读取的原件在送出前脱敏。

**验证：** 真实 V142 状态离线重放（`v142/verify_fix_offline.py`）：权威 index 构建成功（330 items/718 sources）、旧入口脱敏路径仍被拒（钉住缺陷）、出口视图 0 别名泄漏、采样 ref 全部可解析；1,146 tests + lint + 离线重放（proposer 载荷字节数不变）全过；新增回归测试 2 项钉住"入口脱敏必须被拒绝、出口脱敏必须保 ref 可解析"。

## 四、V143：修复后的完整 Slow 管线（live 验证）

冻结导入 V142 已提交历史（2 rounds + cycle1 slow 工件），其余同构。

- **`slow_pipeline_failed` 出现次数：0**（V142 同期 1 次、且必死）。
- 挖掘链路完整执行：signal_mining_reflect（消费 feedback + prior memory，含 slow_source_read 按需读原件）→ 44 次 mining_controller_step（轴种子探索）→ 12 次 mining_candidate_materialize → 验证批次 → H2 更新决策。
- **4 个新因子真实挖掘并物化入库**（V142 因缺陷为零）：
  - `commercial_event/named_customer_order_or_contract_award_disclosed:v1` → provisional
  - `commercial/new_customer_commitment_value_disclosed:v1` → provisional
  - `commercial_disclosure/qualifying_order_disclosure_120d/v1` → provisional
  - `commercial_commitments/disclosed_customer_commitment_value:v1` → rejected（fixture 语义门：把泛泛的合同资金表述判为 neutral 而非 unavailable，拒绝理由附带完整推理）
- 判定全部为**研究性诚实门槛**（"过半正类案例未命中"/"decisive support 低于配对下限"），无代码性失败；registry 维持 v6，goal=unmet。
- 出口脱敏线上高频工作：每个 mining 载荷 168-171 处 MASKED 标记、**0 个原始 cik 泄漏**。
- 跨 run 信息流确认：V142 round 1 的未满足研究需求（masked、source_rounds=[1]）出现在 V143 挖掘 backlog（129 条）中。
- cycle 1 fast：c01 F1 .600/P .562/R .643（c02 15/24 被评估门截断，fitness ineligible：incomplete_case_set）。

## 五、指标进展与提前终止判定（最终）

本 session 全部 round 的 F1：.667/.690（V142 r1）→ .720（V142 r2 c02，P .818，magF1 .208）→ .600（V143 r1 c01）→ .560（V143 r2 c02，P .636/R .500，magF1 .190）；magnitude 全程持平（magAcc .286-.357，magF1 .157-.208）；registry 晋级数为 0（V126 以来所有 live run 均止步 v6）。

**判定：停滞成立，按用户标准提前终止。** 修复后的管线已获得公平验证（cycle 1 Slow 完整跑通挖掘→物化→验证→判定；两个 cycle 的 fast 循环；V143 cycle 2 round 2 已提交）。V143 的两个 cycle F1 递减（.600→.560）且低于修复前最佳 .720，magnitude 无突破，无晋级。V143 于 cycle 2 slow 起点处干净停止（round 2 已提交，workspace 一致可续）。

正面信号：cycle 2 round 2 的父方案首次选中本地提交的 `plan_r0001_c01`（Top-K 亲子链生效，此前所有 round 只用导入种子）。

**费用合计：** V142 948 attempts/$3.85 + V143 1,252 attempts/$5.31 ≈ **$9.16**。

## 六、遗留观察（非阻塞）

- posthoc 反思 92% 纠错率：新格式合同严格导致的首答合规摩擦，全部收敛但占用预算，可考虑在 prompt 中前置 refs 解析规则示例。
- H_init 纠错率 146%（67/46）：与 V129 审计一致的老摩擦（PIT/义务引用），未恶化。
- round 级反思两次未过验证（canonical outcome 绑定）→ 该层经验本轮为空；模型侧合规有待提升，引擎侧行为正确。
- graceful-interrupt 缺口（SIGINT 不被阻塞中的传输响应）依旧存在，本次以 SIGTERM 处理。

# Slow Round 挖矿 Agent 化行动方案（2026-09-16）

> 本文档是自包含的执行方案。执行者无需会话上下文；所有路径、命令、验收标准
> 均已对照仓库当前状态（HEAD `b37133a`）核实。执行前先读 `AGENTS.md`。

## 0. 背景与目标

### 0.1 现状诊断（已实证，勿重新论证）

- V89 完成两个干净提交的 slow cycle（166 次尝试、$1.1365、退出码 0）：
  Update 非零（两轮各 3 候选、全部被配对门诚实拒绝）；**Mining 为 0**。
- Mining 归零的根因已定性：H1 在无证据可见的条件下提出语料中不可测的
  observable（分析师目标价、backlog 占比、现金跑道分母），E1/E2 的证据包
  是先验有损压缩（选篇 2–4 篇/截断 2400 字/6 观察槽/label-blind），
  E2 只能诚实判 inconclusive。
- V87 自然实验：同样的链路，当 H1 提出可从 Company Facts 测量的
  `operating_cash_flow_deficit_state` 时，产出了系统历史上第一个可执行
  Mining 候选。**可测量性是绑定约束，不是链路长度**。
- 已落地修复：`measurable_evidence_manifest`（commit `b37133a`，
  784 测试通过）——给 H1 一张运行时计算的、无值的可测证据族清单。

### 0.2 目标架构（一句话）

**保留两端（Update 管线、候选验证/晋升门），替换中段（H1/H2/H3/E1/E2
双轨 → 单一 MiningAgent 循环 + 共享工具层 + 探索账本）**：

```text
共享 infra（唯一语义，一处修复全局生效）
  raw info store + resolver（PIT 强制） / 身份掩码 / 冻结合约+哈希血缘
  / attempt-cost 台账 / measurable_evidence_manifest / slow memory 管道
        │
MiningAgent 循环（渐进披露：拉证据/算数 → 组内检验 → 对照检验 → 记账）
  ├─ 种子A（hypothesis 驱动）：backlog + meta-memory + prior failures
  │    假设准入：manifest 可测 + 非重复 + 可证伪 + PIT 合法
  └─ 种子B（无监督）：开放对比目标
        │
  终局：候选 signal spec（measurement+逐字引用+falsifiers+applicability）
        或 诚实 no-pattern + 账本引用
        │
候选验证（不变）：fixture 门 → issuer 不相交 holdout 配对评估
  （绝对底线 + 严格增益）→ 原子晋升
        │
跨周期自进化：探索账本 + 结果 → 反思蒸馏 episodes/lessons
  → 下一轮种子上下文改变搜索策略
```

### 0.3 成功标准（三层，最终验收）

1. 无报错跑通：exit 0、无阶段失败、无错误提交。
2. 信息链路正确：账本/反思真实消费上轮结果并改变下轮行为（有逐条证据）。
3. Mining > 0 且 Update > 0（候选数非零；晋升与否由门诚实决定，不放松）。

## 1. 必须复用的资产（不得重写）

| 资产 | 代码位置 |
|---|---|
| PIT 证据访问 | `data/raw_info.py` `documents_as_of`；resolver + `RawInfoRequest` |
| 结构化记录选择器 | `research/evolution_core.py` `_company_facts_context`（含 latest/comparable 血缘） |
| 有界模型视图/掩码 | `evolution_core.py` `_model_evidence_view`、`_select_h3_model_evidence`、`_mask_identity_values` |
| 行情计算锚 | V88 修复的 market calc anchors（在软信号执行投影路径内） |
| 失败语义分类学 | `measurement_contract`（decisive/NEUTRAL/unavailable/技术失败） |
| 配对评估门/fixture 门 | `signal_evolution.py` 候选验证路径；`effectiveness_evaluator.case_limit` |
| 采样清单 | `signal_evolution.py` `build_slow_sampling_manifest`（issuer 不相交、前冻结） |
| 预算/台账/trace | `evolution_transport.py`（attempt ledger、request trace、失败消息持久化） |
| slow memory 管道 | reflection → episodes/lessons → 下轮上下文（V89 已实证） |
| manifest | `signal_evolution.py` `_h1_measurable_evidence_manifest` |

## 2. 阶段计划

每阶段完成 = 测试过 + lint 过 + `progress/status.md`/`changelog.md` 更新
+ 一个 git commit。任何阶段失败：修复后重跑该阶段验收，不得带病推进。

### Phase 0：V90 live run（验证 manifest；可与后续阶段并行）

1. 冻结（镜像 V89 参数，`--slow-bootstrap-from` 指向 V89 工作区）：
   ```sh
   bash scripts/run_information_plan_evolution.sh new \
     --workspace runs/cold_start/evolution/information-evolution-slow-self-evolution-20260916-v90 \
     --raw-info-root runs/cold_start/data/global-raw-info-oracle-v1 \
     --approved-dataset runs/cold_start/evolution/full-market-expanded-2025plus-v13-approved-inputs/expanded_dataset_proposal/dataset_manifest.approved.json \
     --run-id information-evolution-slow-self-evolution-20260916-v90 \
     --judge-model deepseek-v4-flash \
     --evolution-model deepseek-v4-flash-thinking \
     --max-external-attempts 200 --max-total-cost 5 \
     --slow-bootstrap-from runs/cold_start/evolution/information-evolution-slow-self-evolution-20260913-v89 \
     --data-external \
     --max-data-requests-per-cycle 200 --max-data-requests-per-run 400 \
     --data-provider '*' --data-capability '*' --data-source-type '*'
   ```
   注意：冻结要求 git 干净（`evolution_transport.py` 的 `current_code_revision`
   会拒绝未提交的 src/scripts/configs 变更）。
2. 执行（DeepSeek 已获用户总体授权；环境变量见 `~/.env.local` 的
   `DEEPSEEK_API_KEY`，先 `set -a; source .env.local; set +a`）：
   ```sh
   bash scripts/run_information_plan_evolution.sh resume \
     --workspace .../v90 --raw-info-root ... --approved-dataset ... \
     --max-cycles 2 --external --data-external \
     --acknowledge-contract-hash <冻结时打印的 hash>
   ```
3. 审计（三层标准逐条核对；读 `experiments/cycles/cycle-*/slow_loop_result.json`
   的 `new_candidate_count`/`updated_signal_count`、H1 响应中假设是否锚定
   manifest 概念、E2 对比是否拿到结构化记录对）。
4. 验收：exit 0 干净提交；若 Mining>0 → 提前达成第 3 层的挖掘半边；
   若仍为 0 → 从 E2 rationale 定性新卡点，作为 agent 设计的输入，
   **不得**在旧链路上继续打提示词补丁。
5. V90 不可变保存；结果写入 status/changelog。

### Phase 1：Spec 先行

1. 新建 `spec/src/stock_opportunity_agent/research/signal_mining_agent.md`：
   工具契约（fetch/compute/read_span 的输入输出、预算、PIT、掩码）、
   账本 schema、种子A/B 上下文、循环步契约（thought/tool_call/terminal）、
   终局产物 schema、p-hacking 三件套（holdout 门不动/账本/引用接地）。
2. 同步修改 `signal_evolution.md`（挖掘段改为 agent + 影子/切换语义）、
   `evolution_signal_roles.md`（新增 agent 角色；H1/E1/E2 标注 legacy）。
3. 检查 `spec/architecture.md`：若其表述绑定了 H/E 阶段名，按树一致性
   规则先在祖先层确认修改（Slow Loop 仍是"Signal Mining and Signal
   Update"，预计只需微调措辞）。
4. 验收：spec 评审通过（用户确认）；无代码变更。

### Phase 2：共享工具层

新文件 `src/stock_opportunity_agent/research/mining_agent_tools.py`：

- `fetch_case_evidence(case_refs, source_family, query=None, window)`
  → 每案例有界摘录列表（带 document_ref/content_hash 血缘；复用
  `_select_h3_model_evidence` 的评分与截断语义，但**去掉先验多样性选篇**，
  由 agent 的 query 驱动）。
- `compute_statistic(concept, stat_rule, period_rule, case_refs)`
  → 确定性数值表（行带 concept/unit/period/记录引用血缘；复用
  `_company_facts_context` 与行情锚；**禁止**任何 LLM 参与）。
- `read_span(document_ref, span)` → 有界逐字扩展。
- 所有工具：PIT 由 store 强制；输出过 `_mask_identity_values`；
  每次调用自动写一条账本条目（见 Phase 3）；每调用字符/文档上限。
- 验收：单测覆盖（血缘可回溯、PIT 边界、掩码、预算上限、无值泄漏到
  manifest 语义）；全套测试 + lint 过。

### Phase 3：探索账本

- 每周期新增 `experiments/cycles/cycle-XXXX/mining_ledger.json`（周期内
  append-only，runtime 拥有）：工具调用条目（运行时自动写）+ agent 撰写的
  放弃 rationale + contrast 状态（explored/abandoned/promising/terminal）。
- 终局一致性校验：候选引用 ⊆ 账本；promising 未进终局必须有显式放弃理由；
  no-pattern 必须引用账本覆盖面（试了多少 contrast 族/证据族）。
- 新反馈单元类型 `mining-ledger:*` 接入 `slow_input` 的 feedback_rows，
  使反思可蒸馏（"这类尝试从未存活"成为 lesson）。
- 验收：单测（一致性校验、append-only、反馈单元投影）；全套 + lint 过。

### Phase 4：MiningAgent harness

- 同一循环体、两个种子构造器（A：假设准入四条件 + manifest；
  B：开放对比）。循环步为结构化输出（复用现有 structured-correction
  机制与 request trace）；步数上限（建议默认 24/周期）与工具调用预算
  接入现有 attempt/cost 台账。
- 终局产物直接进入**现有**候选验证（fixture 门 → holdout 配对评估），
  门逻辑零改动。
- E1/E2/H1/H3 保留为对照轨（shadow），`_merge_mining_fallback` 暂不动。
- 验收：离线脚本测试（fixture caller 驱动完整循环：种子 → 工具调用 →
  记账 → 终局 → 一致性校验）；全套 + lint 过。

### Phase 5：影子验证（零调用/回放优先）

1. 在 V89/V90 冻结历史上做零调用回放：agent 输入与控制轨一致、
   工具返回可由本地语料确定性重放。
2. 授权 live 影子轮：agent 轨与控制轨并行跑 1–2 个周期。
3. 验收（切换条件）：agent 轨产出候选数 ≥ 控制轨；或控制轨为零而
   agent 轨非零；且账本/接地校验零违例、三层标准全部满足。
4. 失败处置：不满足则回 agent 设计迭代（Phase 2–4），**不得**切换。

### Phase 6：切换 + 扩规模

1. 用 MiningAgent 替换双轨（删 legacy H/E 路径与 merge fallback，
   按 AGENTS.md 的模块移除纪律归档 spec）。
2. 扩 cohort：`SignalMiningConfig.case_pool_limit`/`induction_cases_per_class`
   与 `effectiveness_evaluator.case_limit`（`build_slow_sampling_manifest`
   的 dev/check 上限来源，`signal_evolution.py:3365-3374`）——
   目标归纳工作集 16+16、check 16；成本预算相应上调并观察。
3. 验收：非零 Mining 且门拒绝率符合预期（门的假阳性防御未被绕过）；
   全套 + lint 过。

### Phase 7：在线语料版本接口（仅预留，不实现）

- spec 中固化语义：语料版本 = population_hash；刷新只发生在**周期边界**
  （新版本进入下一轮冻结输入），严禁周期中途刷新（破坏哈希血缘重放与 PIT）。
- 实现推迟到在线化需求明确后单独立项。

## 3. 横切纪律（每个阶段适用）

1. **p-hacking 三件套**：holdout 门逻辑零改动；账本 runtime 拥有；
   引用接地（逐字 span 或确定性输出行；验证失败=技术失败≠unavailable）。
2. **预算治理**：agent 步数、工具调用、attempt/cost 双顶全部硬编码在
   工具/harness 层，不依赖模型自觉。
3. **测试运行时**：`PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests`
   （系统 python3 是 3.9，会 import 失败——见
   `memory/experiences/python-runtime-for-tests.md`）。
4. **lint**：`bash scripts/lint_repo.sh`；每次 push 前读
   `.lint-feedback/pre-push-last.log`。
5. **进度/git**：每阶段一个 commit；status.md 顶部段落 + changelog 各一条；
   live run 结果只追加审计（reports/），不改写历史工作区。

## 4. 禁止事项

- 不得为产出非零而放松任何门（绝对底线/严格增益/fixture/重复门）。
- 不得在旧 H/E 链路上继续打提示词补丁替代本方案的 Phase 2–6。
- 不得周期中途刷新语料或修改已冻结合约。
- 不得让 Update 管线逻辑随本重构变更（其唯一允许增量：吃 compute 工具输出）。
- 不得删除对照轨，直到 Phase 5 验收通过。
- 外部调用仅限 DeepSeek（用户已总体授权）；新端点需再次确认。

## 5. 附录：关键索引

- V89 工作区（最新已提交历史，2 cycles）：
  `runs/cold_start/evolution/information-evolution-slow-self-evolution-20260913-v89/`
- V89 审计：`reports/slow_round_prompt_audit_20260913.md` 的 V89 节
- 冻结/执行 CLI：`scripts/run_information_plan_evolution.sh`（包装
  `scripts/evolve_information_schemes.py`）
- 模型别名：judge=`deepseek-v4-flash`，evolution=`deepseek-v4-flash-thinking`
  （与 V89 合约一致）
- 退出码 75 = 可重试传输暂停，wrapper 会自动恢复；非 75 停机排查

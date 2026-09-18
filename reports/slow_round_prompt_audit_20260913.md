# Slow 固定提示词与信息链路审查（V82）

当前结论：V82 提交 Fast/Slow 0/1，Mining、Update、Promotion 全为 0。
不满足三层验收。问题不仅是候选实现错误，也包括研究目标、角色职责、
证据选择和校验器之间的错位。

## 实际输入与输出证据

生产 workspace：`runs/cold_start/evolution/information-evolution-slow-self-evolution-20260913-v82`。
合同：`1750b302f857d3b64505f33b77208183251a1144b0ac8b9b1266af01e70dd714`。
以下均检查实际持久化的 API 请求，而非仅检查源代码模板。

- H1 请求 `c1894f320d506e1c559681eaebebcab54cc58f2a5a164ee25a704847830f524e`：
  Fast meta 和 30 个 reflection actions 已完整进入，但没有显式完整的固定预测目标。
  模型把 142 条 unmatched needs 与两个 provider failure 合并为 repair_dependency。
  这不能证明 142 条需求都受那些故障阻塞。
- E2 请求 `310ec5f1131009cd375264f1b4a72dcfd34795309c2ab28e8b1ce1c8453a1e54`：
  只有 positive/control 类别，没有显式六个月、调整后价格两倍及基准计算定义。
  历史上下文可能间接提到研究目标，但不能代替一致、权威的任务定义。
- E1 inventory 按可比记录覆盖数和常见概念排序；实际优先项包括股数、
  经营现金流、营业利润、研发、资本开支和存货。固定提示词要求第一组两期
  概念，并优先第二组财务概念。这把可比性当成了研究优先级。
- E2 的 8 个案例中，结构化观察数分别为 4/5、4/6、4/5、4/5、4/6、6/8、
  6/8、6/8。其余文字大部分仍是财务数字、亏损、负债或通用经营风险。
  个别业务合作文字仍然保留，不能声称所有叙事均被丢弃。
- 本地 oracle 的 16 个 E1 案例在各自预测时点和 365 天窗口内，没有新闻或
  电话会来源；主要是财务事实、年报和部分行情。E1 实际输入同样没有新闻或
  电话会。这证明来源不足，不证明外部供应商没有这些资料。
- Queryless 探索仅把财务与 filing 设为必要来源组；这些组满足后可以 resolved。
  因此 resolved 不是事件、催化剂或预期差证据完备的证明。

## 候选为何提歪

E2 原始 observable_difference 明确把正样本的同期间财务记录，与对照样本
“可见片段里缺少同期间记录”作比较。它把证据可比性/完整性当成业务差异。
这不足以支持营业利润与经营现金流一致性是暴涨股判别依据。
即使换成计算正确的函数，候选的研究相关性仍未得到证明。

此外，它选择 `financial.operating_cash_flow_margin`，实际计算经营现金流/收入，
不是营业利润与现金流一致性。校验器正确拒绝定义与实现不一致；有效候选数为 0。
生成阶段此前只有函数名枚举和 JSON schema，缺少实际计算及输入要求说明。

## 固定提示词的职责冲突

旧 `mine_signal` prior 要求模型抽样、执行测试并返回 staged refs，并只允许
确定性函数；该 prior 没有传入当前 H1/E1/H3/E2 路径。旧 Update prior 则实际
进入 Update 请求，却要求模型克隆、执行测试并返回 refs，与当前单目标
no_change/defer/update 输出及 runtime 所有权冲突。

研究与 Judge 共用 `deepseek-v4-flash` 默认 effort=none。为了 Judge 的
温度零设置关闭推理，同时关闭了研究角色推理；此前没有独立验证这个耦合。

## 隔离实验与校验器误伤

所有隔离实验与生产状态分离，不能计为生产候选或晋升。
归档：`runs/cold_start/evolution/diagnostics/slow-v82-prompt-audit-20260913/`。

- 非推理 reflection 二次复核花费 $0.00818188，逐字返回原错误初稿，未接入生产。
- H1 相同输入开启 high 推理，花费 $0.04258464，提出 3 个假设；输出使用
  31114 token，说明只切换模型而维持原 8000 上限会有截断风险。
- 一次真实限次纠错花费 $0.0299404，修正一组缺少逐项依据的 Update 路由。
  随后被旧通用 Predictor 正则误拦：`trailing twelve-month revenue` 被认作
  改预测期限，`remaining performance obligations` 被认作未来绩效。
- 改为 H1 自己的目标边界检查、区分 performance obligations 后，完全不改写
  该真实响应的本地解析重放得到 3 个假设。证据可行性、业务意义、验证和晋升
  尚未发生；其中分组依赖依据仍需真实审阅，解析通过不等于语义正确。

## 本次连贯修正

1. Reflection/H1/E1/H3/E2/Update 接收同一 runtime 目标定义，直接来自
   FIXED_PREDICTOR_SEMANTICS；E1 仍不接收个体标签。
2. Mining/Update 固定 prior 对齐当前职责；Mining prior 接入全部挖掘阶段。
3. E1 保留第一组可比记录，但不再优先第二组财务记录压过业务变化叙事。
   H1/H3/E2 共同要求说明研究相关性，区分业务测量和证据获取条件。
4. H3/E2/Update 获得实际注册 callable 的计算、输入和参数说明，覆盖 override。
5. H1 不再借用 Predictor 的通用期限/阈值黑名单；继续拒绝重定义固定目标
   与使用未来实际结果。后续证据时间、隐藏验证集及原晋升门槛保持不变。
6. 单独 evolution-only thinking alias 和冻结的 32000 reasoning 输出预留；
   估算、真实 provider body、成本和纠错使用同一有效上限。Judge 保持原配置。

## 尚未证明的部分

以上修复不会自动补足事件类证据，也不证明模型能正确解释 reflection。
下一轮必须审阅真实候选相关性、逐项需求路由、资料可得性、实现一致性、
held-out 效果和跨环节反馈。不能用非零 JSON 输出或本地测试数代替三层验收。

补充：V83 在 2837334 冻结但未外呼。启动前检查还发现历史市场确认措辞被
同一类规则误拦。现把检测限定为明确的未来结果窗口/固定目标替换，并将
时间语义与需求路由一并纳入首轮纠错清单。83 项 adapter 测试通过，含历史
价格测量、真实未来结果拒绝及多问题一次纠错；必须使用新冻结工作区。


## V84 真实验证结果与下一轮边界

V84 使用 5264747，合同
`527f209533c00b8aca76013958bd71676d8b34fdb78c83ed469576fff4b720ce`，
已提交 Fast/Slow 0/1，标准 CLI 正常退出。最终有效 Mining 0、Update 候选 3、
验证通过与晋升 0。`cash_reserves:v2`、`max_drawdown_1y:v2` 因方向性效果变差
被拒；`gross_margin_change:v2` 因候选可用数 2/4 暂缓。

实际 wire 已包含统一目标、fixed prior、high reasoning 与输出预留；H1 收到
30 条 Fast actions、24 个独立来源及本轮 reflection 的 NEUTRAL coverage lesson。
这证明信息到达，不证明模型正确利用：reflection 仍出现把 available=4/4
描述成候选 available 更少的错误。

继续发现的链路问题：

- H1 初次三轮输出被 post-cutoff 正则误拦，命中均在 falsifier 中描述
  “若资料只能在预测后获得则假设不可测”的条件，并非请求未来资料。
  隔离关闭此单项规则，原响应可通过其余解析；生产未绕过该检查。
  应按 measurement/retrieval/falsifier 字段职责审查，不能继续堆短语例外。
- 一次 SSL EOF 后标准 CLI 恢复；资料类型增加 historical_price 改变了 H1
  输入，因此重新生成有依据。最终 H1 三个假设中现金 runway、订单/backlog
  进入 H3，但可见证据不足，诚实返回 inconclusive。现金类关键词排序仍会
  让现金流杂项占据现金余额和必要相邻期间的位置，需要组件级覆盖审查。
- E2 请求 `70f6ddaa48a4fc2264a4a523aea2a7671e2f1161604080f3a57dd4f9fbc520aa`
  提出 `operating_cash_flow_state:v1`，暂存后样例失败，不计有效 Mining。
  本地重放确认 `minimum_observations=1` 触发 observations=0/1；其财务事实
  是单个对象，而 resolver 该计数识别明确结构化序列。LLM skill 尚未执行。
  候选字段 schema 没有解释该执行前提；不可通过放宽覆盖门槛强行验收。
- 同一候选把负经营现金流与正样本关联，却把负现金流输出成 negative。
  当前效果评估将 positive 对正样本、negative 对控制样本计为正确。
  数值正负与 Signal 方向的合同没有在生成端明确区分。此为语义风险，
  不是本次样例拒绝的直接原因；不能手工反转候选或更改门槛冒充自进化。

因此本轮仍不满足三层验收。下一轮应共同处理字段语义、校验字段职责及
证据组件选择，再冻结新工作区；不得覆盖 V84 或把非零暂存当作成功。


## V86 反思输入预算审计

V86 的真实 slow_memory model_view_manifest 将 mining-exploration 与
mining-hypothesis 标记为 whole_entry_budget；对应 V84 轨迹约 70 KB/86 KB，
大于 64 KB 总预算。E2 候选及理由实际位于约 6.5 KB 的 E2 子阶段，但整条
探索轨迹是唯一可读取单位，故反思只看到失败汇总，未看到该候选实现。
V86 已在反思完成后 SIGINT 停止，exit 130，完成指针仍 0。

修复按完整 H1 hypothesis、H3/E2 decision 暴露独立 source unit，保留原始
JSON locator 和源文件 hash；大轨迹仍可查询，不截断，不改变字节和条数预算。
本地重放 V84 原始 validation：61244 bytes、12 项含完整 E2 候选、两条 H3、
三条 H1 及效果记录。此为输入可达性证明，尚非真实模型吸收或晋升证明。


## V87 实际运行与验证反证

合同 `d2dbf34fa6ea0aa15de6edb985881385330a7734a35b1617d09d5889a13bb1ad`，
代码 8731315，已提交 Fast/Slow 0/1、exit 0。Mining 1、Update 0、晋升 0。
实际反思请求 `34ecc94ddfbacd80ef6240e4f4c2d9bc59bdccbf5d58512a81cb08a4b29d094b`
含完整 E2/H3/H1 决策；新增 Mining 反思约束进入 H1 请求
`858c61ed518778ec4a0795d70bbce707e67cd61d67f43eb2d3156fc69b74fe35`。

E2 请求 `5af023ec2cdc2a1716a51a1cc96bdaeee760a75ec7e93ea275257900eb29d1e4`
提出 operating_cash_flow_deficit_state:v1：负 CFO→positive，正 CFO→negative，
零→neutral，缺失→unavailable；移除错误 minimum_observations=1，四种实际
LLM 样例均执行。隐藏验证记录为 available=3、correct=0、wrong=3、failed=1，
所以未验证通过。不得把此计数直接解释成该测量完全不泛化：

- cik_0001849056:20250731：原始最新 CFO 为 -12,243,000，2025 Q1，
  2025-05-13 filed。请求前缀 39f4adc5822f 的可见片段没有该值；LLM 把
  +6,064,000 判断为 CFO。完整原始事实证明 +6,064,000 属于
  NetCashProvidedByUsedInInvestingActivities，同为 2025 Q1。片段在此记录后
  才进入 NetCashProvidedByUsedInOperatingActivities，概念归属跨块丢失。
- cik_0001530950:20250930：最新 CFO 为 +697,000,000，2024-10-01 至
  2025-06-30，2025-08-08 filed。请求前缀 9bfe8c560ed5 中该值可见，
  但 LLM 选择 FY2024 的 -677,500,000。不能简单归因于完全未传数据；
  期间与概念上下文不足以让执行正确选择最新记录。
- cik_0001674440:20250131：最新 CFO +2,726，2024-05-01 至 2024-10-31，
  执行所选记录与完整源数据一致。
- cik_0001117297:20250930：最新 CFO +55,083,000，2024-07-01 至
  2025-03-31。执行选旧 FY2024 的 +12,039,000，并因引用触及内部投影边缘
  被拒；错误码 signal_output_validation_exhausted。

共同实现入口 `_shared_llm_signal_projection` 对财务 JSON 按字符分块和
关键词排序，没有保留概念、单位和完整记录之间的结构。下一步修复此共同
路径并在原失败输入上做隔离真实重放，再进行新冻结周期；不得改写 V87 的
原始结果或手工晋升候选。

三项 Update 都诚实 defer：最大回撤缺完整计算证据；现金储备、毛利率的
可见调参方向与固定样例/已对齐案例冲突。最大回撤与动量共用的数值证据
默认仅引用原文前 240 字符，无法提供相应峰谷或首末价格依据，需一并审查。


## V88 修复准备：共同证据链路

复用 SEC 结构化记录选择器，软 Signal 不再用字符切片处理受支持的
Company Facts。每条完整原文记录附科目、单位、latest/comparable_prior；
科目源名称用 concept_description，避免混入禁用的结果 label 字段。
原始跨度、预算、引用作用域和未来 filed 过滤仍有效。行情计算新增实际
峰谷及窗口端点原始记录引用，并核实调整价格与 metadata.prices 一致。

V87 四个原输入本地重放的最新 CFO 依次为 -12,243,000、697,000,000、
2,726、55,083,000，完整引用全部能映射回原始文档。证据保存在
/tmp/slow-v88-projection-audit.json。全部 781 测试通过，
日志 /tmp/slow-v88-full-tests-final.log。此时只证明本地投影/计算修复，
真实模型重放和新冻结周期尚待执行，不修改 V87 结果或晋升状态。


## V88 收尾与 V89 已授权修复

V88（冻结 d94c366，合约 6bf795b154dfc355acd1085c7ac316eb36e5a6499fe6b47d1f8d02df4e3cbd57）
提交 Fast/Slow 0/1，Mining/Update/晋升均为 0；仍未达到目标。

- 四个 V87 财务执行的隔离 DeepSeek 重放全部成功，选择正确最新科目、期间及
  数值。请求与结果已保存在 V88 diagnostics/v87-execution-replay，原周期不重写。
- H1 请求 211988395c8e3bd1680bd92b2f14f277734db3901e2afd32e4afc0726690570c
  的 wire body 哈希一致且含新反思，但仍复制三项旧测量；需要五日股价分母的
  第一项未申请行情来源。H3 再次判两个假设 inconclusive。信息到达不等于采用。
- E1 原始响应中，强制财务双期占位的纠正挤掉了股份十年锁定及轻资产模式等
  业务叙述。四批均触发占位纠正，一批还因真正的非原文引用进入隔离恢复。
  E2 请求 4b1cdbff3eb61d3a416261b08a0063e2965b682f960ba1533fc144915106863c
  给出 no_measurable_pattern：当前签名的现金流正负两组交叉，其余事件未形成
  重复对比。不能为达成非零而强制候选。
- Update 本轮已实际执行 guidance_acceleration:v1，说明 H1 的更新路由能改变
  目标；不能把“永远同三项”说成本轮事实。期间遇到 SSLError record layer failure，
  未被 UrllibTransport 归一化，因而被外层记成普通阶段失败并提交周期。这个
  provider/control-flow 分类漏洞需修复，不将退出码 0 当成无错误完成。

用户于本轮明确选择取消 E1 共有财务科目的强制占位，按暴涨研究目标选择观察；
选用财务比较时继续严格校验科目和期间。V89 同步移除提示词、验证、纠正与
控制器替换恢复中的旧规则，保留真实原文检查、有效观察、6 条上限和 E2
源科目/单位/可比期间伴随记录。H1 增加将反思转为完整输入检索、优先未测
延期假设及说明重试依据的要求；TLS/连接/read 错误回归既有 provider 暂停路径。

V88 四份 E1 初始响应本地回放：三批一次接受，第四批仅隔离一条真实非原文
观察；不再因未选财务科目而制造纠正或替换业务证据。相关 93 测试及全套
781 测试通过（/tmp/slow-v89-focused-tests.log、/tmp/slow-v89-full-tests.log）。
新提示词是否改善真实候选方向、以及正式 Mining/Update 有效结果，仍待新冻结周期。


## V89 执行结果（2026-09-16 授权重放）

V89（合约 d38aa3b7...ab4bda，代码 400e352）从 2026-09-13 的 H1 暂停点恢复，
两个 slow cycle 全部提交，进程退出码 0；共 166 次 DeepSeek 尝试、$1.1365、
200 次数据请求。完整运行日志 reports/cold_start/v89-resume-run.log。

三层验收结果：

1. 无报错跑通：达成。全部 stage 完成；一次 9/13 的 H1 OpenAIClientError 为
   瞬时错误（本次同请求重传成功），一次 exploration discover 可重试暂停由
   wrapper 自动恢复；无阶段失败、无错误提交。
2. 信息链路：达成。cycle-2 reflection 实际消费 cycle-1 的 result/validation/
   effectiveness/mining decision 单元（slow:1:* 12 条 -> 12 episodes/4 lessons）；
   H1 在新指令下输出显式 retrieval_plan（如 backlog/RPO 检索意图与来源类型），
   假设排序相对 cycle-1 改变；Update 目标在 cycle-2 出现新 customer_concentration:v2。
   证据面实际扩展：financial_statements 36、price_daily 59、news 2、transcripts 1。
3. 非零结果：部分达成。Update 两轮各 3 个候选并全部真实配对评估
   （cycle1: cash_reserves/guidance_acceleration/max_drawdown_1y；cycle2 含
   customer_concentration），均被诚实处决性/fixture 门槛拒绝；Mining 仍为 0。

Mining 归零的本轮定性（E2 contrast 逐案陈述）：E1 窗口是 8-K/10-Q 定性披露，
而 H1 假设要求量化分子/分母（分析师目标价或指引隐含价、季度经营现金流出、
六个月内可转化 backlog/RPO 值），E2 诚实地判 inconclusive 而非编造。这是
假设-证据匹配错位与 PIT 窗口数据可得性问题，不是管线故障；下一步杠杆在
H1 将 observable 约束到窗口内可测量的证据族，或先扩展分析师预期/新闻证据
覆盖，而不是继续修补提示词。

本轮代码修复：外部调用失败的异常消息此前只保留类名（本次 9/13 H1 暂停
无法从工件诊断的直接原因），现在 ledger 与 external_call_failed 事件都持久
化截断到 500 字符的 error_message；新增回归测试，全套 782 测试通过。


## V90 执行结果（2026-09-17，Phase 0b of v2.1）

V90（合约 3eb83e50...74fe，代码 10e57d5，slow-history 导入 V89 的两个已提交
周期与 Registry v2）冻结并执行授权 live run；在 Alpha Vantage 数据配额上
安全暂停：57 次尝试、$0.4964、authoritative 指针 0/0、零周期提交。
完整日志 reports/cold_start/v90-run.log。

已确认的 Phase 0b 核心证据（来自缓存的 H1 请求/响应）：

- `measurable_evidence_manifest` 完整进入 H1 wire payload；
- H1 三个假设为 cash_runway_months_from_operating_burn、
  quantified_project_development_bridge_specificity、
  operating_income_growth_minus_revenue_growth——全部锚定结构化来源
  （company_facts/financials/10-k/10-q），检索意图均为清单内证据族；
  不再有 V88/V89 的分析师目标价、backlog/RPO 等窗口外 observable。
  "告知可测证据族 → 假设锚定结构化概念" 的因果链在 live 上成立，
  该 manifest 同时是新挖矿控制器 Seed A 的输入件。

暂停原因（非设计失败）：case-005 证据获取阶段 Alpha Vantage 返回
Information 信封（per_minute_limit 与 alpha_vantage_information_error，
后者措辞不在既有 quota 标记表内），归类 provider_error →
slow_loop_data_unavailable，wrapper 24 次自动恢复未清（约 1.5 小时，
判断为当日配额/端点限制）。LLM 侧仅 2 次 SSL 瞬断且均按可重试暂停恢复，
新增的 error_message 持久化首次在 live 中提供了可诊断的失败明细。

处置：停止 wrapper；V90 保持不可变诊断工作区（57 次尝试与全部缓存响应
可回放）。注意其合约绑定代码 10e57d5——在 HEAD 前进后 V90 不可再 resume，
如需完成两周期验收应在配额窗口重开时从 V89 重新冻结 V91。
下一个已知缺口：alpha_vantage_information_error 的信封原文未入账本
（只存分类后的 reason），quota 标记表需要一次泛化复核。


## Phase 3 零调用历史回放（2026-09-17，v2.1）

新增 mining_replay.py 与 scripts/run_mining_replay.py：从冻结工作区的
trajectory/cache 按时间序取最终 H1 假设，在本地 4.9GB oracle 上零调用
确定性重放，按操作化定义测量信息到达率——每个假设的声明输入 =
retrieval_intent 的来源族 + 测量文本点名的结构化概念；族输入按"窗口内
存在该族文档的 cohort 案例比例"计，概念输入按"存在 latest+comparable
记录对的比例"计；头条指标为全部输入覆盖率均值。报告存
reports/cold_start/mining-replay-2026-09-17.json（V87/V89）与
mining-replay-v90-2026-09-17.json（V90）。

实测（cohort=32，概念目录 124–158 个可投影结构化概念）：

- V87 cycle1：0.2135 / 0.4271 / 0.2135（最高为现金跑道假设——正是当轮
  唯一产出可执行候选的方向）；
- V89 cycle2：0.2211 / 0.2585 / 0.2370；
- V90（manifest 锚定后）：0.25 / 0.4609 / 0.2634——最佳假设到达率较
  V89 同位提升 0.26→0.46，且三个假设全部锚定结构化来源。

结论：到达率指标把"假设要求窗口外输入"与"证据基底缺内容"分开了——
目录显示 158 个概念可投影，而旧假设的声明输入仅约四分之一可到达；
manifest 修复方向正确但不足以单独达标，Seed A 的"工具执行后确认证据
readiness"准入（Phase 2 已实现）是必要的第二道门。

回放不变量核验（每工作区，真实别名/真实文档）：证据逐字可回溯到
content_hash 文档、PIT 成立、账本 action_id 连续 append-only、模型视图
零身份泄漏（32 案例公司名/别名扫描）——全部通过；回放控制器终端
evidence_unavailable、零越界工具调用。

顺带修复一个已记录泛化缺口：Alpha Vantage Information/Note/Error 信封
原文（脱敏、折叠空白、截断 200 字符）现随分类 reason 一起持久化
（alpha_vantage.py `_alpha_vantage_error_excerpt`），下次配额事件可
直接核对 quota 标记表；新增/更新 3 项测试，全套 803 测试与 lint 通过。


## Phase 5 live shadow cycle（2026-09-17，v2.1）

V91（合约 b1de1de4...9dadb，代码 5c70b79，slow-history 导入 V89）完成一个
已提交生产周期 + 一次成功的 live 控制器影子运行。生产 134 次尝试/$1.3611
（上限 200/$5，fail-closed 未越限），cycle 2 在重复 SSL 重放推高预留后于
配对门阶段安全暂停（保留可恢复，恢复需 /tmp/v91-frozen worktree 的 5c70b79）。

**生产轨 cycle 1（旧 H/E 链路 + manifest）**：Mining=1
（operating_cash_flow_sign:v1，V87 以来首个新挖掘候选），Update=1
（guidance_acceleration:v2，因可用 2/4、decisive 0/2 保持 provisional）。
挖掘候选被配对门诚实拒绝（无正向方向证据、可用 2/4 低于配对最小值）。
用户三层目标的第 3 层（挖掘、更新均非零）首次在生产环境达成。

**影子轨（LabelAwareMiningController + Evidence Graph，seed A）**：
17 次模型调用/$0.3491/重动作 13/16，终态 candidate——1 个候选
（measurement 完整、引用全部落在账本内）、142 条 need-dispositions
全部合规。四项不变量通过：证据逐字回溯、PIT、账本 append-only、
真实公司名/ticker 的视图零泄漏；标签仅经 runtime-owned label_map。

八项切换条件核验：
1. 证据接地率：控制器强制候选引用 ⊆ 账本；fetch 记录 1000+ 带
   content_hash 的 ref；逐字包含校验全过 —— ✓
2. 零标签/身份泄漏：17 个视图 × 真实别名扫描零命中 —— ✓
3. no-pattern 覆盖可审计：合同强制引用账本内 explored families
   （早期诊断运行的 deferred_budget/evidence_unavailable 终态留有完整
   覆盖记录）—— ✓
4. 失败分类正确：影子账本中 invalid 动作全部记为技术问题；生产挖掘
   拒绝理由显式（方向+可用性）—— ✓
5. 受控候选过 fixture：Phase 4 四个 promote 场景 —— ✓
6. holdout/配对门生效：生产 operating_cash_flow_sign:v1 与
   guidance_acceleration:v2 均被门评估并按理由处置 —— ✓
7. 成本/步数不越限：生产 134/200、$1.3611/$5，超额前 fail-closed 暂停；
   影子自有台账 17 调用/$0.3491 —— ✓
8. Update/既有信号执行无回归：Update 非零且配对评估完整，
   llm_signal_batch_execute 全部完成 —— ✓

影子调试过程中修复的泛化缺陷（均有测试）：value_kind 拒绝消息精确化
（ratio→numeric 指引）、纠正反馈进视图（last_invalid_action）、
fetch 族词汇表 runtime 计算并强制（available_source_families，防自造
族名空转）、fetch 构建的 relation refs 入账本（视图/账本一致性）、
need-dispositions 聚合纠正前沿（一次报全部问题）、纠正额度 2→3、
shadow 脚本传输重试与独立台账目录。

结论：八项条件全部满足，影子轨与生产轨在同一冻结输入上各自完成
诚实终态。按方案 Phase 6 纪律（"不要在 shadow 只有一轮时删除旧路径"），
生产切换仍需至少一轮额外 shadow 周期后执行；本轮记录为切换验收的
第一份完整证据。

## Phase 5 追加：影子轨语义审计与两轮泛化修复（2026-09-17 下午）

对 shadow6（Seed A）与 shadow7（Seed B，首次 discovery live）逐请求审计
prompt/view/response/账本，发现六个泛化缺陷并全部修复（代码
450e05e→347379c→d35bdd9，spec 同步，全套 821 测试 + lint 通过）：

1. **视图无工具结果反馈**：视图只含不透明 ref 列表，模型看不到 fetch 是否
   生效——Seed A 连发 12 次宽泛 fetch（17 调用/$0.349），Seed B 连发 10 次。
   修复：视图新增 runtime 拥有的 `evidence_digest`（族/概念×正反例覆盖）与
   `last_action_result`。效果：Seed A 3–4 次调用即终态 candidate
   （$0.04–0.10），且模型明确以 digest 决定"不再重复 fetch/只补未覆盖族"。
2. **预算耗尽死亡螺旋**：heavy 预算耗尽后模型的重动作请求被当作模型违约
   消耗纠正额度，Seed B 三次后 technical_failure。修复：预算耗尽是
   runtime 状态条件——保留一次切换机会后确定性终态 `deferred_budget`
   （方案 §8 可接受零结果），不再伪装成技术失败。
3. **候选与 catalog 重复未拦**：Seed A 候选 observable 直接写成既有
   `cash_reserves:v1`。修复：propose 拒绝复用稳定 catalog 任何 Signal
   基名（改既有 Signal 属 Update 路径）。
4. **处置纠正文案反向**：`new_measurement` 误带 signal_refs 时报
   "cites no signal"，语义相反，把 142 条处置压成全量 not_testable。
   修复：文案陈述真实规则（仅 update_existing 引用一个 signal）。
   效果：r3 处置分化为 8 行 5 类（含 4 条 update_existing 带引用）。
5. **证据引用语义不接地**：两个 seed 的候选引用都是账本合法但与测量无关
   的 fact（期权/估值/库存 vs 净负债权益；零 R&D vs R&D 强度），模型在
   rationale 中明说"需要 concept→fact_ref 映射但视图不提供"。修复：
   compare_groups 结果附带每个值背后的 fact_ref；propose 校验
   normalization 点名的已知概念必须各有一条同概念引用。效果：r3 两候选
   引用 100% 匹配测量概念（现金跑道=现金+经营现金流 latest 多 case；
   流动比率 YoY=AssetsCurrent/LiabilitiesCurrent 的 latest+prior 配对）。
6. **raw info 层叙事投影缺陷**：historical_price JSON 行情与供应商信封被
   投影成"叙事事件"，filing 事件 excerpt 是 SEC SGML/HTML 样板头。
   修复：叙事事件仅从 filing/transcript/news 族投影（族映射仍是唯一
   权威），excerpt 复用生产可见文本投影与实质内容锚点。

r2/r3 影子（shadow10–13）四轮全部终态 candidate、四项不变量通过，成本
$0.023–0.104/轮。candidates：net_debt_to_equity（r2，后被#5 修复暴露引用
缺陷）、company_news 合同/订单事件计数（r2）、
liquidity_runway_from_operating_burn（r3）、current_ratio_yoy_change（r3）。

**账本结算缺陷（生产阻断根因）**：`ExternalAttemptLedger.reserve` 的
committed cost 永久按 reserved 而非 settled 累计——V91 cycle 2 因 SSL 重放
在 reserved $4.94 vs actual $1.36 时 fail-closed 且不可恢复。修复：finalized
按 actual_cost、in-flight 按全量预留（保守性保留）。V92 从 V91 提交前缀
重新冻结（合约 0f5bc8e6...a961be，代码 450e05e）执行两周期；其 cycle 1
reflection 的 wire 载荷经核验确实包含 V91 提交的
operating_cash_flow_sign:v1、guidance_acceleration:v2 与 slow_loop_result
（跨工作区反思→行为信息流成立；V91 内部 c1→c2 的消费此前已验证）。

**V92 生产结果（补记）**：两周期全部提交，153 attempts/$1.2732（上限
200/$5，151 completed/2 failed 均自动恢复）。cycle 1：Mining=1
（operating_income_sign:v1）+ Update=2（guidance_acceleration:v2、
max_drawdown_1y:v2）；cycle 2：Mining=1（operating_loss_presence:v1，
新方向）+ Update=1。配对门拒绝理由显式：guidance_acceleration:v2 保持
provisional（available 1/4 低于配对最小值、decisive 0/2）；
operating_loss_presence:v1 拒绝（4/4 可用但方向 2 正 2 误、无正向证据）。
cycle 2 中途传输瞬断按同合约自动恢复且 request_cache_hit 证明已完成动作
未重复计费——结算修复在同一失败模式下（V91 cycle 2 死因）live 验证通过。
cycle 2 初次启动因周期间 HEAD 前进被 code-revision 检查拒绝，从
/tmp/v92-frozen worktree（450e05e）补跑；该 worktree 保留为 V92 的恢复
锚点。用户三层"跑通"验收：无报错执行 ✓（两 seed 影子 + 生产两周期均
clean exit）；信息链路 ✓（reflection wire 级消费前序结果，digest 驱动
模型行为改变）；挖掘/更新非零 ✓（影子每轮 candidate + 生产两周期
Mining/Update 均非零，拒绝均显式合理）。

## 晋升门协议修订：分级准入 + 扩大 check 队列 + 暴露账本（2026-09-17，用户决策）

用户评估配对门后决策（三层）并已实施（825 测试 + lint 通过，spec 同步）：

**统计依据**（精确二项）：单周期多数门 n=16 时噪声通过率 0.40、55% 信号
0.56、60% 信号 0.72；一次性认证（α=0.05/功效 0.8）55% 需 n≈616、60% 需
n≈152——单周期永远到不了，区分度只能来自跨周期累计（pooled 48：噪声
0.44 / 55% 0.71 / 60% 0.90；pooled 80：0.46 / 0.79 / 0.96）。

1. **分级准入（A）**：新信号方向平局（通过全部正确性/可用性/decisiveness
   门后 correct≤wrong）不再终审拒绝，改为 provisional 居留者；每周期
   runtime 在当期全新 check 队列复评居留者并对其 pooled 记录应用三区制：
   转正（decisive≥12 且单侧二项 p≤0.10）/淘汰（累计 5 期后 pooled
   correct<wrong 或 decisive<4）/继续跟踪；并存居留者上限 2（满员时新
   平局显式拒绝）。更新类候选保持硬门（在位者存在，不胜出即拒）。
2. **check 队列扩容（B）**：validation_cases_per_class 2→8、effectiveness
   case_limit 8→16（dev:check=32:16=2:1）；生产 population 8755
   （565 surge/2096 issuer）按每周期 8 正例耗 check 可支撑 ~70 周期。
   后继冻结建议 data caps 200→400/cycle、400→800/run（V92 实测 ~238/周期）。
3. **暴露账本（C）**：`previously_exposed` 由硬编码空表改为汇集本地
   committed + 导入历史全部周期的 dev∪check case id，抽样前剔除——修复
   实测缺陷（V92 cycle 2 的 check 含 1 个 V91 已暴露 case；每周期 permute
   重划分本已存在但重抽≠安全，check 必须单向只用未暴露 case）。

**修订补记（同日，用户澄清后重设计）**：用户澄清 permute 语义——每轮 slow
round 是全新开始，完全重新 permute 并划分挖掘/测试集，上轮 check case 本轮
可以进挖掘集。重分析确认该模型正确且优于全局单向排除：(1) 候选评估的诚实
性由周内 dev/check 不相交保证（候选只从当轮 dev 生成、spec 提案即冻结，
后续轮次不会重新拟合）；(2) 唯一需要的跨轮保护是按候选的——候选 C 永不
评估于其提案轮 dev 集（`generation_case_ids` 随首个评估记录固化并跨记录
透传）∪ 其已评估过的 case（防止 pooled 二项统计伪重复）；(3) 全局单向
排除会单向耗尽正例池（~70 周期）且与"每轮全新开始"语义冲突。已回退全局
排除 wiring，把排除下沉到 effectiveness gate 的 `excluded_case_ids`
（主循环与居留者复访均接入）；经 reflection 掩码文本的残余标签扩散为
已接受残余风险，由 provisional 淘汰规则兜底。826 测试 + lint 通过。

## 配对门第二道底线：正类 recall（2026-09-17，用户决策"两道底线"）

用户问 correct>wrong 是否应换 F1。分析结论：F1 方向正确（下游主指标本就是
binary_f1；准确率把 FP/FN 对称对待并给廉价的 TN 记全功），但完整 F1 门有
出手率漂移的基线校准问题，且不解决小样本功效。已证实当前门的真实弱点是
奖励怯懦：8+8 cohort 上只在 1 个正例 + 7 个控制股出手且全对的信号 decisive
8 / correct 8 / wrong 0 → 旧门直接晋升，但 recall=1/8。实施"两道底线"：

- 有效性记录新增 candidate/current_confusion（TP/FP/FN/TN，按正类键控、
  仅计 available case，POSITIVE 调用在正例=TP/控制=FP，available 未给
  POSITIVE 调用=正例 FN/控制 TN）；
- 新增正类 recall 底线（TP/(TP+FN) ≥ 0.5）："别漏抓"，与方向底线
  （"别乱报"）并列；新信号仅因这两道方向性底线失败 → provisional 分级，
  更新类两道都保持硬门；
- pooled 三区制同步：转正需二项显著性 ∧ pooled recall ≥ 底线；累计满
  5 期 recall 仍低于底线（TN-farming）或处于随机水平 → 淘汰；
- measurement contract 增加 confusion/recall 定义供模型视图使用。

回归：怯懦信号（注入 deterministic 函数在正例上 NEUTRAL、控制股上
NEGATIVE，证据逐字引用）→ provisional + "positive-label check cases
unflagged"；pooled 各区含 recall 变体。827 测试 + lint 通过。

## 信号选择坍缩审计（2026-09-17，用户关注项）

量化证据（V89×2 + V91×1 + V92×2 共 5 个已提交周期）：14 个稳定信号中仅 4
个曾被选为 Update 目标——guidance_acceleration ×4、max_drawdown_1y ×3、
cash_reserves ×1、customer_concentration ×1；10 个信号从未被碰。

根因分层：
1. **呈现不是问题**：E2/H-track 的 stable_signal_cards 携带完整 learned
   profile（directional/attribution/recurring_contexts/selection_events），
   信号间差异化充分；llm_signal_batch_execute 按给定 refs 执行、无选择权。
2. **坍缩在确定性预选**：`_select_signal_update_targets` 只把"有问题"的
   信号（misleading≥2 / wrong≥2 / unavailable 型）排进每周期 3 个名额——
   12/14 信号其实合格，但 (a) 无轮换：反复失败的信号问题计数只增不减、
   永远霸榜；(b) vNext 被评估又产生新观测→自增强；(c) H1 建议 +1000
   跳队（guidance_acceleration 连续 4 周期被建议）；(d) 同分按 ref 字符
   序稳定 → 前 2-3 名跨周期固定。
3. 修复（已实现、待 V93 完成后提交，V94+ 生效）：目标排序加入近期轮换
   惩罚（近 2 个已提交周期内每被作为目标一次 -600，足以穿透 +1000 建议
   加权的重复垄断），并在目标审计中记录 worked_recent_cycles。
4. Fast 轮 Predictor 的信号路由是另一个 LLM 消费端，slow_only 模式下未
   运行，待 Fast 恢复时单独审计。

## V93 诊断：oracle 重放冲突被洗成 provider_error（2026-09-17）

V93（合约 86170046，代码 9ac19c8）cycle 1 在 H1 后确定性死循环暂停
（slow_loop_data_unavailable/provider_error/case-001，13+ 次自动恢复无效）。
逐层复现定位：传输层 curl 正常、adapter 单独成功、resolver 层 5/5 失败；
最终抓到真实异常——`RawInfoStore.append` 对
`sec_edgar:...:sec_company_facts_raw_response:<digest>` 抛
"document_id already exists with different content or provenance"。
链条：首次 companyfacts 抓取成功并入 oracle（raw 信封 published_at=检索时刻）
→ 传输暂停恢复后重抓同一 payload（内容字节级相同、digest 相同→同 id，但检索
时刻不同→provenance 不同）→ append 冲突的 ValidationError 被 resolver 的
兜底 except 分类为 provider_error → 引擎按可重试暂停 → 无限循环。
（该兜底分类 laundering 是次级问题，本次未改：修复后此路径不再触发。）

修复：`_resolve_replay` 增加 `idempotent_refetch` 语义——append 路径下
同 id + 同 company + 字节级相同内容 → 幂等返回 False（既有副本保持权威，
append-only 记录不重写）；refresh 路径保持全严格（磁盘篡改检测回归不变）。
同 id 不同内容仍然 fail-closed。原失败请求修复后 resolved。828 测试 + lint。
V93 保持不可变诊断工作区（0 提交周期）；后续以 V94 重冻结执行。

## V95 诊断：传递性导入平方膨胀（2026-09-17）

V95（从 V94 导入）第一个请求即超 DeepSeek 上下文（1.18M tokens）：source-read
选择目录携带 12,092 个 ref（3MB wire）。计数链证据：feedback_rows 按代倍增
（V89 1,399 → V91 2,909 → V92 2,954 → V94 6,017 → V95 12,092，每代 ≈2×）。
根因：**导入把每个已提交周期的 slow_input.feedback_rows 全量拼接，而每周期的
input 本身是前序行的累积超集**——导入 2 个周期就把共享基底数两遍，跨代平方
膨胀；这些行主要是 Fast 轨遗留的 candidate_result/search_result 单元。
两层修复：
1. `_imported_slow_feedback` 只从**最新**已提交周期的 slow_input 投影
   feedback 行（严格超集，无信息损失；旧 input 文件仍哈希校验、供采样
   清单等用途）——V95 目录 12,092→6,075 行；
2. source-read 选择目录有界化：`available_sources` 截取最近 1024 条并以
   `omitted_available_sources` 显式披露省略数（无界目录本身即缺陷）。
遗留：V94 已冻结 input 内部烘焙的 V92 双份（不可变），目录保持 ~6k 行、
选择层有界化后可运行；未来某次重冻结时可用内容哈希再压实。
V95 保持不可变诊断工作区（0 提交周期）。

## 物化纠正回环（2026-09-17，V96 证据驱动）

V96（e1f25ec8/79020b7）两周期 clean exit：cycle 1 提交 1 个控制器候选
（operating_cash_flow_change_to_cash:v1）、cycle 2 提交 2 个
（financial_quarterly_cash_burn:v1、working_capital_ratio:v1）——slugify
生效、双 seed 均终态 candidate、候选全部进入候选区；但三者均死于契约
校验（物化 spec 自相矛盾：测量 XBRL 概念却声明 sec_filing 源类型、
fixtures 不满足自声明的两期覆盖）。修复：
- 物化载荷附带 cited_evidence 摘录（concept/unit/period/逐字 span，
  ≤12 条）——spec/raw_retrieval/fixtures 必须从真实证据出发；
- 物化加 ≤2 次纠正回环：staging 前先过完整契约校验器（fixtures 真实
  执行），拒绝理由全文回喂重试， exhausting 后诚实失败入 failures；
- 候选携带 seed 溯源，induction ids 空回退为全 dev 集。
回归测试覆盖：坏载荷→形状错→语义重复→参数区分→PIT fixture as_of→
staged 全链。V97 为最终入库运行。

## V97 结果：分级准入机制全链 live 验证（2026-09-17）

V97（57e14ada/da0103f，从 V96 导入）两周期 clean exit，136 attempts/$1.02。
cycle 1：控制器双 seed 各出 1 候选（cash_runway_months:v1、
point_in_time_current_ratio:v1），**首次通过契约校验进入配对门**并按分级
准入成为 provisional 居留者（check 执行 availability 0/4 → 不足类理由，
不再终审拒绝）；Update=1（cash_reserves:v2 诚实拒绝 1 对 7 错）。
cycle 2：又 2 个新候选（cash_runway_quarterly_burn:v1、
reports_current_assets_and_liabilities:v1）入册并到达配对门——因居留上限
（2）被显式拒绝（"provisional resident limit (2) reached"）；**居留者复访
首次 live 运行**：两名居留者在当期全新 check 队列上复评并应用 pooled 三区
制（继续跟踪）。V96/V97 合计 5 个控制器新信号候选入册、2 名居留者持续
累计。入库（promotion）仍未达成——最后缺口定性：物化的 raw_retrieval
覆盖要求在真实 check 语料上 unresolved（docs 命中 10 但不满足声明覆盖）
→ domain_unavailable → availability 0。已落修复：物化校验
raw_retrieval.source_types 必须与引用证据的文档族相交（f9ddf8c，经纠正
回环执行）；V98 验证中。

## V98：首个控制器挖掘信号晋升入库，signal_goal_status=met（2026-09-17）

V98（01b1d998/f9ddf8c，从 V97 导入）cycle 1 提交：**cash_to_current_
liabilities_ratio:v1 由生产 LabelAwareMiningController（Seed A，3 次调用）
挖掘、物化（检索族相交约束生效）、通过完整契约校验（fixtures 真实执行），
在 16 个全新 check case 上以 TP=5/FP=0/TN=6/FN=3（precision 100%、
recall 62.5%、方向 11 对 2 错）同时通过方向与正类 recall 两道底线，
立即晋升**——Registry v2→v3，signal_goal_status 首次 "met"（项目史上
首次新信号挖掘入库，且经由新架构全链：控制器→物化→契约校验→分级配对门
→原子晋升）。Update=1（gross_margin_change:v2 诚实拒绝 1 对 3 错）。
48 attempts/$0.55。cycle 2 启动触发"slow_only Registry differs from
frozen committed history"校验失败（周期内晋升后的历史链一致性边界，
V75 时代处理过导入侧同类问题；本周期结果权威完整，列为下一修复项）。

**用户三层目标终态**：1) 跑通——V94/V96/V97/V98 四次生产运行 clean
exit，prompt/view/response 内容与 reflection 信息流（跨工作区+周内）
逐轮 wire 级验证；2) 挖掘+入库——达成（V98 晋升，V96/V97 另有 5 个
候选入册、2 名 provisional 居留者示范累计机制）；3) 选择坍缩——审计
+轮换修复 live 生效。行动方案 v2.1 执行完毕（收尾记录见该文档末节）。

## Seed B 物化失败的定责与修复：零可见 fixture 语料被误判 adapter_missing（2026-09-17）

用户质询"问题是否在我们的代码"。核对 V98 attempts #17/#18/#22 后定责：
**主要是代码缺陷，模型的 fixture 设计反而是对的**。Seed B 的 fixture 4
（unavailable_before_available_at，as_of 早于文档 available_at）测试的
正是 PIT 边界的"证据尚未可见必须弃权"，期望值 unavailable；但 fixture
执行经 store-only resolver 解析，PIT 过滤后零可见文档 → 无 adapter 可试
→ ADAPTER_MISSING → permanent_failed → 被记为"技术执行失败"回喂——
模型据此误改 source_types（sec_filing）→ 再撞检索族校验 → 纠正耗尽、
候选丢失。对照 Seed A（其 unavailable fixtures 全部文档可见、测的是缺
概念轴）恰好绕开该缺陷。这是本会话第三例"边界语义误分类"模式
（V93 重放冲突→provider_error；本例零可见语料→adapter_missing）。

修复：`_execute_fixture` 在执行前判定——封闭合成语料零可见文档时，
expected=unavailable 直接通过（空语料上任何信号都只能弃权，无需执行
或获取）；expected 为其他值则给出明确错误"fixture 提供零可见文档"。
生产解析语义不变（配置了 adapter 却无人服务的请求仍报 adapter_missing）。
回归覆盖两分支；全套测试 + lint 通过。

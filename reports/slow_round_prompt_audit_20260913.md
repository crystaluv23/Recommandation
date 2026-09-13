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

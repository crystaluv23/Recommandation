# 分类含义的执行与消费链修复

本轮针对旧 Predictor 把 categorical positive 解释成“月份数为正”的错误，先修 spec，再实现实际执行声明的传递。已支持执行器→Reflect→最终 Predictor context→保存/重读→Posthoc，以及 Update 的实际结果入口；445 项关联测试通过，独立反例审查支持这些局部连接。**没有新的生产模型回答，旧完整消费者语义仍0/1，F9、实际 critic/Slow 和整体 MVP 均未关闭。** 外部 API、资料 GET、业务标签和 Locked Test 读取均0。

分类含义来自冻结版本的实际 callable 声明及其 consumed 参数，或完整冻结 LLM skill 和参数。它是 control data；声明存在不证明定义完整或语义正确，不提供 issuer evidence、股票方向、数值采用或 typed repair 权限。未声明的意义保持 unknown。`SignalResult`、SignalRound、ResearchState、数值计算、阈值、评分与准入没有变更；runway 文档仅明确原有 equal-threshold positive-first 顺序。

执行器在真正调用前捕获声明，在结果校验成功后绑定 canonical result_hash，并只为同一个实际产出结果对象交付 sidecar。传递按 round/result 对齐，避免按 ref 给另一轮旧记录、clone 或导入结果补写含义。最终匿名化保留原 source_contract_hash，为完整匿名视图重算 contract_hash；spec/result hash 保持原绑定。保存产物缺声明时不查今天的 Registry 回填。完整 skill 不裁剪，进入既有 request/case 预算。

独立审查发现三处初版漏修，原失败均保留：

| 反例 | 原因与修复 |
|---|---|
| 同 ref 的 legacy/live 轮次相互补写 | 初版 core/critic 全局 map 按 ref 聚合。改为精确 round 位置和 result_hash 绑定，正反顺序及不同 live result 复验通过。 |
| Update 声明与实际 override 不同 | 实际 executor 跑 A，packet 却从未调用的 validator 表 B 重建。改为每 case 执行后立即捕获 sidecar，并校验同一 result 对象；缺出处保持无声明。 |
| 匿名文本与原 hash 不匹配 | identity masking 改了 doc/skill/参数文本但未改 view hash，真实 Predictor 输入门拒绝。改为保存源 hash、对匿名视图重算 hash；原反例、保存重读及 tamper 拒绝复验通过。 |

此前检查只核 model-view 字段/提示和单轮局部 helper，没有覆盖 actual override、跨轮传播及匿名后再次校验；也把中间 critic helper 的保真过早当成最终 egress 的保真。本轮改以实际生产与消费边界、同义反例和原失败重验作判断，不以更多通过数替代未闭合链。

当前验证与其边界：

- [最终关联测试](../runs/diagnostics/classification_contract_20261023_v1/final-connected.log)：445/445，兼容 Python、网络 tripwire；含9项新测试及执行/反思/身份/reading/Update/Mining 关联模块。此前243/182等重叠批次不相加。
- [独立终审](../runs/diagnostics/classification_contract_20261023_v1/independent/final-review.json)：14主控+6扩展控通过，另 Update 两捕获案和原匿名反例重验通过。覆盖正 scalar 的三种类别、负 scalar/positive 类别、非默认/相等阈值、unbounded、technical status、48,000字符 skill、override、clone、跨轮、错误绑定和预算入口；这些是离线控制，不是模型回答或研究样本。
- [实际来源输入预演](../runs/diagnostics/classification_contract_20261023_v1/actual-source-preflight/result.json)：reviewed1780 view/v12/已接受 H_init；本轮一次真实 deterministic v3 计算，与旧严格通过结果逐字段相同。完整 bootstrap 相等、1847来源绑定未变、旧 usage111032保留。Reflect 逻辑预留59806、可用79655；Predictor 估算62272/62272/65313。request-ready 后、cache/receive/inbox 前停止，生产回答0。估算不是模型实耗。
- 该预演发生在最后 Update/匿名修复前；[代码差异](../runs/diagnostics/classification_contract_20261023_v1/preflight-code-delta.json)保留三个变化的源文件。它只证明中间代码的实际输入连接，不能冒充最终冻结代码的真实模型遵循，也没有重入旧 stage。
- 初次测试的构造器字段、critic fixture 形状、JSON literal 格式和 positional selection fixture 错误均留原日志。`associated-first-duration-fixture-error.log` 的名称反映当时初猜，实际是非 compact JSON 不满足原 literal matcher；只修 fixture，没有放宽产品证据校验。

独立审查仍发现 **实际 critic/Slow egress 丢声明**：`_plan_critic_trajectory` 保真后，真正的 Critic 又重建精简 trajectories_view，声明未进入其实际原件；`CaseReflectionEvidence` 和 `ReflectionMemoryIndex` 原件也没有该字段。中间 helper/Posthoc 测试通过不能关闭 C05/T10。此处需要 canonical meta 存储决策，已提交[完整声明字段或引用档案方案](classification-context-persistence-proposal-20261023.md)，尚未得到答复，未实施 canonical 扩展。

下一步在获得该决策后补齐真实 source unit/catalog/read_refs/最终请求，并先冻结具体反例、原件、代码和预算，再以 fresh 独立 subagent 检验完整消费。旧原答、旧 financial9 的6pass/1literal失败/2政策unknown、routing0/1及 maturity strict0/1保持；不重入完成阶段、不重置旧目标预算、不从本地测试声称新模型遵循、反馈收益或 MVP 收敛。本轮不启动完整后继、不修改发布版本或业务完成指针。

`.githooks/pre-push` 已通过，随后亲读 `.lint-feedback/pre-push-last.log`：status0 / Lint result PASS；该检查只证明仓库与行政记录一致。

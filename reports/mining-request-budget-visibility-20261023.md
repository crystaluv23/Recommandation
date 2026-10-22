# Mining 请求预算进入实际决策输入

2026-10-23。上一轮是实质进展：显式 SEC 坐标修复、8 个 fresh 原答与两份预算终态，
把下一动作从“继续压提示”改为“核预算到决策输入的连接”。本轮不重入或补答两案。
验收对象是局部输入/计量/控制流连接；新模型规划、完整端点和工程 MVP 仍未通过。
外部 API/GET、新业务标签、check/LockedTest、fresh 作者、候选发布和业务指针变更为0。

## 修复范围

- `MiningAgentRoleModel` 接受运行方明确给定的 single、累计 logical reservation 和
  call 上限。累计范围是该 role instance；不从工具次数、memory、H1 或其他预算
  推断隐含累计额度。未配置时实际完整原生请求与冻结旧实现逐字节、对象及 hash 同。
- 有配置时 actual user payload 增加独立 `request_budget`：明确上限、已消费量、
  本次完整请求成本、消费后余量、可适用的剩余调用数，以及后续请求最低成本。
  最低成本取同一 shared prompt/output allowance 加空 payload，不是未知工具结果的
  成本预测，也不保证下一请求能放行。工具免费不使 LLM 终止/后续决策免费。
- 当前成本和消费后余量是定宽十进制字符串，以避免“成本字段改变自身请求大小”的
  数字位数循环；原生估算复核相同字节成本才可放行。独立数值反例确有普通数字迭代
  的 89↔90 两周期，不能靠多迭代几次掩盖。其他计数保持普通整数。
- 估算和 completion 共用完整普通/typed-patch prompt、module envelope、身份投影和
  output allowance。共享 stage Client 的估算补上同一 envelope。曾拟区分 local 与
  remote HTTP-body 的 transport 分支，但实际 constructor 已禁止这两种注册混用，
  现有有效 local 注册本来就计 message bytes；该推测性改动已撤去，不称缺陷修复。
- 生产 `SignalEvolutionEngine` 构造替代后的 controller role 时，传递原有 Mining/H1
  **单请求**上限；不新设 aggregate/seed/cycle 额度。共享受控 constructor 的可选
  `request_limits` 默认不启用，旧原件/终态不被改写或重新执行。

角色只披露资源事实和原有支持的终止选项；不规定第4步结束、不移除 compute/其他
工具、不授予新研究结论，也不改变候选/准入/PIT/证据/typed repair 权限。

## 独立反例及纠正

独立审查在实现前冻结83绑定和12组义务，核原10个 view/8个已答 payload 都没有
request budget；最终验证绑定精确四份产品源码。以下两项初版错误原件保留：

1. 我误用了既有 `RuntimeBudgetExceeded`，它继承 `ValidationError`，会进入
   Controller 的模型内容纠错。现为小型 `MiningRequestBudgetExhausted`，继承
   `EvolutionControlFlow`；真实 Controller 路径验证零内容纠错、零 invalid ledger、
   请求准备前停止，不生成无模式或研究失败结论。
2. 泛看 `exception.usage` 的类型会把发送前 no-progress 拒绝附带的空 AgentUsage
   也扣为一次请求。原生反例从0误扣到1call/18055；现仅消费真正已答的
   StructuredOutputInvalid/IdentityOutputRejected 或非零 usage 的错误，前置拒绝
   不扣。正常 cache 回放保留原生逻辑预留，不产生新物理作者。

Malformed/nonobject/身份拒绝原答仍计实际逻辑预留；pending、未发送及重复请求
前置拒绝不计。顺序重建只消费已经依次读取的回答，不把磁盘上的未来 prepared
请求先计入早期 payload，从而保持 replay hash 和预算字段一致。

证据：

- [独立审查](../runs/diagnostics/mining_request_budget_20261023_v1/independent/independent-final-review-v2.json)：**17/17 原生控制组**通过，最终收窄 transport 见补充核查。
- [最终范围补充](../runs/diagnostics/mining_request_budget_20261023_v1/independent/final-scope-v1/final-scope-supplement.json)：5/5针对性复验，合法原生完整请求与前述版本相同；transport恢复为原HEAD字节，前述历史审查hash不改写。
- [原初硬停失败](../runs/diagnostics/mining_request_budget_20261023_v1/independent/native-v1/results.json)、[原初误扣失败](../runs/diagnostics/mining_request_budget_20261023_v1/independent/predispatch-v1/predispatch-result.json)保留。
- [最终关联测试](../runs/diagnostics/mining_request_budget_20261023_v1/associated-tests-final.log)：**397通过**，网络 tripwire0，125 tested bindings 前后不变；原先测试记录另留，不覆盖。
- [pre-push lint](../runs/diagnostics/mining_request_budget_20261023_v1/pre-push.log) PASS，已亲读 `.lint-feedback/pre-push-last.log`；meta PASS不代表业务验收。
- [顺序 cache 复验](../runs/diagnostics/mining_request_budget_20261023_v1/independent/sequential-v1/sequential-results.json)：3已答+未来第4prepared，重建 hash/预算同、3物理回执不增。回答明确标注 offline fixture，非fresh LLM。
- [生产构造核查](../runs/diagnostics/mining_request_budget_20261023_v1/independent/production-factory-v1/production-factory-result.json)：实际工厂仅传 single_limit32768，sentinel在执行前停，零业务案例/模型。

其他原生控制覆盖普通/patch grammar、SEC/Unicode 投影、9/10等位数变化、巨大上限
宽度、single/total exact-fit和少1拒绝、call边界、共享 model 跨 seed 的明确范围。
首次独立 source-view 运行遭当前源码漂移而拒绝，保留后做 before/after 绑定重验；
另有脚本 harness 缺 `__file__` 的首错保留。它们不算产品反例或通过。

## 实际来源范围与证据局限

[source-view 重建](../runs/diagnostics/mining_request_budget_20261023_v1/independent/source-views-v2/result.json)
使用上一轮两个固定源、原预算和完整 read receipts；compare→read→read→stop 输入
成本为 **97429/92841**，原上限98304，末次余量875/5463均低于下一请求下界
15234/15238。计数在 input capture 后明确模拟，没有 receive、inbox、cache伪造或
新作者。这证明信息已可表达且固定路径仍可达，**不证明新作者会选择它**。

75个旧stage文件和1791个 source/reference 文件逐 hash 同；原模块 **0/2**、更早
taxonomy **1/2** 及所有旧失败保持。未声称 OS恢复、完整研究恢复、候选实施/准入/
后继精确复用或独立效果。完整匿名和来源 primary-filing 语义仍服从既有限制。

本轮局部关闭请求成本披露、前置硬停和顺序消费错误家族。下一步应把新预算信息用于
预先冻结的能力正控，并连接到真正 Mining 测量/实现链；先核原材料充分性、独立
义务与完整成本，再派 fresh 角色。保留既有失败，不重置两份预算终态，不用一个
更容易的 endpoint 替代 S3–S8，亦不启动完整后继。canonical 分类 A/B 等原决策不变。

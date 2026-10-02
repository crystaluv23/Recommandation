# v168 实际内容审查与隔离修复

对象：`/Users/l/Project/Recommandation/runs/cold_start/minimal_rounds_v168_integrated`，冻结代码 `7e6be2e377bcae719f3611bd55e7117473841396`。本报告是进行中的内容审查，不是完成验收。Fast/Slow 提交指针仍为 0/0，没有新的完整固定 24 案 F1。原 40 案及标签、评分分母保持；四份新增历史行情快照已在 preparation 报告披露，不作 paired gain 主张。

## 已检查的实际链路

读取真实原始请求/缓存响应，并检查已保存 trajectory 中的 prediction、self_reflection、state_deltas 和最终状态。已审阅首份 Plan 前八个案例的 Predictor 及 Posthoc 文本；后续读取了 Ciena、Woodward、Newmont、MP 的相关文本。并非已审查所有案例、所有阶段，更未覆盖尚未产出的 Critic/Round/Slow。

首例 Enbridge 的 Initialize → Retrieval → Signal → Reflect → Predictor → Posthoc：

- Retrieval 首答将 guidance 对 regulatory need 的关系当成回答；实际纠错保留同一 Signal，降为 applicability/context，并保留未解决 need。
- 保存的三轮 state delta 保留先前有效基本证据、两条法规风险、已接受 Signal 引用。程序修复后融资和订单原文仍可见，随后增加确定性 revenue/operating cash-flow 测量。最终 unresolved needs 没有被假装回答。
- Predictor 实际收到 Basic Info、anchor、compute、Signal、状态演进和最终状态拼装；模型明确区分 180 trading sessions 与六个月预测期。预测 FP 是研究错误，不能以事后标签否定其当时所见来源。
- Posthoc 原答第三条把准确基准算术误写成 binary correct=true；实际 native delta 仅改该条 category/outcome_claim，已保存的 binary false 与 canonical feedback 一致。数学正确和方向错误并存，不能混为一项成功评价。

这些观察证明具体生产路径的行为，不能外推所有内容正确。

## 1. Posthoc 学习动作偷改固定判断边界

真实请求 `52a3ae4f02220214b56282211cf69b943410432c001f0ce94dc164ed652c0ebc`，案例 `cik_0000701818:20250930`。第四条 action 的 brief 要求先有与 doubling threshold 绑定的前瞻催化/预测；detail 把缺少 forward projection 设为 binding evidence gap 并 cap surge judgment。原初始提示已说明机会判断不要求价格证明，但检测只识别 quantified/stated path 等措辞，两字段均漏检。

隔离修复扩展同一个 bounded shared guard，初始合同及反馈明确 threshold-bound projection 与 missing-projection binding cap；新动作 ingestion、保存校验和三个 Plan 指令消费者复用同一函数。源引用、outcome、其他行保持；商业证据要求、可选预测、confidence caveat、否定规则保留。

[真实响应零网络重放](v168-projection-policy-replay-20261002.json)：原 guard 对两字段均 false，新 guard 均 true；生产 `LLMBlindPredictor.reflect` 重建相同 source catalog/snapshot，仅授权第四条 brief/detail。脚本化 native delta 经完整生产 parser 接受，其余所有作者字段与来源逐项相等。没有新 LLM 纠错调用，不能声称新代码 live 合规已验证。语义错误没有唯一程序答案，因此不自动改为某项研究判断。

## 2. 大写法定名称的短品牌漏进盲测请求

Ciena 的实际 Predictor 请求 `9a542facaabecf1e8e7031c787e379c83bdb7750f473f2b3b3e24ced4a75be83` 中有 80 处 Ciena。已知别名是 `CIEN`、`CIENA Corp / CIENA CORP`；变体已派生 CIENA，却因不超过五字母的大写 token 被作为大小写敏感 ticker 而漏掉普通正文大小写。

这是输入匿名边界缺陷，不是模型自行猜测身份。共享 matcher 现在对多 token 正式名称派生的品牌按 prose 大小写不敏感处理；独立 ticker、短 ticker 的 marker 规则和 strict aggregate inventory 保持原策略。所有 case egress、最终上下文 masking、assertion 及 reversible transport 使用共享 matcher；不修改事实存储或原 evidence hash。

[真实上下文零网络投影](v168-brand-masking-replay-20261002.json)：原请求和 canonical final context 均有 80 处，原 matcher 再投影仍为 80，新投影为 0；整个原 payload 可逐字恢复，保存 request/trajectory 未写入。新增 transport 测试检查 estimation/prepared wire/cache/restore 一致，而不是只检查字符串助手。

## 待处理与验收边界

- Woodward 的 fact brief 称 guidance/financing “were sufficient to identify” outcome，自己 limitations 又承认成功不证明原因充分；Newmont 的 fact brief 把“正证据被 underweighted”说成既定校准事实。单一结果不能建立 ex-ante 权重错误；需继续检查 fact/hypothesis 分工及实际下游学习消费。
- 部分 case 的 context_tags 含市场规模标签，但必要路由 context 没有明显市值依据；需对照标签契约和卡片排除规则进一步审查，尚不据 issuer 名称直接宣判标签错误。
- 幅度仍多次选择 2-3x；临床案例实际为 3-10x，Posthoc 正确拆开 binary 成功和 magnitude 失败。这能证明归因轴拆分，不能证明幅度学习已有改进。
- v168 在保存 14 个案例后遇到 Remote end closed connection without response，进程/session exit 1 已核验；按原冻结代码和同一 root 续跑，恢复进程 PID 98495、session 49638。连接故障不成为因子失败或成功反馈。后续运行仍需检查提交与实际缓存/检查点恢复。

所有新修复仅在附属隔离 worktree。主运行代码仍冻结 7e6be2e3；完整新代码 Fast/Slow、固定 24 案 Binary F1≥0.60、逐环节内容与下游消费仍未完成。

## 隔离验证

74 项相关测试通过；补齐 worktree 缺少的本地历史 fixture 后，原生全量 1,388 项全部通过（64.651 秒，无跳过），lint PASS。初次 worktree 全量的缺资产错误与跳过均已重新验证，未通过修改测试或评分分母消除。完整原运行保持原代码，修复只通过本地/离线验证。

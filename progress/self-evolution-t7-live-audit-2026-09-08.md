# T7 真实执行与响应审计

日期：2026-09-08。原运行代码：`a9480cab70958009c6c84f484be2a5cabfcfd762`。
工作区：`runs/cold_start/evolution/self-evolution-t7-20260908-v1`。

## 结论

这次执行没有完成一个 Fast round。权威指针仍为
`state.json:last_completed_round=0`、`cycle_state.json:last_completed_cycle=0`；
Registry 仍是 version 1，Locked Test 未读取。停止原因是 250 次外部模型尝试
耗尽，不是候选通过、Fast 提交或 Slow 完成。

运行安全性符合预期：两个未完成候选只保存为 diagnostic attempt，固定 24
案例 cohort 没有缩水，失败案例没有被当成负例或 unavailable，半成品没有进入
Archive、Signal 学习或提交指针。但现有合同无法证明“自进化已经发生”。

## 实际执行量

- 模型 ledger：250 行，其中 248 completed、1 failed、1 in_progress/不确定；
  actual cost `$0.37523724`，累计 reservation `$1.74480068`。
- 持久化 wire artifacts：253 个 request、248 个 response。
- 数据请求：64 行，37 error、15 quota_deferred、8 fetched、4 cache_hit；
  SEC Edgar 21、Massive 17、Stooq 13、Alpha Vantage 13。
- 完成的案例轨迹：候选 1 为 17/24，候选 2 为 0/24，候选 3 为 11/24。
  候选 1 的 17 个有效结果含 6 个正预测、3 个 true positive，但 cohort 不完整，
  因此没有计算或保存可比较 F1。候选 2 在首案例失败。
- 调用密度：扣除 4 次 Plan proposal 后，244 次 completed/started 尝试只推进
  约 30 个案例起点，实测约 8 次模型尝试/案例。一个 3 候选、24 案例的 Fast
  round 因而约需 600 次尝试；当前 250 上限在设计上无法覆盖一轮。

角色调用也显示 prompt/contract 负荷过高：H_init 为 32 次初始、31 次纠错；
routing 为 52 次初始、27 次纠错；LLM Signal 为 20 次初始、2 次纠错；
H_reflect 为 21 次初始、2 次纠错；Predictor 与 posthoc 各 28 次，posthoc
另有 3 次纠错。H_init 初始请求平均约 30,491 字符、最大 52,760；其纠错请求
平均约 37,515、最大 66,330。LLM Signal 请求平均约 40,814 字符。

## Prompt、context 与 response 内容检查

### H_init 与 Basic Info

首个成功案例的 H_init 输入包含 prediction time 之前的 Basic Info projections
和 runtime-owned evaluation context。模型最初写出 UBS `$27 from $20`，引用却
只支持 `$27`；本地 quantity/逐字证据校验拒绝了 `$20`，纠错后缩成来源实际
支持的 `$27` 并让 quantitative belief 逐字复制 evidence claim。这个路径正确：
模型负责提出研究状态，runtime 决定来源与接受标准。

候选 1 的失败响应
[`f25b6ff6...json`](../runs/cold_start/evolution/self-evolution-t7-20260908-v1/cache/responses/f25b6ff6b7e1bc2cb400fc48e548ab1b52c471625b3cfeee27f0867b2b9051ad.json)
保留了两条简短、可验证的运营/融资证据，却把 10 个交易日的行情 JSON 全段
作为第三条 `exact_text`，长度 1,156。prompt 已明确要求最短连续 literal，
两次纠错仍未缩短，说明继续叠加文字提醒不能成为唯一恢复手段。

候选 2 的失败响应
[`6d1fa230...json`](../runs/cold_start/evolution/self-evolution-t7-20260908-v1/cache/responses/6d1fa230117e5cd1d955173acdda14caa9d78cdc15de694ed6ae85a464ab37ef.json)
把 SEC 原始 `val:-1005900000`、`val:-1189900000` 表述成正数字面金额；“used”
在经济语义上暗示流出，但不满足当前逐字 quantity contract。另一条 operating
cash flow literal 又绑定到不包含该片段的 projection，同时相同片段出现在两个
其他 projections 中。runtime 不能猜应选哪一个，正确行为是隔离该 evidence。

修复后的原样回放使用上述最终响应及其真实 Basic Info payload：

- 候选 1 删除 `supporting_evidence[2]` 与同文 `current_beliefs[2]`，保留另外
  2 条 evidence/belief，完整 parser 和语义校验通过。
- 候选 2 第一层删除 2 条 quantity 不一致 evidence 及其 beliefs；复验暴露
  先前被遮住的 projection grounding 错误，第二层删除该 evidence/belief；
  最终保留 5 条有效 evidence/belief。没有选择两个歧义 projections 中的任何一个。

### Signal routing 与 Signal 执行

首个 routing response 把 `target_need_indices` 返回成标量 `4`；结构纠错仅把它
改成 `[4]`，其余合法 siblings 保持不变。这类 provider/model 格式波动适合
schema 校验、局部 patch 和完整复验，不应靠 issuer/model 专用规则处理。

`financing_listing_action:v1` 的首个真实 Signal 结果引用了 Asante share-sale 的
逐字 span，PIT 和 literal lineage 合格，状态为 neutral/partial。但它对当时的
growth-project need 只提供间接背景，routing relevance 偏弱。它没有被当成直接
答案，未授权删除 residual need；这避免了“检索到内容”等同于“回答了问题”。
unavailable Signal 在最终 context 中使用 unknown/do-not-infer-absent 语义，符合
信息缺失边界。

### Predictor 与语义质量

Predictor 输入使用匿名身份和 runtime 计算的 baseline。一个 Wynn 案例中，模型
给出 `possible/is_surge=true`，但理由同时承认价格离 2x 很远、催化剂缺少里程碑、
现金/贷款不直接支持翻倍；真实标签为 non-surge。这是 schema 合法的语义误判。
固定 cohort 和 F1 应保留并惩罚该 false positive；不能为该公司添加规则。后续
需要在独立评估中衡量这类“有催化剂但缺少幅度桥梁”的系统性频率。

## 通用恢复修复

纠错耗尽后的 ResearchState fallback 现在遵循以下边界：

1. 只接受能机械定位到完整 evidence 行的 literal/quantity grounding 问题，或
   明确的无支持 quantitative assertion。
2. 删除已确认无效的完整 evidence 行；只有在没有同文有效 evidence 留下时，
   才删除 byte-identical belief/contradiction。
3. 不把 SEC/行情原始 JSON 改写成 belief，不修 claim，不猜 projection，不处理
   身份、PIT、来源、shape、预算或授权错误。
4. 每次删除后运行原完整 parser 与所有语义校验；若前层错误遮住后层错误，继续
   在同一 call-free fallback phase 处理。每步必须改变状态，重复状态停止，步数
   不超过拒绝对象的 top-level item 数。
5. 无 evidence 可留时拒绝 fallback。事件记录每一步和所有删除路径，原 request、
   response、usage 与 failure artifacts 保持不可变。

这实现了“有效 siblings 存活、错误不进入结论、失败不改变 cohort”，同时不会
通过宽松 parser 或本地生成事实来制造成功。

## 与当前 agent runtime 实践的对应

当前主流系统的共同方向并不是寻找一个永不出错的固定 prompt：

- OpenAI Agents SDK 使用 typed/strict structured output，把 malformed output
  分类为 `ModelBehaviorError`；它的 invalid-final-output handler 仍会用同一
  output type 验证 fallback。模型重试是显式 opt-in，并区分 network/timeout、
  provider advice、response 是否已开始和 replay safety。参见
  [Agents output types](https://openai.github.io/openai-agents-python/agents/)、
  [running agents](https://openai.github.io/openai-agents-python/running_agents/)、
  [model retry policies](https://openai.github.io/openai-agents-python/models/)。
- OpenAI 的 guardrail/result 设计保留已完成的 guardrail/tool 结果和原始 response，
  让局部拒绝与整条运行失败可分别审计。参见
  [guardrails](https://openai.github.io/openai-agents-python/guardrails/) 和
  [results](https://openai.github.io/openai-agents-python/results/)。
- Anthropic 推荐简单、可组合的 workflow，在标准明确时使用 evaluator-optimizer，
  并强调改进 agent-computer interface 与工具参数，使错误更难发生；其 SWE-bench
  实践花在工具接口上的优化多于总 prompt。参见
  [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)。
- LangGraph 把 checkpoint、幂等重放和 durable execution 作为 runtime 责任；节点
  重跑可能再次执行副作用，所以 side effect 必须有 idempotency key。参见
  [durable state and idempotency](https://langchain-ai.github.io/langgraph/how-tos/state-reducers/)
  和 [persistence](https://langchain-ai.github.io/langgraph/concepts/time-travel/)。
- Google ADK 生态把 prompt/response trace、线上 scorer、离线 batch evaluation 和
  从生产失败建立 golden dataset 放在同一改进闭环。参见
  [ADK observability and evaluation](https://google.github.io/adk-docs/integrations/freeplay/)。

对本项目的含义是采用六层责任，而不是把所有规则塞回 H_init prompt：

1. provider adapter 统一 refusal、missing usage、schema capability、transport error；
2. role contract 只暴露该步必须完成的最小结构；
3. deterministic validator 管 shape、PIT、lineage、数量和跨字段不变量；
4. recovery policy 按错误类别选择 transport retry、受限 correction、item quarantine
   或 fail-closed pause；
5. checkpoint/ledger 管幂等、成本、固定 cohort 和提交；
6. frozen eval 用真实失败集比较 prompt、模型和 runtime 版本。

H_init 的后续设计重点应是把 Basic Info 中的 SEC/价格原始长投影预先切成带稳定
`projection_id` 的原子 literal choices，让模型选择 ref 并写短 claim；证据解析与
研究假设也可拆成两个最小角色。是否拆分必须通过同一冻结失败集比较首次通过率、
最终通过率、语义错误率、成本和端到端 F1，不能因为 prompt 变短就宣布更好。

## 下一次真实合同

原 workspace 绑定旧代码 revision，修复后不能原地恢复或改写历史。新 workspace
应重新冻结。按本次约 8 attempts/case 的实际密度：

- 一个完整 Fast round 的安全上限建议 700 attempts；
- 完成合同中的两轮 Fast 加一次 Slow，建议 1,400 attempts；
- 保留第二 cycle 及下一 Fast 对新 Signal 的实际可见性检查，建议沿用 CLI 原稳定
  上限 2,500 attempts；
- 仍保留已批准的 `$20` hard cost ceiling。按本次 250 attempts 仅花 `$0.3752`
  估算，尝试次数将先于金额成为主要边界，但两者必须独立执行。

新的外部执行需审阅并批准 2,500 attempts 这一提高后的精确边界。可靠性 pilot
仍使用独立的 320 attempts/`$20` 合同，不能与 Fast/Slow 的成本或样本混算。

## 尚未完成

- 没有完成或提交一个新 Fast round。
- 没有运行 Slow Mining/Update、没有 candidate Signal、validation 或 promotion。
- 没有证明下一 Fast 能检索、执行、引用新 Signal。
- 没有运行两 provider reliability pilot。
- 没有生成四臂 benefit confirmation，因此不能声称 gain confirmed。

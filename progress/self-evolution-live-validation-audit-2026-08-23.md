# v6 自进化持续修复与真实上下文审计（2026-08-23）

## 结论

本次不是完整成功。standing-authorized v4-v9 修复链准确用完了累计
`800` 个外部 LLM attempt 上限，因此停止继续外呼：v7 有一个 Plan 完成全部
24 个 case 并提交 Fast round 1，但没有任何 workspace 提交 Slow cycle 1。
权威最好状态是 v7 的 `last_completed_round=1`、
`last_completed_cycle=0`，不是目标要求的 `1/1`。

真实请求审计也确认，流程在“合同和 JSON 形状正确”之外仍有两个会改变学习
含义的问题：

1. provider 仅按 ticker 关联的他公司新闻进入了目标公司的 Basic Info，随后被
   post-hoc、Plan critic 和 Round reflection 当成目标证据逐层放大；
2. durable meta 虽完整保留 original/vertical/horizontal 三层，但旧 model view
   每种 assessment 取第一条 case，可能选择空反思或 validation fallback，把后续
   具体根因挡在 proposer 之外。单一完成 Plan 的 Round reflection 又只是复述
   vertical critic，并不是真正的横向洞见。

上述问题已按 spec-first 修复。另在逐字检查真实 routing payload 时发现完整
document fingerprint/hash 列表被重复发送给模型；模型无法解释这些 hash，且
executed-ref 排除与 fingerprint no-op 已由本地代码负责，因此也已从 model-facing
context 删除。完整 Raw Info、fingerprints、trajectory 和三层 meta 仍在本地持久化。

## 审计方法和证据范围

本报告以 v4-v9 的不可变 workspace 为事实来源，逐项连接：

- `requests/<request_hash>.json` 中实际发送的完整 system/user messages、canonical
  wire body、body bytes 和 output ceiling；
- `cache/responses/<request_hash>.json` 与 `failed_responses/` 中实际 response；
- `attempts.json` 中发送前 reservation、完成/失败状态、provider tokens 和费用；
- 每个 case 的 `experiments/trajectories/`、candidate attempt、prediction artifact；
- v7 的 committed Plan record、24 条 original post-hoc reflection、Plan critic 和
  Round meta；
- `state.json`、`cycle_state.json`、contract、evaluation snapshot、Registry hash 和
  provider request ledger。

因此，“实际看过”只覆盖真的到达 provider 的角色。H1 没有成功发送；H2、H3、
Update 更未到达，不能用代码测试冒充 live context 验证。

## 实跑、预算和权威状态

| workspace | contract hash | attempts | settled cost | interrupted reservation | real fetches | round/cycle |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| v4 | `3df72360...` | 68 | `$0.09646000` | `$0` | 4 | `0/0` |
| v5 | `e8978d22...` | 40 | `$0.05430908` | `$0.01708000` | 3 | `0/0` |
| v6 | `aae27290...` | 56 | `$0.07652680` | `$0.00341992` | 4 | `0/0` |
| v7 | `e8b06bed...` | 342 | `$0.42175924` | `$0` | 4 | `1/0` |
| v8 | `e3d21675...` | 165 | `$0.22199408` | `$0.01194144` | 25 | `0/0` |
| v9 | `1c959ac8...` | 129 | `$0.15969828` | `$0` | 2 | `0/0` |
| **合计** |  | **800** | **`$1.03074748`** | **`$0.03244136`** | **42** | best `1/0` |

保守费用（settled 加未结 reservation）为 `$1.06318884`，远低于 `$20`；终止条件
是 attempts 耗尽。v9 合同的 `max_external_attempts=129` 正好等于修复链剩余额度，
没有通过新 workspace 重置累计预算。

v7 的 `plan_r0001_c02` 完成 24/24 cases，Combined Binary F1
`0.6666666667`，precision `0.8`，recall `0.5714285714`，混淆矩阵为
`TP=8/FP=2/TN=8/FN=6`。另外两个候选分别只完成 4 和 2 个 case，未提交为 Plan。
v7 round 1 合法提交，但 Slow loop 在 H1 发送前的全 alias 本地扫描处暴露性能缺陷；
修复后 v8/v9 又分别暴露 batch identity 合同问题并最终用完剩余 attempt。

所有 v4-v9 contract 均记录 `locked_test_accessed=false`；所有 cycle state 的
initial/current Registry hash 都是
`4011b59acf545b9d9ea664818b47ad0e7a597492220f7fcb761dc8f52e0dfe39`，
没有未经 promotion gate 的 Registry 变化。

## 每个实际角色的完整 context / response 判断

v7 是唯一提交 Fast round 的 workspace，实际发送量如下：proposer 3；initialize
32+1 correction；routing 86+5；LLM Signal batch 35+28；reflect 57+1；finalize
30+1；Predictor 30；post-hoc 30+1；Plan critic 1；Round reflection 1。v8/v9
对相同 Fast 角色提供了额外失败与恢复样本。

| 环节 | 实际 context / response 检查 | 逻辑判断 |
| --- | --- | --- |
| Plan proposer | system 固定四档/2x/六个月语义、source catalog、可改 Plan 字段和 additive meta；v9 correction response 试图重新引入 `P(S=1)` 概率语义，被 fixed-semantics scan 正确拒绝。 | 边界合理；旧概率 Plan 没有重新成为活跃语义。 |
| Basic Info / initialize | user payload 是 request purpose 加最多 32k normalized projection；initialize 只产生当前 projection refs。SEC filing model view 的 HTML tag 为 0。但 v7/v9 的 market projection 仍分别出现 `retrieved_at/source/symbol=16/7/2` 和 `5/3/2` 次；更严重的是 company news 混入他公司正文。 | evidence 引用合同合理；输入相关性和 market chunk 边界有确定性缺陷，已修。 |
| Signal routing | cards 只含当前未执行 ref、category、description、execution type 和非默认 profile；实际 output 无重复，最多 4 个、最多 2 个 LLM Signal，未知 ref 走一次 correction。 | 选择语义合理；但完整 document hash 对模型无用且重复，已删除。 |
| LLM Signal batch | 两个 soft Signal 共用去重后的最多 32k projection；outer versioned ref 与 inner id/version 在 v9 已对齐。每个结果独立做 literal evidence 验证和 unavailable fallback。 | fail-closed 合理；correction 仍很多，主要是非唯一 literal、unavailable 携带 evidence、neutral 无 evidence 等真实语义错误，不能本地猜测修复。 |
| Controller reflect | payload 带完整 current batch、prior state、精确 Signal evidence tuple catalog；response 只能保留旧 refs 或引用当前 batch。 | 组织方式合理，v4/v5 暴露的错误字段/index feedback 已变成可执行 correction。 |
| Controller finalize | 使用独立 finalize schema，强制 `decision=finalize`、空 next needs；只可保留已有 provenance tuple。 | 与终止语义一致，无通用 continue 示例冲突。 |
| H_analyse / Predictor | H_analyse 是 Plan 内的证据组织/权重指令，不是概率计算角色；Predictor 收到固定匿名 compact packet。v7 Predictor user payload 最大 10,035 bytes，v9 最大 13,179 bytes，均低于 24k。 | 固定预测语义和可进化分析边界合理；没有再重复完整 Basic bundle。 |
| post-hoc | truth reveal 后收到 final state、结构化 refs、Signal 摘要、Basic source index/DataGaps 和固定 judgment feedback；v7 最大 5,921 chars、v9 最大 7,762 chars，无 `original_context`、`basic_info_bundle` 或完整 projection。 | context 足以做错误归因且不重复 Raw Info；实际 response 质量有空输出、validation fallback 和详细根因并存，因此后续取样不能“第一条优先”。 |
| Plan critic | v7 request hash `12b2bd35...`，user context 125,172 chars、wire 134,899 bytes、provider input 28,426 tokens；包含 24 个 compact case row、完整 post-hoc 诊断和 Signal 摘要，不含 Raw Info/identity。response 保留了价格下跌过度加权、商业化不足加权、Signal validation 失败、收入减速和 base-rate FP 等主要模式。 | 内容足以做 vertical 归因，28k 输入在这一轮有真实聚合价值；它没有抹掉 original layer。 |
| Round reflection | v7 request hash `2b56f7fd...`，只有一个完成 Plan，却要求 horizontal reflection；response 几乎逐字复制 vertical critic。 | 逻辑不成立且浪费 3,201 input + 672 output tokens；现已在少于两个 Plan 时零调用。 |
| H1 | v7 在构造请求前的全 alias scan 性能热点停止；compile-once 修复后没有剩余额度把 H1 真正发送。 | 只做过本地 context/code/tests 检查，不能声称 live 验证。 |
| H2/H3/Update | 没有到达。 | H2 readiness、H3 news relevance/dedup、zero-call Update 只有离线测试证据，没有真实 response 证据。 |

对实际到达的 retrospective/proposer/critic/post-hoc/Predictor 请求和接受 response，
用对应完整 alias inventory 做 value-level 扫描均为 0 命中。这里的新闻污染不是
target identity 泄漏：它是合法保留的第三方公司名被错误当成目标证据，必须由
source relevance 边界解决，不能靠 anonymity scanner 误删所有第三方名称。

## 确认的跨层失真案例

v7 `plan_r0001_c02` 的第 14 个 case（Micron，CIK 723125）把问题完整暴露出来：

1. initialize 实际 request `1ebe8923...` 的 5 条“company news”只有 1 条正文是
   Micron；另外 4 条分别属于 ASP Isotopes、Astera Labs、SAIHEAT 和 TSMC。
2. 模型把这些文字视为目标公司的可用 Basic evidence。post-hoc 的
   `ignored_evidence` 随后明确列出五家公司，并将它们解释为该 false negative
   忽略的商业化/行业正面证据。
3. Plan critic 再把这组污染概括为“underweighting positive commercialization
   and pipeline progress”。
4. 只有一个 Plan 的 Round reflection 又复述了这条结论，于是错误来源看起来像
   稳定的跨 Plan 经验。

将当前可见发行人匹配器回放到 v7 c02 的完整 24-case Basic artifacts：107 条
新闻 projection 中有 23 条正文/标题不含目标发行人的强名称或 boundary-matched
ticker，影响 9 个 case；Micron 是 4/5。旧 artifacts 保持不可变，不能重写这些
historical reflections。

同时，旧 `PlanMetaMemory.model_view()` 对每个 assessment 选择第一条 case。v7
会因此选中早期空反思和 validation fallback，而不是 case 14、17、20、21 等具体
根因。durable round meta 实际保存了全部 24 条 original reflection 和精确 vertical
critic，因此这是 model-facing selection 缺陷，不是 durable overwrite。修复后的
同一 v7 artifact view 为 11,617 chars，并选中 case 14 的 severe false negative、
case 17 的 false positive、case 22 的 conservative correct positive 和 case 3 的
strong correct negative；每条带 opaque case index。未来运行中，case 14 上游的
他公司新闻会先被过滤，不会再制造这条伪根因。

## 已实施修复

1. **Basic / Signal company news relevance**：当 case 有身份 aliases 时，news /
   company_news 的可见 title/body 必须出现公司名派生强 alias 或大小写严格的短
   ticker；provider ticker metadata 和存储路由本身不够。过滤事件持久化
   `news_documents_filtered` 和 document ids，Raw Info 原文不删除。正式全大写
   公司名派生的自然 brand 使用大小写不敏感匹配，避免把 `CIENA`/`Ciena` 误判。
   H3 复用同一 matcher，再叠加 hypothesis query relevance。
2. **market projection row boundary**：先按完整 JSON row 和 observation lookback
   选 offset，再在不重叠的完整行边界分组；normalizer 不再收到跨 chunk 残留的
   metadata key/value。raw offsets 与完整原文保持不变。
3. **reflection fidelity**：model-facing FIFO 先按 assessment 计数，再为每类选择
   非空内容最多的 reflection，而不是第一条；最多六类，保留 opaque case index，
   全局仍受 48k chars 限制。durable original/vertical/horizontal 不变。
4. **horizontal semantics**：新完成 Plan 少于两个时不调用 H_R，持久化带 Plan ref
   的确定性空 horizontal layer。vertical critic 和 original cases 仍完整提交。
5. **routing token projection**：不再把 prior document fingerprints/content hashes
   发给 selector；保留 prior compact Signal results 以选择互补证据。本地仍按
   executed refs 和 fingerprints 双重 no-op。

这些更改没有调整 16 Anchor + 8 Random、Combined Binary F1、四档 judgment、
2x/六个月标签、Signal promotion、Locked Test 或任何 commit pointer 规则。

## Token 使用与进一步优化判断

- v7-v9 的 164 次 routing/correction 实际 payload 累计重复发送 216,953 chars 的
  fingerprint JSON（2,958 个 hash entry）；本次已零损失删除。模型从未能据 hash
  产生语义价值。
- 单 Plan H_R 的实际 v7 对照是 3,201 input + 672 output tokens、`$0.0012726`；
  本次改为零调用，同时避免伪 horizontal insight。
- 新闻过滤在 v7 对照上移除 23/107 条不相关 projection，不只是节省 token，更
  重要的是阻止错误学习跨层传播。
- Signal-batch correction 在 v7/v8/v9 分别消耗 272,898 / 115,305 / 73,669 input
  tokens，共 461,872。外/内 identity prompt 已修；剩余主要是 evidence 语义错误。
  这仍是最大优化区，但不能通过自动改引用、把 unavailable 改成有 evidence、或
  放宽 literal uniqueness 来省调用。下一步只能改善模型可执行的 evidence catalog
  或在不丢可见原文的前提下缩小 correction projection，并继续 fail-closed 验证。
- Plan critic 的 28,426 input tokens 保留了 24 个 case 的真实 post-hoc 根因；在
  当前一次/Plan 的频率下有明确增量价值。本次不为省 token 再裁掉具体诊断。

每个已发送 attempt 都能找到 exact request artifact 和 `wire_request.body_bytes`；
v4-v9 最大 wire body 分别为 65,693 / 67,645 / 63,936 / 134,899 / 52,617 /
47,687 bytes。所有完成 trajectory 的最大 case model tokens 分别为 69,995 /
66,597 / 64,057 / 68,475 / 72,933 / 65,193，均低于 120k，无 post-call overflow。

## 验收矩阵

| 要求 | 结果 |
| --- | --- |
| 至少一个 Plan 完成 24 cases | 通过：v7 c02 |
| `last_completed_round=1` | 通过：v7 |
| `last_completed_cycle=1` | **未通过：所有 v4-v9 均为 0** |
| Locked Test 未访问 | 通过 |
| Registry 只经 promotion gate 变化 | 通过；本链 Registry 未变化 |
| 每 case <=120k、发送前 reservation | 通过 |
| reached roles 的 target alias 命中为 0 | 通过 |
| SEC model view HTML tags 为 0 | 通过 |
| source types 属于 catalog | 通过：提交 Plan 只用 `news`/`market_data` |
| routing <=4，LLM Signal <=2 | 通过 |
| post-hoc 不含完整 original context | 通过 |
| meta <=48k 且具体根因可见 | 通过：v7 replay 11,617 chars |
| H2 readiness、H3 packet/relevance、Update zero-call live 验证 | **未到达，不能声称通过** |

当前代码的 356 个 repository tests 全部通过。最终 repository lint 和 checkpoint
记录在同日 status/changelog；不会用新的外部 workspace 绕过已经耗尽的 800-attempt
任务预算。若要实现最初的完整 `round=1/cycle=1` live 目标，需要用户另行扩大本次
修复链的累计 attempt 预算；standing authorization 本身不等同于可重置额度。

## 预算终止后的上下文续审

对 v7-v9 的 56 个可读 `research_controller_finalize` 基础响应逐字段重放后发现，
50 个没有改变 hypothesis、belief、evidence、contradiction、resolved/open question
中的任何一项；剩余响应中出现了没有新证据却把 open question 移到 resolved、删除
hypothesis/open question，以及仅改写 evidence claim 的情况。终止触发发生在
`no_signal_match`、case budget 或最大 Signal round 之后，此时没有任何新 evidence
进入 context，因此再让模型重写 ResearchState 没有信息论依据，且会损害前序推理
保真度。当前实现改为确定性闭合：完整保留全部分析字段，只设置
`decision=finalize` 并清空 `next_information_needs`。三个完整 24-case candidate 可
因此少 72 个外部 attempt。

DeepSeek prefix cache 的实际可观测性也补齐：response/cache/progress 现在持久化
provider 报告的 `prompt_cache_hit_tokens` 和 `prompt_cache_miss_tokens`，而预发送
预算仍把全部输入按 cache miss 保守计价。对 v7-v9 的 155 个真实 routing 基础请求
重排回放后，最大相同卡片组有 60 个请求；旧 user payload 因动态
`information_needs` 在前，只共享 28 个字符，新 canonical payload 先发送
`available_signal_cards`，共享前缀为 2,790 个字符，净增加 2,762 个字符。该数值只
证明更大的可复用前缀；实际命中率必须在下一次真实运行中依据 provider usage 审计。

## v10 续跑缺陷与停止点

新增边界下冻结的 v10 合同 hash 为
`010d3aa002f51772dddfdb4a3f6552aea517159364f984adba7c6518344f20db`。
在 7 个 attempt（6 completed、1 interrupted reservation）和 2 个真实 SEC fetch 后
主动停止，权威指针仍为 `0/0`。已结 LLM cost 为 `$0.00302092`，保守保留的中断
reservation 为 `$0.003696`。

逐字检查 proposer attempts 1/2 发现，两次 `H_analyse` 都明确写了
“without calculating probabilities”，实际是在遵守固定 Predictor 边界；旧 scanner
只消除了 `do not/never/must not/cannot` 后的文本，因而把其中的 `probabilities`
误判为 affirmative redefinition。attempt 6 则收到必须改变 `B/H_init` 的 focus，却
原样返回 parent 的 `B/H_init`、只改变 `H_analyse`，旧 runtime 因整体 hash 不同而
错误接受。这会让三个 proposal focus 不可归因，属于流程语义缺陷而不是模型质量。

当前修复把显式 probability prohibition 与 affirmative threshold 指令分开，拒绝时
返回实际命中的 prohibited phrase；同时按 attempt focus 验证 `B/H_init`、
`H_reflect` 或 `H_analyse` 对每个 parent 都确实变化。v10 的三个真实响应成为最小
fixture。provider usage 另兼容 Responses 的
`input_tokens_details.cached_tokens`，并由总 input 确定性计算 miss；预算仍按全 miss
冻结。下一版合同只能使用新增授权的剩余额度：793 attempts、`$18.93009424` 和
956 个真实 provider requests。

## v11 SEC projection 与 evidence claim 缺陷

v11 合同 hash 为
`b94f7a56f75505757afb344ab714dcd1207937a6af8abb353dbdebd1e1502893`。
第一个 case 已用 7 个模型调用完成，证明确定性 terminal closure 正常工作；真实
usage 也首次证明缓存命中：三个 proposer 均为 1,024/1,047 input tokens 命中，
一个 soft-Signal batch 为 9,984/10,036 命中。第二个 case 后主动停止，v11 共
14 attempts（13 completed、1 retryable transport failure）和 3 个真实 SEC fetch，
已结 cost `$0.01337168`，权威指针仍为 `0/0`。

实际 attempt 10 的 `quarterly_filings` model view 有 19 个 projection、10,064
字符、12 个 HTML/XBRL tag 和 7 个 `style=` 片段。根因不是 tag regex 完全缺失，
而是 resolver 先按每 2,000 个 raw HTML 字符切块和 query 排序，导致 span 从 tag
attribute 中间开始或结束；随后只删除完整 `<...>` 的 projection 无法恢复边界，
而 query hit 又会被 XBRL attribute 干扰。当前 resolver 对 filing markup 先在完整
document 上移除 tags、规范化空白并按 readable text 排序/分窗，再把窗口映射回
raw start/end；durable span 仍严格等于原始 Raw Info literal。projection 额外移除
旧边界 fragment 并解码单字符 HTML entity。

同一 response 还把“cash 从 2,521,793 降至 2,165,476”绑定到只含 beginning
balance 的 literal。另一个市场趋势 claim 合法使用两个 refs 分别承载起终点，因此
不能简单要求每个单 ref 包含全部数量。新 gate 按相同 claim 聚合 Basic refs，并
要求 claim 的每个规范化 numeric quantity 在这些 literal 的并集中出现；缺量进入
一次 actionable correction。对 attempt 10 原始输入的精确本地 replay 从 22,610
降到 17,548 Basic chars，quarterly projection 从 19 条降到 4 条，tags、`style=`、
XBRL fragment、HTML entity 均为 0，且保留现金、经营现金流、capex 和债务段落。
v11 artifacts 保持只读；下一合同剩余 779 attempts、`$18.91672256`、953 provider
requests。

## v12 Signal-to-reflection、post-hoc 与四字母品牌边界

v12 合同 hash 为
`f0ebb65dc79fb3974c35255a84015774aec079d563e3aac42764fe922b28e1a4`。
在 23 个已预留 attempts（22 completed、1 interrupted reservation）和两个真实
SEC fetch 后主动停止，权威指针仍为 `0/0`。已结 cost `$0.02041956`，另保守保留
中断 reservation `$0.00283612`；下一合同剩余 756 attempts、`$18.89346688`、
951 个真实 provider requests。

逐字检查第一个 case 的 Signal batch 与 H_reflect 证明，结构化 ref 只能保证“引了
哪一条”，不能保证 claim 没有改写证据。`commercialization_status:v1` 的 index 0
literal 是 Paracatu 585,000 oz 和 Tasiast 119,000 oz，reflection 却写成公司 Q2
513,000 oz、margin 超过 `$2,200`；`guidance_acceleration:v1` 的 literal 在窗口边界
停在 `all-in sustaining cost of $1,`，reflection 又写成 `$1,400`。同一请求中另一
overlap projection 的完整原句实际是 `$1,500`。v13 起，Signal evidence 触及非
document 的 projection 起止边界会先纠错；新 Signal claim 的所有数字必须出现在
同 claim refs 的 exact evidence 并集；旧 batch 的 Signal ref 因 backing text 已不在
当前 context，其 claim 必须逐字保留。这样既不复制旧 batch，又不会让下游 summary
覆盖上游根因。

第一、二、三 case 的真实 post-hoc 都在 framework-correct 时返回六个空诊断数组。
同时其 `basic_info_source_index` 为空，尽管本地 prediction artifact 已有两条 compact
source-index row。根因是 post-hoc compactor 期待原始 `basic_info.requests`，实际收到
的是 Predictor 的 `basic_info.source_index/data_gaps`。当前直接保留 compact index，
不恢复完整原文；`PredictionSelfReflection` 新增向后兼容的 `decision_drivers`，新写
artifact 显式持久化，framework-correct 输出至少一条具体 source-backed driver，
避免空 original layer 被 critic/round 的泛化表述替代。

第二个 Predictor 与 post-hoc wire body 还各含 8 次 `Wynn`，来自 `Wynn Mayfair`
与 `Wynn Al Marjan Island`；正式公司名已被掩码，但四字符 leading brand 因原阈值
为五字符而漏过。当前将非 generic leading brand 阈值降为四字符，三字符仍只接受
uppercase；真实 Wynn 片段回归验证品牌、branded property 与 ticker 全部被 mask。
本轮到达的 proposer/initialize/routing/Signal batch/reflect/Predictor/post-hoc 均已检查；
H1/H2/H3/Update 仍未到达，不能标为 live-verified。

## v13 Signal projection id 唯一重定位

v13 合同 hash 为
`d2d5507e3235cc2177d650b59c1515c8fbadca2661dad71d083987e881df527c`。
主动停止时共预留 16 attempts（15 completed、1 interrupted reservation），两次
真实 SEC fetch，权威指针 `0/0`。已结 cost `$0.02110640`，保守 reservation
`$0.00463596`；下一合同剩余 740 attempts、`$18.86772452`、949 provider requests。

第一个 soft-Signal response 返回完整的 `$1,500` guidance 原句，却把它绑定到
相邻 overlap 的 `projection_46292...`。精确检查显示该 quote 在指定 projection
出现 0 次、在全部可见 projection 中总共出现 1 次，唯一匹配是
`projection_a3f27...`；指定 projection 的尾部仍是 `$1,`。旧 mapper 因只检查指定
id 而进入 correction，correction 又把 result 字段嵌进 evidence，导致本来可验证的
guidance 被降为 unavailable。当前 mapper 在指定 id 不含 literal 时搜索完整可见
lineage，仅总 occurrence=1 时使用唯一 projection 做 raw-span mapping；0 或多次仍
fail-closed，literal 不做任何修改，resolved projection 仍接受 edge-fragment 检查。

同一 case 还实证了 v12 两项修复：post-hoc 不再返回空对象，而是保留三条具体
`decision_drivers`；后续第二次 H_reflect 对先前 `commercialization_status` ref 的
claim 逐字保留。Predictor/post-hoc 的 Basic source index 也已非空。Slow 角色仍未
到达。

## v14 精确单位等价与 fixed-threshold 描述

v14 合同 hash 为
`31d04773743c66dd50812c1d22dccf6055931de1e6f225552f1d0862abfc59d4`。
主动停止时 14 reserved attempts（13 completed、1 interrupted）、两次真实 SEC
fetch，指针 `0/0`。已结 cost `$0.02004632`，保守 reservation `$0.01425900`；
下一合同剩余 726 attempts、`$18.83341920`、947 provider requests。

c01 首 case 的 Basic financial projection 原样包含 `val=1605300000` 和
`val=2446400000`，initialize claim 合理写成 `$1.6053 billion` 和
`$2.4464 billion`。旧 quantity gate 只比较字符化数字，纠错反馈仍无法让模型改变
正确表述，最终错误淘汰整个 candidate。当前对每个带显式单位的 token 建立原值与
精确 Decimal 缩放值的等价组；literal 命中任一个即满足。这样
`2,521,793 thousand` 仍可由 raw `2,521,793` literal 支持，`1.6053 billion`
也可由 `1605300000` 支持；不做 tolerance、rounding 或隐含单位猜测。

c02 的 post-hoc 初次输出已经含两条具体 decision drivers，其中“$27 相对 $24.37
约 11%，far below the doubling threshold”是在正确使用固定 2x 定义，旧 scanner 却
因裸 `threshold` 单词触发纠错。当前允许 bare fixed-threshold/cutoff 描述；只有
set/use/adopt/change/adjust 等肯定动作、显式 numeric replacement、probability/odds
仍被拒绝。纠错没有改变分析结论，证明原调用是纯 token 浪费。

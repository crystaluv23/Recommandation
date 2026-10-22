# Mining source coordinates, complete prompt cost and fresh consumer boundary

2026-10-23. 本轮推进 `content_chain` 的局部连接，不关闭整体 S3/S4 或工程 MVP。
外部 LLM API、GET、新业务标签、check/LockedTest、候选发布及完整后继均为 0。
所有生产回答由仅见当前 exact inbox 的 fresh subagent 独占写 outbox；父进程不代写回答。

## 验收问题与结果

上一轮不同来源前置有两项实际缺口：source handle 保留可解析的 SEC accession；
四请求固定路径逻辑预留 102563，超过原 case cap 98304。该前置只有 input capture、
0 inbox/作者，并没有可重启的正式执行。本轮保留原失败，先修可逆身份投影和完整
提示的重复成本，再冻结同两份来源、原 O1–O6 和原预算，运行首个正式两控。

结果：显式 SEC 坐标的局部投影/恢复成立；完整固定四步预演可达；fresh 两控均正确
找到并读取两个 operand，继而合法计算差值，第五请求被原预算拒绝。**完整模块端点
0/2**，没有 `record_deferred` intent，也没有执行 domain terminal。不得把计算正确
或四步预演改报成两控通过。旧 taxonomy 两控 **1/2**、旧前置失败及其他固定分母不改。

## 行为修复及证据

1. 原生 `_CaseIdentityProjection` 在 issuer 的部分匹配前处理完整 dashed accession、
   SEC `Archives/edgar/data` 的数字 issuer/accession 目录。filing agent 的 accession
   前缀不等于 issuer CIK，仍可识别。多层 JSON slash escaping、目录终点/query 及
   相对路径共用可逆 token 表；canonical refs、原文、内容 hash 和持久化原件不改。
   无上下文的 18 位数字、财务值、日期及数字开头的普通文件名不据此屏蔽。
2. 仅合并全局 Mining controller prompt 的重复表述，12953→11098 UTF-8 bytes，
   每次省 1855、四次省 7420。59 组义务逐项对照、23 个纸面反例；动作/字段/enum、
   PIT/候选/准入/记忆/backlog/terminal 义务保持，shared constants 和整个
   `next_action` 源码不变。该对照不证明所有 Mining 场景的新模型语义服从。
3. preparation 显式选择独立 `preflight-v2`；shared driver 新可选参数保持旧默认。
   原 `preflight/` 的 102563 失败未覆盖。正式 stage 从未在该失败前存在，未重置
   一个已消耗的正式 case budget。正式准备前绑定 108 code、1791 source/reference
   文件；其中来源前置 inventory 为 1784，额外包含 reference 和本次 preflight result。

身份审查的最初义务冻结晚于第一版实现存在，不冒称完全盲于实现。独立反例实际
捕获多层 slash、终点/query 未遮挡，以及过宽数字前缀误遮普通文件名，均留原失败后
修复。最终 hash-bound **19/19**（10 mask、9 preserve）及完整原生
estimate→wire→cache→inverse/typed patch 控制通过。真实八条前置请求由新 controller
逐字节重建、与 canonical view 可逆，四个实际源 operand 的 literal/hash/namespace/
期间/值均核同。只覆盖已识别别名和显式 SEC 坐标，不证明全球匿名性或申报真值。

证据：

- [身份最终局部审查](../runs/diagnostics/mining_identity_and_prompt_20261023_v1/identity-review/local-final-review.json)
- [真实八请求前置审查](../runs/diagnostics/mining_identity_and_prompt_20261023_v1/identity-review/full-mining-preflight-v2-review.json)
- [最终提示逐项映射](../runs/diagnostics/mining_identity_and_prompt_20261023_v1/prompt-review/applied-obligation-map-20261023-v1.json)
- [最终提示字节审查](../runs/diagnostics/mining_identity_and_prompt_20261023_v1/prompt-review/applied-review-20261023-v1.json)
- [341 项关联测试](../runs/diagnostics/mining_identity_and_prompt_20261023_v1/associated-tests.log)，网络 tripwire 0；127 tested bindings 前后同。
- [pre-push lint](../runs/diagnostics/mining_identity_and_prompt_20261023_v1/pre-push.log) PASS，已亲读 `.lint-feedback/pre-push-last.log`；meta PASS 仅行政一致性。

首次本地测试有 stage-input 配置和 cache key 的 harness 错，独立前置重建另有缺省
progress key 的 harness 错，均保留后修 harness；不算产品反例。root 终核首次 import
误指不存在的 identity module，发生在只读校验前；改用 driver 已有 canonical hash
函数后通过，无 stage 写入。

## Fresh 两控：保留原预算与资源失败

来源均来自原 Discovery case-001/002 的首份既有财务文档；initial target query 是
受控 preparation，非自主检索。来源为回溯 normalized SEC extraction，保
`requires_primary_filing_audit` 限制，不称 primary filing/latest/current 真值。

| 样本 | 实际来源与读到的历史量 | 四个真实已答请求逻辑预留 | 第五 prepared / 结果 |
| --- | --- | --- | --- |
| a / 1179 | IFRS `CashFlowsFromUsedInOperatingActivities`、USD；2023-07-01..2024-06-30 -15122354，2022-07-01..2023-06-30 -2378789 | 21100+22457+25126+26582 = **95265** | 25385；总120650>98304，创建 inbox 前拒绝 |
| b / 0770 | US-GAAP `NetCashProvidedByUsedInOperatingActivities`、USD；2018-01-01..2018-09-30 20122000，2017-01-01..2017-09-30 20727000 | 19662+21030+24194+25791 = **90677** | 24396；总115073>98304，创建 inbox 前拒绝 |

两案各 4 fresh/0 structured correction，8 个真实 agent receipt。每条依次执行
compare、read latest、read prior、compute；计算 `latest_minus_comparable_prior` 分别
为 **-12743565.000000**、**-605000.000000**。a 原答明确负值不能推增长/融资计划/
研究效果；b 原答明确是九个月 YTD，Q3 metadata 不使其成为独立季度，并限制
2025/current/positive-control/predictive benefit 推论。不是同名跨 namespace 配对，
也不是算术或期间误读。a 两 raw row 的 fiscal_year 都为2024，原件未被重写。

已答逻辑预留共 **185942**；含两次未发送 prepared 为 **235723**。这是完整消息
UTF-8 bytes 加 output allowance 的原生逻辑计量，不是 host token usage 或费用。
固定每案 single32768/case98304、6 decisions/至多1纠错、output2000、heavy6 不变。
两份终态各封存34文件，root 只读核 hash/manifest，未调用 advance 重入或追加作者。
逐次 advance 复用实际 cache/receipt；不冒称 OS 中断、全研究恢复或后继精确复用。

- [a 原生失败终态](../runs/diagnostics/mining_locator_generalization_20261023_v1/stage/a/failure.json)
- [b 原生失败终态](../runs/diagnostics/mining_locator_generalization_20261023_v1/stage/b/failure.json)
- [独立实际消费者审查](../runs/diagnostics/mining_identity_and_prompt_20261023_v1/independent/fresh-consumer-review.json)

## 首次缺失与下一行动

此次不是模型再次违反已知预算。实际作者只见 `/budget/{browse_remaining,
heavy_remaining,light_remaining}`；第4次 heavy 仍为2，`compute_statistic` 合法。
完整 system/user 没有 single32768/case98304、累计 reservation 或下一请求余量。
累计 gate 在共享 stage `make_client.observe(request_ready)`，但没有接入决策 view。
该证据定位本 stage 的 orchestration→decision 衔接，不能未经核实推及所有运行入口。

我此前按固定 compare→read→read→endpoint 预演判断可达，忽略了允许且有研究意义的
额外计算动作。压短提示只解决固定路径字节成本，不能证明所有合法动作序列可完成；
不应事后要求作者必须第4步结束，也不把资源异常变成内容纠错/无研究模式。

下一步先检查现有 transport/caller 预算接口，让决策看到实际适用的剩余额度与完整
请求成本，并验证与预留/重放/typed correction 一致。先用已封存两案的只读重建及
边界反例区分“信息足够可规划”与“原资源不足”，不再盲压提示或重跑这两个终态。
任何后续 fresh 控制另行真实冻结；不提高预算、不删工具/正文义务、不换易源求过。

canonical 分类持久化 A/B 仍等原用户决策，未默改；完整反馈消费、新测量的忠实实现/
准入/后继精确使用、完整恢复及双环仍 open。独立收益是后续里程碑，未知。

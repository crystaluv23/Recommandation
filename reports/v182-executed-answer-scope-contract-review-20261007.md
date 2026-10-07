# v182 实际回答范围合同复核

2026-10-07。审计 main `ff28a5a1`、冻结运行 `85ffff9e`。本轮只保存已完成的诊断与可审查提案；不改生产代码、活动 spec、oracle、历史结果或评分。

## 已证实的问题

Bumble 两案的 Q3/FY 需求被 Q2 引文记为已解决。生产 need contract 与原保存请求完全相等，完整 state validator 接受实际落盘状态。诊断副本只恢复未回答需求、删除对应的错误 resolved 标记，随后得到 `remove_exact_target`；typed fallback 又删除该需求，合并结果仍通过完整 validator。冻结和 main 的完整诊断结果相等，外部调用 0。

这说明问题涉及 Routing 的预期范围、Reflect 的完成义务、validator 与 fallback。**合法引用和成功执行不能证明实际问题已回答。** 诊断副本没有写回旧运行，不能说模型曾返回该副本。

当前更高层合同明确规定采纳 scoped full answer 后删除目标、partial 后替换为 selector 的固定 residual：见 [scheme_evolution.md](../spec/src/stock_opportunity_agent/research/scheme_evolution.md)、[evolution_runtime.md](../spec/src/stock_opportunity_agent/research/evolution_runtime.md)。固定 prompt、叶子 validator 与 fallback 都实现了这条规则。只放松叶子检查会造成合同冲突，本轮未实施。

## Kinross 的成功纠错反例与开放问题

亲读 12 份相关原输出、5 个完整源窗，共 10007 字符；两份原 transcript 文件 hash 与两个最终引用的唯一 literal 校验通过。其余输入不是完整亲读验收。

- 264 第三段引文在投影边缘结束于 `$1,`；265 获得一个完整新窗口，改用 Q2 与 Q1 的完整生产/成本指引。生产 Signal runner 接收原首答及原纠错，初始与纠错 projection ID 均与保存请求一致，完整 canonical result 与历史 `success/neutral/sufficient` 相等。冻结与 main 回放均通过。10 个 runner 源文件机械核 hash；不冒称全部正文亲读，也不声称匿名化或 HTTP 重放。
- 267 用全年 2025 指引删除并 resolved 一个询问未来六个月指引的需求。原文还明确预计全年剩余两个季度各约 500000 盎司。measurement sufficient 不能单独证明整个需求完成，但也不能由此猜测公司没有 2026 指引，或强迫补一个未经披露的六个月预测；此处范围仍需语义复核。
- 268 将生产/成本绝对水平及利润作为支持背景，同时明确写 guidance_acceleration 为 neutral；269 因它不是加速催化剂而称该使用误导。revision neutral 不使基础水平失去研究价值，原理由也未明确声称指引上调。这是待审归因，不能当作已证明的误判原因。269 对 order 的 domain_unavailable 保持区分、把动量因果列为 hypothesis，是应保留的反例。

本轮没有完成 Kinross 全双案内容链；已有 Enbridge/Bumble 共 4/48 案的成对内容报告，其余 44 案仍待完整复核。

## 可审查提案，尚未实施

保留 Routing 的原始预期范围。在 Reflect 依据实际执行内容，为每个目标声明实际 `full/partial/unanswered`，绑定所采纳的 exact evidence tuples；执行未回答预期范围时保留未决需求。使用既有有限交换与 snapshot-bound repair，不追加模型调用来猜答案。

先评审该 disposition 的接口位置和保存形式，再自上而下同步 scheme/runtime、角色与 validator 合同；本轮不新增 canonical 字段或跨模块依赖。随后一起验证正常 prompt、解析、typed 权限、fallback、保存、最终 Predictor、posthoc、更高层与下一周期消费。机器检查 ownership、literal 身份、residual/PIT 和状态一致性，不能把这些检查说成语义证明。

必须保留的反例：partial measurement 可完整回答狭窄事实需求；sufficient measurement 可只回答复合需求一个期间/方面；neutral 引文仍可提供有用水平背景；unavailable/technical failure 不授权完成；未选中的重复 need occurrence 不得丢失；当时公开的未来预测仍可用，不能要求未来已实现数据。不能用公司/季度 regex 代替这些判断。

## 当前状态与限制

新鲜读取确认 v182 exit0、完成时间 2026-10-06T21:59:30.527295Z、正式 Fast/Slow 指针 1/1；冻结 tracked clean、revision 未变。仍未验收新 magnitude、后继 exact-version 使用、高档有效扩展或独立收益；PIT 定义和独立四臂协议没有新的人类答复。

目标服务在 **2026-10-07T03:41:36Z 返回 `usageLimited`**，tokensUsed=6011233、timeUsedSeconds=36662；这覆盖旧 heartbeat 的 ACTIVE 描述。保存本轮已完成成果和 git checkpoint 后停止新增目标工作，不把它标为 complete/blocked/paused，也不自行恢复。继续需要目标使用限制解除。

[完整原件绑定、诊断及复现脚本](v182-executed-answer-scope-contract-review-20261007.json)。报告-only 本轮未重跑全量单元测试；已完成两组冻结/main 生产回放与原件绑定，repository lint PASS，最新完整日志已读（UTC 2026-10-07T03:44:45Z）。

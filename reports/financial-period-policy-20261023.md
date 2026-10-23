# 用户批准的财务比较期间：新版本局部验收

2026-10-23，用户选择收入加速度为“本季度同比增长率－紧邻上一季度同比增长率”；缺任一比较期为 unavailable。毛利率变化采用最新期间减去年同一财务窗口。实现、原材料和唯一真实两项确定性批次已通过独立核验：**1个数值测量正确、1个缺资料判断正确**。Fast 全体、工程 MVP 与独立预测收益未通过。

## 定义与实现边界

- `gross_margin_change:v4`：最新 GrossProfit/revenue 减去年同窗口 margin；`period_policy=same_window_yoy`。
- `revenue_acceleration:v3`：季度需要四个明确报告窗口；年度比较相邻年度同比增速，需要三个年度窗口；`period_policy=adjacent_yoy`。
- 新版本保留原注册函数 ID，满足既有 next-version validator；显式政策进入测量范围与分类声明。未配政策的旧版本继续原算法；未知显式政策 unavailable。
- 两者先确定最新 revenue 窗口，再检查利润与比较期；同结束日采用明确报告的最短窗口。不得跳季度、从累计数相减制造单季、混用年度季度或回退旧完整配对。
- 保留原币种、总额 tag、PIT、550天新鲜度、literal、阈值、合理值及准入政策。支持明确月边界；stub、无独立日历证明的52/53周期间 unavailable。

新公式使用 literal 中的精确数做中间分数运算，最终才转 float；分类仍调用原 classifier，不增加 epsilon。首轮独立控制发现三个数学上恰好落阈值的值因中间浮点误差误分，此失败保留。最终 float 在小于一个 ULP 的差异上仍不能区分精确实数，不宣称任意精度分类。

## 独立证据

[最终独立审查](../runs/diagnostics/financial_period_policy_20261023_v1/independent/candidate-final-lineage-review-report.json)及对应原件保留：

- 实际旧 `v1→v3`、`v1→v2` 定义逐版本进入独立合成 Registry，再验证真实 next-version；两新版本与11通用 fixtures 通过。错误函数 ID 与概念拒绝，10未知政策返回 unavailable。
- 85项原失败、季度/年度/YTD、财政年、缺期、冲突、币种、边界、科学计数和大整数等控制通过。14组无政策旧输出及选文依据与 ba309796 相等；剥除新增 dispatch 后旧算法及共同 classifier 未变。
- 两新版本实际 prepare 各10份文档，与61份本 issuer 全池的完整 basis 相同；这是选文证据，不是实测结果。
- 源 oracle 在真实新 Signal 执行前由标准库独立构造并冻结；完整列出允许的同事实历史版本，避免重犯旧 oracle 漏列 prior 版本的问题。原 freeze 不改，另用 addendum 绑定原 ID＋显式政策。

[245项关联测试](../runs/diagnostics/financial_period_policy_20261023_v1/driver/associated-tests.log)通过；与59项focused检查重叠，不相加。原模型反馈语义0/1、旧财务9项的6通过/1失败/2unknown与所有已完成 stage 均保留。

## 实测与剩余范围

新批次固定分母为2，仅一个 GPRE/2025-05-30、原1780份 reviewed view，无新网络、模型、标签、append、稳定发布或业务指针推进。[唯一真实执行产物](../runs/diagnostics/financial_period_policy_20261023_v1/native-approved/native-batch.json)符合预期：margin 为 `-1072647553/119744393070 = -0.00895781026150388`（约−0.896个百分点），neutral；acceleration 因缺明确报告的2024Q4及2023Q4 revenue 而 domain_unavailable，无数值。不是两个数值测量通过。

[实测独立审查](../runs/diagnostics/financial_period_policy_20261023_v1/independent/actual-review.json)逐核四条完整literal及允许的原申报版本、选文/完整basis/fingerprints、spec/result/contract hashes、政策/阈值、四条consumer observation、单位展示及JSON恢复。1799来源、98当前代码/driver/spec、旧24文件、41份顶层独立文件均保持；完整绑定另覆盖1971路径。根目录合入后59项focused检查通过，产品代码hash与实际执行候选相同。批次result保留当时的pending-review状态，后来的独立审查单独保存，未重写执行记录。

首 prepare 将 source-only 清单内历史代码 hash 错当当前资料绑定，执行前拒绝；现保留历史代码身份，当前代码独立冻结。独立 preflight 又发现脚本对 unavailable 强索引成功分类声明，已改 optional-contract 消费，原计划保留为未执行的前置拒绝。这些是诊断脚本错误，不能记为真实批次成功或产品失败，也不能掩去。

本项只验批准定义的实现和确定性消费投影；新版本尚未发布进后继冻结 Registry，未经 fresh Reflect/Predictor/Critic 消费，不建立 S8、Mining 能力或研究收益结论。整体 Fast/MVP 继续开放。

Unavailable的公共consumer投影只有通用缺资料说明；具体缺失Q4和政策保存在原始batch、plan和addendum，未伪造成功分类声明。下一次真实触发仍须检查精确新版本及研究语义消费。

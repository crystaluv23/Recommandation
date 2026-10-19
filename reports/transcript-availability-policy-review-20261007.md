# 电话会议时间来源合同评审

状态更新（2026-10-19）：用户已选择下述推荐合同；现已同步到
[Data Resolution](../spec/src/stock_opportunity_agent/data/resolution.md)。选择政策不等于
任何来源已完成证明。旧 correction preview 仍是历史提案，不是可发布的已核实输入；
会前公告只证明计划时间，不能单独证明会议实际结束或完整内容已公开。
尚未修改 oracle、原冻结输入或启动完整后继。

## 已确认的问题与有效反例

当前 [Data Resolution 合同](../spec/src/stock_opportunity_agent/data/resolution.md)
以 earnings `reportedDate` 的次日 UTC 零点作为 transcript 的可用时间。
财报发布日期与电话会议日期不是同一个事实。

| 对象 | 冻结记录 | 一手来源确认 | 影响 |
| --- | --- | --- | --- |
| Rezolve 2024Q4 | fiscal end 2024-09-30、reported 2024-10-29、available 2024-10-30 | FY2024 截止 2024-12-31；2025-04-24 发布业绩，2025-04-28 08:30 ET 召开会议 | 财年与时钟错配；v182 该案 cutoff 为 2025-05-30，尚未确认该案未来泄漏，但 lookback 与来源顺序错误 |
| Kinross 2025Q1 | reported 2025-05-06、available 2025-05-07 00:00 UTC | 会议为 2025-05-07 07:45 EDT，即 11:45 UTC | 所谓次日保守时间仍早于会议；v182 该案 cutoff 为 2025-09-30，不能据此声称该案泄漏 |
| First Interstate 2025Q1 | reported 2025-04-29、available 2025-04-30 00:00 UTC | 会议 2025-04-30 11:00 ET，回放当天 13:00 ET 后公开 | 同一代理时钟错误家族 |
| First Interstate 2025Q2 | reported 2025-07-29、available 2025-07-30 00:00 UTC | 会议 2025-07-30 11:00 ET，回放当天 13:00 ET 后公开 | 同一代理时钟错误家族 |
| ATI 2025Q2 | reported 2025-07-31、available 2025-08-01 | 会议 2025-07-31 08:30 ET | 次日规则在这个已核实样本中保守；不能把所有财政季度映射都判错 |

一手来源：[Rezolve 6-K](https://investor.rezolve.com/node/7716/html)、
[Kinross 会议公告](https://www.kinross.com/English/news-and-investors/news-releases/press-release-details/2025/Kinross-to-announce-Q1-results-on-May-6-2025/default.aspx)、
[First Interstate Q1 SEC Exhibit](https://www.sec.gov/Archives/edgar/data/860413/000086041325000057/fibk-20250331x8kpr.htm)、
[First Interstate Q2 SEC Exhibit](https://www.sec.gov/Archives/edgar/data/860413/000086041325000114/fibk-20250630x8kpr.htm)、
[ATI 会议公告](https://ir.atimaterials.com/news-events/news-details/2025/ATI-Announces-Webcast-for-Second-Quarter-2025-Results/default.aspx)。

## 推荐合同：公开会议信息的可用时间

1. fiscal `YYYYQn` 仍按公司的真实财年解释。earnings 元数据仅提供检索线索，不能独立证明 transcript 的公开时间或 fiscal period。核对公司、期间、会议主题与逐字稿内容；有冲突不能用 quarter 回显覆盖冲突。
2. 以一手会议、公开回放或逐字稿来源证明该内容何时已公开。精确时间只在覆盖整段内容的公开回放/逐字稿时间得到证明时使用；会议开始时间不能当作完整逐字稿可用时间。
3. 仅有核实后的实际会议日期时，以该会议日期次日 UTC 零点作为保守信息时间，明确其依据是公众已能听到的会议内容，**不是声称提供商逐字稿当天已经上线**。若来源涉及跨 UTC 日期或尚未证明会议结束，继续核对回放/完整公开时间，不猜测。
4. 无法建立可靠时间或期间映射时，仅该记录不可用，披露具体来源缺口；保留其他已验证记录、SEC 文件、新闻及数据。获取时间、case cutoff、标签或模型叙述都不能替代来源时间。
5. 原始 provider JSON、历史 Raw Info、v182 请求/响应/指针和输入文件均保留原件。纠正用新 document_id 与原记录 hash/来源证明的 lineage；后继输入 manifest 显式列出采用的新记录与被替代旧记录。不能仅追加新记录却仍让旧错误时钟进入后继快照。
6. 同批逐条核查 26 份 transcript，保存核查/待核查清单；目前不能宣称全部 26 份实际公开日期都已核实。不得把一种公司财年改为所有公司的 calendar quarter。

该选择保持 case pool、标签、Binary/magnitude 评分、Locked Test 和预算不变；
但会更新 Data Resolution 的时间来源合同和后继输入身份。后继结果不能与旧输入直接作因果增益比较。

## 可选择的更严格定义

若目标是证明“逐字稿这一文件已上线”，仅接受一手逐字稿/回放公开时间，
不以公开会议口头内容时间替代。找不到该文件公开时间时，这一 transcript 不可用。
这会减少历史 transcript 覆盖；其他来源仍可继续研究。

## 实施与验收顺序

用户选择后先修改 owning spec，检查 ancestor PIT/append-only 约束，再实现来源证明和
snapshot lineage。不得引入对标签/未来结果的依赖。验证至少包括晚一天会议、
跨财年/并购元数据错配、正常 fiscal quarter、UTC 边界、相同内容不同来源时间、
未知时间、错误回显，以及追加/恢复/原件不变/后继错误记录排除。

离线预览：[四条已确认错误记录的提案](transcript-availability-correction-preview-20261007.json)。
预览没有写入 oracle；其中时间采用推荐合同，必须在选择后再次核对来源身份再发布。

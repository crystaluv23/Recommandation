# ICFR exact-source prerequisite review — 2026-10-23

先冻结 `obligations.json`，再读原件并生成 `bindings-evidence.json`；复核脚本为 `review_local_sources.py`。本次只准备四份批准开发材料的来源证据，未创设研究定义、canonical 接口或候选。外部调用/新模型作者/新候选/业务 stage 改动均为 0；未读新业务标签、Check 或 Locked Test。来源定位使用旧审查记录，结论来自直接打开原 cache/正文后的核对，未沿用其 `admitted` 字样充当证明。

## 结论与证据范围

四份均 **pass_local_binding**：SEC submissions 原缓存中的 registrant CIK、精确 accession、form、primaryDocument、reportDate/acceptanceDateTime，与原 Archive 正文请求、原本地文档和当前 snapshot 相互对应。四份完整 retained body 与 source 正文逐字相同；每条原引用的字符区间另行核对。这里的通过只覆盖“这一精确历史申报对象有本地原采集支持”，不声称独立远程认证、2024/2025 当时逐字快照、全正文无污染数学证明、最新期 ICFR 真值、生产准入或研究收益。

| case/source | registrant CIK / accession | 申报 / 报告期 | submissions acceptance = published = available (UTC) | cutoff (UTC) |
| --- | --- | --- | --- | --- |
| 005 / 1507 | 0001814215 / 0000950170-25-075392 | 10-Q / 2025-03-31 | 2025-05-20 21:28:45 | 2025-05-30 00:00 |
| 006 / 1500 | 0001946703 / 0001213900-25-033933 | 20-F / 2024-12-31 | 2025-04-22 12:00:54 | 2025-07-31 00:00 |
| 003 / 1501 | 0002009312 / 0001641172-25-001168 | 10-K / 2024-12-31 | 2025-03-28 20:00:48 | 2025-09-30 00:00 |
| 001 / 1768 | 0001951089 / 0001213900-24-092156 | 20-F / 2024-06-30 | 2024-10-30 18:40:53 | 2025-05-30 00:00 |

主文档分别为 `buru-20250331.htm`、`ea0238515-20f_webuy.htm`、`form10-k.htm`、`ea0217031-20f_critical.htm`；完整引用 URL、原件/cache 路径、哈希、submission 原行、正文原始 anchors 见机器证据。accession 前缀并非 registrant CIK；本次使用 submissions `cik` 和正文 DEI EntityCentralIndexKey 双向对应，而非推断前缀。

## 原采集与后更新污染问题

- 1507：submissions 于 2026-09-17 18:13:59 UTC、精确正文于 18:14:00 UTC 缓存；正文 DEI 为 NUBURU / CIK1814215 / 10-Q / 2025-03-31 / amendment=false。生成注释日期 2025-05-20、正文签署 May20 与申报日相符。
- 1500：submissions 于 2026-09-12 19:23:39 UTC、正文于 19:46:26 UTC 缓存；DEI 为 WEBUY GLOBAL / CIK1946703 / 20-F / fiscal2024 / amendment=false；封面期末与 submission reportDate 配合读取。生成注释 Apr22 2025、签署 Apr22 同申报日。
- 1501：submissions 于 2026-09-12 12:40:15 UTC、正文于 12:40:18 UTC 缓存；DEI 为 Aureus Greenway / CIK2009312 / 10-K / fiscal2024 / amendment=false。正文 subsequent-events 明确评估至 March28 2025，等于本申报日。
- 1768：submissions 原缓存于 2026-09-04 11:34:52 UTC；正文的 2026-10-20 00:23:25 UTC 原 HTTP200 响应有完整 gzip 原始字节及 receipt，解压后与 source1768 完整相同。响应 Last-Modified 为 **2024-10-30 18:41:54 GMT**，只比 acceptance 晚 61 秒，支持同日历史 Archive 对象；`x-amz-version-id` 被保留，但没有该版本的远程历史记录，不能把这个字段独自当历史真实性证明。正文生成/签署 Oct30 2024，DEI 为 Critical Metals / CIK1951089 / 20-F / fiscal2024 / amendment=false。

这些是 accession 特定的 SEC Archive 申报正文，并非会滚动覆写的“当前公司摘要”。本地没有观察到 issuer/期间/生成时钟/引用段落与所选申报版本矛盾的后更新证据。2026 retrieved_at 表示本地后来取得历史申报，不等于正文到 2026 才公开，也不自动产生 PIT 污染。

**仍 unknown**：没有本轮独立外部取证，也未建立 2024/2025 同时点捕获或独立版本历史，因此不能宣称正文从 acceptance 瞬间到采集日绝无逐字修改。前三份仅有原 native cache，没有本次找到的独立 HTTP headers/原压缩响应；其 retrieved_at 是本地采集记录，不是 SEC 发布时间。1768 的同日 Last-Modified 是额外佐证而非上述绝对证明。哈希只固定本次观察到的文件/内容，未用来替代来源语义。

## 原文反例与可使用范围

1. **1507 可作为实际已识别 ICFR 弱点的历史材料**：原文明确 `internal control over financial reporting was not effective due to a material weakness`，继而明确本报告期未修复。评估入口先谈 disclosure controls，后面的 ICFR 结论对象必须逐字保留；本次未改写它为未来/当前新评估。
2. **1500 是明确相反材料**：as of December31 2024 的评估明说没有构成 material weaknesses 的控制缺陷。它同时含许多 may/if 风险语句，证明关键词出现不能替代历史评估结论；不能扩展为 cutoff 时点仍无弱点。
3. **1501 是更强的未知/假设反例**：风险部分说 `may experience`；管理层报告部分另明确因新上市 transition period，**未提供 management assessment**。因此既不能从该风险标题认定实际弱点，也不能因缺肯定句认定无弱点。此额外段落已以原始 offset/span 落机器证据。
4. **1768 的歧义是原申报内容本身**：多处说 six significant deficiencies，Item15 同段又称 identified material weaknesses，并定义两者严重性不同。原响应与 snapshot 相同，不能靠重新命名或删掉其中一句消除冲突；其来源绑定可通过，清洁单向 ICFR 语义为 unknown/术语冲突反例。

本地证据已足够继续准备“精确历史申报材料”层的能力控制，前提是消费端保留以上日期/对象和 unknown 区别；还不足以冻结候选测量定义、承诺股票方向/幅度或宣称生产能力通过。若未来义务提升为“当时逐字正文独立版本证明”，需新增针对性来源证据，不能把当前材料口头升级。重要关闭前请由主审对以上范围作反例复核；此文件本身是前提证据准备。

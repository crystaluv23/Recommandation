# v2 实际部署短核验

固定范围：h005–h008 的 exact inbox／raw outbox／receipt，以及 h009 inbox；未读
h009 回答或 receipt，未追后续。31 个必要绑定文件在检查期间稳定，所读 native
代码与 v2 manifest 冻结 hash 相同。仅在本新诊断目录写报告／证据，未改 stage、
oracle、code 或生产答案，未联系 actors，外部 API／网络0。

实际保留已确认：h007 的 `narrative_read_evidence` 同时含 case-003 A/B 两窗；
h007 发出目录动作后，h008 仍完整保留 A/B；h008 首读 case-002 C 后，h009 同时
保留 A/B/C。正文长度分别1631／1015／2094，无遗漏或 oversized。与旧实际来源
逐项核正文、raw范围、case、content_hash／verbatim_hash、来源类型与公开时钟
均相同；原文件的完整正文 hash 和 raw slice hash 也匹配。当前 read_targets 忠实
对应真实原答中的 event_ref；旧 stage 曾使用 document_ref，未把不同读取动作
伪称相同。匿名编号跨请求会变化，按 case＋source hash＋raw范围对齐。

完整请求的 compact sorted UTF-8 messages bytes 加 output allowance，逐个等于
`request_budget.this_request` 和 native request-scopes reservation；h006–h009
的 prior-used 增量也与前一已答请求完整成本一致，因此新正文页、披露及重复的
last result 均已计入：

| inbox | 完整逻辑预留 |
| --- | ---: |
| h005 | 193062 |
| h006 | 192196 |
| h007 | 193665 |
| h008 | 198990 |
| h009 | 197851 |

h009 inbox 记载此前8答累计1244600；本检查仅核它的输入预留，不将它计为新答。
这些数字不是 host tokens 或实测费用，二者未测量。

h007 原答将 A 的 disclosure-controls 有效与 B 的 ICFR 无重大变化分开，并明确
两窗未建立 ICFR effectiveness assessment／material weakness predicate。此有限
表述与可见原文一致；不背书整份文件、最终测量或任何股价方向，也不据此证明
修复造成效率提升、节省请求或完成候选链。

剩余导航限制：h008 evidence 目录只含2/14项，omitted12、next_cursor2，而 light
剩余0、catalog allowed_scopes 仅 memory。h009 的 last result 被 C 的 read 替换，
目录页／section 列表不再出现；三窗正文、已读回执和 raw 导航坐标仍在。这里只
记录可见限制，未改 code，也不判定其已造成能力失败。

逐项出处与入账证据见 `evidence.json`，文件 hash 见 `bindings.json`。这是实际
运行中的输入保留和有限原答核验，不是完整候选、准入／复用或 MVP 关闭。

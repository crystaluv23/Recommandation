# 已完成 h001–h010 的正文保留诊断

结论：已确认 S4 后续 view 的正文保留缺口；没有确认原材料或运行时 evidence
丢失，也不足以仅凭这些重读判定 Mining 能力失败。当前角色请求各只有 system
与当前 user view 两条 message，未附前轮对话。每次实际 read 的正文只进入下一
轮 `last_action_result.masked`；再执行别的动作便被替换，进度只保留出处回执。

审查固定为已完成 h001–h010 的 exact inbox、raw answer、receipt。未读取 h011
或后续请求；h010 的 raw answer 只证明它请求再次读取，不追认该动作的执行结果。
34 个绑定文件复核稳定，所读 native view 代码与 stage manifest 冻结 hash 相同。

| 窗口 | 实际 raw 坐标／长度 | readable 字符数 | 固定集合中出现完整正文的 inbox |
| --- | --- | ---: | --- |
| case-003 A | 1148801 / 4000 | 1631 | h006、h008 |
| case-003 B | 1152908 / 4000 | 1015 | h007 |
| case-002 C | 3969625 / 4000 | 2094 | h010 |

全 payload 字符串逐项检索完整正文及各窗有辨识力的含义片段，结果一致：
h007 有 B、无 A；h008 重读后有 A、无 B；h009 调回目录后 A/B 均无；h010 有 C、
无 A/B。后三轮旧窗口回执仍完整，无 omitted rows，包含 content_hash、
verbatim_hash、raw offset/length、case_refs、next_readable_start、read_count。
因此这里不是回执分页导致的遗漏。A 的已执行重读在 h008 回执中明确计为2。

匿名编号不能跨 wire 直连：此前 case-003 为 `[ANON_ID_0000]`，h010 中 case-002
成为0000、case-003成为0001。本检查按 case、content_hash、raw范围及原始窗口
verbatim_hash 对齐。完整 hash 与逐轮出现／缺失路径见 `fixed10-evidence.json`；
文件 hash 见 `bindings.json`。

读取 h010 receipt 之前已保存的九动作 seed observation，确认 A/B/C 全部仍在
runtime `evidence[].read_windows[].readable_text` 中，正文 hash 与各 inbox 所见
相同。`_read_narrative_span` 保存这份运行时交接副本；`_model_view` 却只公开
metadata-only `_read_progress` 和单个 `_last_action_result`。这是已确认的 producer
可见投影缺口，不是历史正文被删除，也不是 S5 handoff 再次截断。

动作解释应分开：h006 按 next_readable_start 读 B 是必要续页；h007 为核对 A 的
确切含义而回读有合理理由，因为当轮 A 已不可见。h008 回目录是恢复其他来源的
导航选择；h009 首读 C 是新增证据。h010 选择回读 A 也受到旧正文不可见的约束，
但为何选同一窗口、是否有更好的来源及最终测量能否成立，仍是模型选择／未知。
反复读同一原始窗口不增加新证据；A 的 disclosure-controls 结论与 B 的 ICFR
no-material-change 表述不能直接替代 ICFR 有效性或整改评估。这里不审判最终候选。

在当前实际可调用工具中，没有可把两个 narrative 正文固定在同一后续 view 的
工具：`read_span` 一次一个 target，最多4000 raw字符；`inspect_catalog(evidence)`
返回导航与 read receipts；`compare_groups`／`compute_statistic` 使用结构化 facts，
不比较 narrative 正文。`inspect_catalog(memory)` 读取既有授权经验，不能写入本轮
阅读笔记；`record_need_dispositions` 是需要分流／结论动作，不是来源正文 notebook，
其接受结果也只临时占据 last_action_result。没有批量 narrative read、pin 或
追加观察语义的公开动作。尤其 h010 两个不同文档无法由一次 read 同时展示。
这是限定于 h001–h010 实际完整 view／tool contracts 和冻结 Controller 实现的
明确否定；不是对未来或任意未公开工具的不存在证明。h010 的 evidence catalog
也因 light 已耗尽而不再可调用，`inspect_catalog.allowed_scopes` 仅有 memory。
实际 contracts／available_actions 已逐轮收入 `fixed10-evidence.json`。

所以能确认的是“为了再次看到旧正文，需要再次消耗角色请求／逻辑预算来重读；
host tokens／费用未测量”，以及“没有同时保留两窗原文的当前接口”；不能据此宣称每次重读都必要、模型完全不能比较，或本轮能力
验收已失败。没有运行测试、改 code／stage 状态、写生产 outbox／private oracle，
没有联系生产 actors；外部 API／网络调用0。

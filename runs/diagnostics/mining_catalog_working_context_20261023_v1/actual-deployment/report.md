# v3实际部署窄核验

固定范围：stage-v3 h001–h007 的 exact inbox、raw outbox、receipts；h008 (`96b5bb86…`) 只核输入及对应transport/request-scope，未读其答案/receipt或后继进度。按七个已确认actor/request hash固定集合，未把后来增加的receipt计入。只写本目录，代码/stage/oracle/生产答案未改，actor通信、网络/API0。

**本次实际工作上下文保留与局部原答事实通过。** h001/h002读取Signal cursor7/14后，h003–h008同时完整保留18张capability cards；逐张完整对象及source_hash与h003相等，跨h003 fetch未丢。h004只请求一次evidence cursor0，h005输入披露2/14文档、完整sections及next_cursor=2。h005/h006读A/B后，h007仍可见原whole目录；h007直接用该目录另一文档坐标3969625读C，没有重复page0。h008同时保A/B/C与该whole目录，light_remaining=1。未披露其余12目录项；这不是目录exhaustive证明。

h005–h008所留目录的response_hash均为 `1c39f92c…`、source_snapshot_hash均为 `6d185a19…`、source_snapshot_matches=true；归一化每个wire不同匿名ID后，完整result相等。目录仍是原历史响应（不含后来read_windows），真实当前正文/读状态在独立工作页，未把旧目录伪装成新读取。

| 窗口 | 原始绑定 | 实际v3读取 |
|---|---|---|
| A | case003，filing `…000149315225011966`，content_hash `f6bbe6a7…` | document_ref，offset1148801/length4000 |
| B | 同一case/source/hash | document_ref，offset1152908/length4000 |
| C | case002，filing `…000114036125018373`，content_hash `8de69375…` | document_ref，offset3969625/length4000 |

两份原件是manifest中263份document bindings的精确子集（manifest另有非document绑定，不把全部1163条误称文档）。原文件sha、全文content_hash、每窗raw verbatim_hash、按whole-document可见范围投影的完整readable_text、source_type、case/target、published_at/available_at及cutoff均匹配。case003源clock为2025-08-14T20:01:09+00:00，case002为2025-05-12T20:05:53+00:00。两份目录的完整sections/section_count/raw_chars/readable_start也与原件生成的source-owned document_card逐项相同。每wire的匿名ID映射会变，验证以真实source/hash/范围/case绑定，未按ANON_ID编号跨wire配对。

v3三个动作都是document_ref读取；此前v2对应动作是event_ref读取。实际正文/范围/源相同不等于target权限路径相同。本次每个document目标的已披露case scope分别仅case003或case002；没有把v2 event target说成相同。

h007原答称case003两窗披露effective disclosure controls及no material ICFR changes，但没有据此推出ICFR effectiveness或material-weakness contrast；随后直接读control case002原目录的section坐标。这与可见A窗DCP effectiveness结论及B窗“无重大影响/合理可能重大影响的ICFR变化”文字相符。有限结论仅为该原答对两窗控制概念的区分忠实；未证明整份filing或所有PIT资料没有其他ICFR assessment，也未评h008未来原答、候选正确性或完整研究结论。

完整实际native请求逐项计费核对：transport messages与inbox完全相同，request hash对应，`json_bytes(messages)+max_output_tokens`均等于payload估算this_request与request-scope reservation。七个receipts精确绑定各inbox/raw输出，h008输入的used也等于前七个实际成本之和。

| 固定输入 | 完整逻辑成本（bytes_plus_output） |
|---|---:|
| h001–h007，各已答 | 90877、108402、111714、234074、246816、245898、247395 |
| 7已答合计 | **1285176** |
| h008，仅输入预留，未计入已答 | **251665** |

冻结HEAD9ae48904下182个manifest code文件逐字节sha匹配；223个固定输入/原答/receipt/transport/request-scope、manifest、必要源和code文件在检查前后相同，详见bindings.json。检查脚本两次中途harness错误保留：source_bindings混有非document条目，首次selector未容错；随后把raw子串直接strip误当whole-document raw_span_view投影。纠正selector/投影后通过，原样本/source未换；此前脚本与说明均在本目录。

这里只关闭实际目录/卡片跨步可见、完整已读正文绑定和h007局部原答事实。v3 broad fetch32/query=null得到2879facts/1342relations，v2 targeted fetch为2088/952；请求全文成本和fresh采样不同。此次没有page0重查不能证明因果效率、总成本改善、新测量成立或完整candidate/S5/admission/S8/MVP通过。host tokens/费用未测量。核验到固定范围即止。

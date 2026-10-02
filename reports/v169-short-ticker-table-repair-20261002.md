# 短股票代码证券表与嵌入元数据盲化修复

本轮继续 Fast/Slow 完整目标。源诊断 v169 冻结为 `1f26845df7a0f747a08133e46c5be6be92c2c6b9`，两次供应商 SSL 终止后未再运行；70 completed/2 failed、六份 staged 案例、一份 Initialize 技术排除、Fast/Slow指针0/0均保留。新修复不改该历史，也不把技术排除改成正确预测。

## 错误家族及修改

MS 案例证券登记表的“Common Stock ... MS New York Stock Exchange”以及“MS/PA ...”没有被旧短代码模式覆盖。模型复制可见原文，在 claim 中写 symbol MS 后被身份防线当成猜名拒绝。逐实际输入复查还发现 earnings_call 正文 JSON 内 `"symbol":"MS"` 残留；只修表格会留下同类漏洞。

共享身份 matcher 增加明确证券位置：短代码位于 US 交易所名称之前（可附 /优先股系列），Trading Symbol(s) / Symbols 标签之后；源文字内明确 ticker/symbol/company_id JSON 元数据中的已知短代码也属于身份位置。嵌入 JSON 只替换值，保持键、空白、引号/转义、逗号和数值。共同 masker、出站 projection、检查与逆映射使用同一规则，不新增独立匿名化引擎。

不改变已提供 token 才能逆映射、未知 token/猜名拒绝的边界；普通 MS 症状、AI 服务、Q2收入、Gen Z、非身份 JSON 字段或不属于当前 inventory 的长代码仍保留。源文件、原始字面引用和内容 hash 不覆盖。

## 证据及范围

[实际 v169 输入重放](v169-short-ticker-table-replay-20261002.json)：14个已发送MS匹配全部遮蔽为0，原已引用字面片段经新 projection逐字恢复，财务数字和projection_id不变，原request/cache/failure SHA不变，0外部调用。该重放对旧已匿名payload追加共同遮蔽，并单独核验真实引用，不重建旧 opaque token完整逆表，也没有重新生成完整Initialize回答。

新回归覆盖交易所/优先股/标签变体、普通缩写反例、大小写明确 JSON 身份、JSON非身份字段和转义引用。实际 StructuredRoleClient 估算、持久化wire、cache模型视图和token复制逆映射一起测试；JSON结构和数字保留。模型响应为离线复制fixture，因此不证明新模型质量或真实排除率下降。

专项151项通过。全量和仓库 lint 在最终提交前核验。完整近零技术排除、双轴新因子真实入库、后继Fast使用及独立幅度收益仍需实际流程证据。

## 后继准备

v170 输入已准备（未冻结运行contract/未模型调用时核验）：anchor/discovery/validation完整case rows与v169逐项一致，标签hash与初始Registry hash一致；来源数量3602→3606，新增四份数据快照，所以不作严格同输入收益比较。后继运行只能在最终补丁已提交、合并后绑定新revision启动。

最终全量1,439项通过（86.666秒），repository lint PASS。验证覆盖本轮三项新增身份回归及此前来源集合/完整生产Plan修复；冻结v169的原FN/失败记录没有回写。

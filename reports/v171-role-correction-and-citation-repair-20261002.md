# v171 实跑前沿与共同纠错修复

2026-10-02。冻结源 v171（41d2c393）实际 Slow 已提交，Fast/Slow=0/1，Registry v7→v8。`financing_listing_action:v4` 与 `guidance_acceleration:v3` 通过技术门并发布为效果待验证；不是新因子产出。direction 与 magnitude 的两 seed 均技术失败，没有新候选。源 v170 的固定24评分、两技术排除／一技术FN原样保留。

[结构化证据](v171-role-correction-and-citation-repair-20261002.json)绑定源契约、pointer、validation/result 文件hash和实际paid请求。Mining 六次漏rationale纠错链都收到完整动作而不是native patch；首次与SSL恢复后的动作/证据前沿不同，但终态仍为技术失败。初答system要求完整action，后段又要求patch，确有相互冲突的输出语法。生产适配器现在先选唯一语法，typed修复时只要求base_hash/operations，并复用共同patch操作定义；完整action纠错仍拒绝，工具/PIT/预算/来源等完整验证不放宽。原文与正确参数保留。

Update实际8000输出token截断发生在case_diagnostics的长HTML引用，**不是fixture复制**：该请求immutable fixture JSON仅166字符。新model-facing source span带case/document/content绑定编号，HTML用已有可读投影，不截断语义正文；模型可选择编号，运行时在单独parser视图恢复完整原文，再走原完整校验。 canonical facts仍为(document_ref,exact_span)，patch base仍是原始wire output。跨案例、错文档、未知编号和混合格式均拒绝并提供局部权限；不发明缺失来源或研究结论。

真实失败请求输入JSON由263118字符降至112771字符，46个source bindings，原文不裁剪、不改变数字。0外部重放证明视图/权限/原参数保留；脚本rationale/native patch不证明模型实际会修复，截断研究内容未尝试补造。新增3项测试覆盖普通/typed Mining grammar、长HTML原文恢复和四类越界citation反例。1474全量PASS；最后复用共同PATCH_INSTRUCTION后306相关测试PASS；lint PASS。

下一步以新的冻结代码对真实失败请求做必要付费局部验证，随后保留已入库更新继续新方向/magnitude挖掘及Fast消费。完整Fast零技术排除、双轴新因子入库、独立magnitude贡献仍未验收；不把当前Slow pointer提交当作研究目标完成。

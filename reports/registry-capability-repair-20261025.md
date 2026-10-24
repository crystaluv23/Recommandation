# 批准后的 Registry 修复：基线与描述校验前提

用户已批准[受限修复方案B](mvp-next-boundaries-20261024.md)。本报告记录
其实现前提和局部修复；**capability_repair事务尚未实现、准入或发布**。
原Registry不变，不能以新seed14项替代原18项。

[独立基线](../runs/diagnostics/registry_capability_repair_20261025_v1/independent/baseline.json)
直接核对v12/18，原198文件完整保留，definition hash为
`40a451c051b0bfbdf424121a5362405f2fae6672c2be7b0f51e8072e8bd4ae8d`。
准确9个旧财务ref的fixture缺body及metadata CIK。未来七个只修fixture的
下一版本仍须保留测量/参数/期间/预期值，另两个执行已批准的期间政策。

## 独立探针改变了下一步

[审查](../runs/diagnostics/registry_capability_repair_20261025_v1/independent/review.json)
在内存中给新fixture明确合成身份，无staging/admission/publication。
七项stable审计全16fixture通过，但完整候选validator仅接受6/7：
`operating_cash_flow_margin:v2`原定义是经营现金流占收入比例，却因缺字面
margin被拒。原期间完整；这属于共享概念屏幕的同义描述误拒，不能修改
被冻结的定义或期间来凑通过。探针最初使用非compact JSON导致literal
失配的错误保留，纠正后才得出上述结论。

简单增加短语子串后，独立22案又发现5种新增误准入：nonoperating、
revenue growth、revenue per share、revenue minus expenses等被混同为
经营现金流/收入。恢复旧表实际拒绝这5案，证明是新修复引入的范围问题，
原反例结果均保留。

当前实现为明确有序的分子/分母短语加完整词及分母结束边界；拒绝紧邻
non/not前缀，尾部仅允许声明的期间/来源限定引导词。旧多token规则保持。
Update和Mining实际候选contract同步披露同一个matcher说明和概念表。
它仍是有限词面屏幕，不是自然语言含义正确的充分证明，不改变数值函数、
fixture答案、PIT或准入政策。

原定义及变体/反例5项测试通过，关联engine131项通过；实际Update及Mining
披露连接单项通过。初次本地测试把JSON的definition字段误传给dataclass
构造器，原错误日志保留；正确构造器下旧产品仍有6项真实失败，修后通过。
最后独立复验结论以独立产物为准，不将局部测试称为迁移完成。

[最终独立复验](../runs/diagnostics/registry_capability_repair_20261025_v1/independent/description-fix-review/final-review.json)
已通过36/36个声明语法内的描述变体与反例；原七项仅补身份的下一版本经
完整validator通过7/7、16/16fixtures，七个身份冲突均拒绝。原198文件未变，
staging/admission/publication仍0。语法范围外的附加措辞可被保守拒绝，旧
多token子串屏幕的语义局限仍在，不把这些检查称为任意自然语言的语义证明。

## 已细化但尚待实现的事务约束

owning spec明确普通promote仍要求健康输入；受限入口绑定原完整目录、
每个原文件hash、准确disabled原因、恰好下一版本和admission-v1 key。
其余七项须额外逐字段检查禁止阈值等漂移，通用validator不会替代该检查。
原有事务先增版本再审计，且定义hash不覆盖tests/learning等原件，不能
直接作为此接口的完整实现。新路径须先通过完整18项实际审计再推进版本，
prepared期间拒绝普通读取，精确恢复且不重复增版。

下一步先落实上述事务并验证24组独立身份、范围、准入和中断反例，再在
独立后继Registry执行已批准迁移。原始Registry和旧失败保留；全部新版本
effect-unverified，new Mining仍0，后继真实使用须另行举证。

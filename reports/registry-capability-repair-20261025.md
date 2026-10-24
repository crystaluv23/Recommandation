# 批准后的 Registry 修复：基线与描述校验前提

用户已批准[受限修复方案B](mvp-next-boundaries-20261024.md)。本报告记录
其实现与实证；**capability_repair受限事务和正式后继Registry迁移均已完成并独立核过**。
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

## 已完成的受限事务与正式迁移

owning spec明确普通promote仍要求健康输入；受限入口绑定原完整目录、
每个原文件hash、准确disabled原因、恰好下一版本和admission-v1 key。
其余七项须额外逐字段检查禁止阈值等漂移，通用validator不会替代该检查。
原有事务先增版本再审计，且定义hash不覆盖tests/learning等原件，不能
直接作为此接口的完整实现。新路径须先通过完整18项实际审计再推进版本，
prepared期间拒绝普通读取，精确恢复且不重复增版。

实现见 `SignalRegistry.capability_repair` 和独立 capability-layer helper；上层驱动
调用原完整validator，下层只消费精确绑定的真实验证/准入，不反向依赖research。
候选和稳定历史读取共享原有canonical版本内容hash，数值函数未变。

## 正式发布结果

[最终独立审查](../runs/diagnostics/registry_capability_repair_20261025_v1/independent/formal-publication-review/final-review.json)
逐件检查真实产物和原始依据；[完成记录](../runs/diagnostics/registry_capability_repair_20261025_v1/completion.json)
只表示这个受限迁移完成，不代替任何Fast/Slow业务指针。

- 实际CLI prepare/execute使用固定迁移目录，plan hash为
  `54f5afd84576b7f1706f36407c318c164f10c6e4c63356910c2d2b004a521cac`。
- 后继Registry从v12推进至v13，定义hash为
  `cd4d0f4a31de885585f37becb85300505b51af59424e6183046b75807d6c0ab5`。
  [真实Registry](../runs/diagnostics/registry_capability_repair_20261025_v1/migration/registry/registry.json)
  完整18项能力审计通过，disabled为空；没有用seed14项替代原目录。
- 精确9个下一版本中，GMv4/accelv3采用已批准政策与11份fixture；其余七项
  仅版本递增及新fixture显式合成身份，定义/测量/参数/期间/答案均保持。
  总27份fixture经过实际完整validator、稳定/批内检查和admission-v1；
  独立正式审查又实际重验，不把重复执行计为新的研究案例。
- 原198文件字节未变。后继230文件中188原件未变，改动仅9个manifest和
  registry.json；新增27个版本文件、4个精确空默认stats及1个事务记录。
  旧v12定义快照可重新构造；所有旧版本、学习记录和原失败保持。
- 九个新准入和promotion标记逐件对应候选hash/key，事务实际applied。
  新进程读取和直接精确重放通过，整个正式目录297文件、候选54文件和
  原始198文件的前后库存不变。原有三个健康版本的准入状态也原样保留；
  没有把其他legacy版本补成已准入。
- 新九项均effect-unverified，new Mining=0，模型答复/外部API/标签读取/
  业务pointer推进均0。99个精确代码文件已封存，94份复用经过重新hash
  核对的旧不可变代码档案，只新增5份归档文件。

## 恢复、后继与失败反思

[最终预发布审查](../runs/diagnostics/registry_capability_repair_20261025_v1/independent/transaction-review/prepublication-review-v4.json)
针对最终冻结代码重做74项事务控制，包括12个真实materialization/版本/标记
中断点、`os._exit(73)`直接结束进程后的新进程恢复。另7项后续普通更新、
新增Signal和可移植读取控制通过：临时副本可合法更新至v14、扩容至v15/19项，
仅复制Registry并删除准备材料后仍可读。晚期原件漂移会保留v12、无发布标记、
prepared不可读，精确恢复后才能发布。

检查中实际发现并保留六类缺口：未检查已应用promotion标记、未知状态可绕过
读取门、Python bool/int与int/float等值误放行、仅改applied字样暴露未增版
内容、将历史v13身份错误约束到当前latest而阻断合法v14、只比较已存hash而
未重算旧fixture。最终读取门核对完整提交身份、严格JSON类型、历史精确版本
spec/skill/tests及准入hash，同时允许正常后继更新。不同版本的失败/通过
证据分别保留，未用新通过覆盖原反例。

我此前主要检查同一版本内的中断，遗漏“下一次真实更新后还能读什么”；
也把状态词和hash字符串当成了足够的完成/内容证据。现在真实普通后继与
历史内容篡改反例已进入检查，不再用v13局部恢复成功替代跨轮连续性。
同一次审查中的source-group变体构造、继承准入状态集合及tuple/list形状
错误是审查harness问题，均有原记录和修正说明，未据此放宽产品边界。

最终共享hash代码的185项关联检查、12项定向历史内容/准入检查通过；早期
16项本地事务检查及旧74项属于各自代码版本，不冒充最新运行。最终74项
独立事务检查和正式发布审查补足实际连接。有限字面屏幕和去重检查仍不
构成自然语言语义正确或独立研究收益的证明。

## 尚未完成

本迁移不证明方向/magnitude Mining发现、正式Registry的fresh后继Fast消费、
真实Slow完成或预测收益。旧financial9的6strict/1literal失败/2政策unknown及
旧F9 0/1保持；分类修后新单案1/1也不推广为全部Fast通过。
下一步验证已发布精确版本在已审查真实源上的执行和消费者输入保真，再在
合法资源边界内做真实消费。完整Fast→Slow→后继Fast及必要业务恢复仍待。

# v170 技术 FN：需求相似性与保留义务冲突

2026-10-02。目标仍为逐环节产物正确、技术排除尽可能为零及Slow双轴因子真实产出入库。

## 实际失败链

AXT正类案例cik_0001051627:20250930，v170 c02在Reflect技术退出。实际输入有两条相似但不同文本的定量guidance需求：need0未被选择、必须逐字保留；guidance_acceleration:v2只针对need1。付费答删除need1、采用两条真实当前guidance引用，保留need0。原guard仍扫描全部current needs，把need0判为need1的cosmetic重写，反馈要求删除或改写这个必须保留的成员。原程序已去掉违反精确数字声明契约的新belief，引用保留，随后被这条误拒阻断；最后付费纠错按错误反馈删除need0，又因untargeted需要保留而失败。纠错次数不能解决互斥规则。

## 一致性修复

先更新owning spec。原multiplicity-aware规则先按文本与所需次数给preserve和exact partial residual分配当前occurrences；现在cosmetic检查只扫描剩余未分配位置。必须保留的相似需求不再被当作新伪装。新增/额外复制的相似需求仍拒绝，反馈使用真正surplus index而非同文本第一个被保留位置。原full remove、exact partial residual、缺失untargeted、精确重复次数、PIT、来源及数字规则不变。没有自动语义去重，也没有为结束任务删除未回答问题。

## 验证

4项新回归覆盖：untargeted相似需求保留、真正新增/额外复制及准确反馈坐标、另一partial的exact residual保留、真实LLMResearchController native patch完整合并/语义引用验证首答通过（1调用、0纠错）。既有模块一起130专项PASS。

[真实前沿重放](v170-need-cosmetic-replay-20261002.json)覆盖普通与预算terminal两份原付费native operations、实际发送need规则/选择/Signal可见结果，以及程序性grounding后实际保存到correction输入的baseline。旧guard各报1个cosmetic误拒，新guard均0；所选need1消失、untargeted need0逐字保留，shape/PIT/anchor normalization通过。原付费删除need0的纠错仍被拒绝。

此专项只为模型视图重新绑定snapshot hash；原操作和原请求/cache/failure/pointer文件不改。没有重建完整canonical Raw Info/旧匿名逆表，不将need前沿或synthetic Controller fixture视为AXT完整新预测成功。原数字改写仍需要既有grounding，不因本修复被接受。原F1、技术FN计分不改。

当前代码1461项全量PASS（86.101秒）；随后新增的完整Controller回归连同其余129项专项PASS。repository lint PASS，完整输出已读取。已确认v170监督器及子进程不存在，不重启旧冻结代码或把旧技术排除改成TP。下一步整合已验收修复，冻结继任执行，验证实际完整案例和Slow候选、技术准入、入库及后继消费；可靠性零排除与新双轴因子真实产出尚未验收。

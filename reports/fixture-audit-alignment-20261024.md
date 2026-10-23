# Fixture 候选校验与发布审计统一

本轮实际准备发布两份已批准财务更新，正常 `freeze()` 的全18项能力审计
拒绝了9份缺少issuer绑定的旧财务fixture，尚无发布。追查同时发现真正的
代码缺陷：候选validator与stable capability auditor对同一fixture使用
不同的公司、来源与正文类型规则。现已统一执行边界并通过独立反例审查。
旧9项仍应拒绝；本次不关闭S7、F9或整体MVP。

## 原因与实现

候选入口尊重fixture.company_id，接受已有source-family别名，并要求正文
为string、技术执行成功或domain-unavailable。stable审计却强制替换成
`capability_fixture`、只比较literal source_type，并用`str(content)`强转
非字符串；最后只比较categorical value。后果包含合法typed来源/显式公司
被误拒、错误公司被metadata掩盖、技术失败误当合法unavailable。

此前11个通用fixture只经candidate入口，保存的分类/源码hash不能证明
发布入口同样可执行。这次实际normal freeze才暴露该下游断点。修复是把
原candidate完整执行逻辑移至Signal Library的单一lower-level runner，
两入口共同调用；不是增加别名特例或放宽issuer/PIT。保留candidate原有
explicit override、完整LLM skill、closed-future-corpus与异常语义。
未提供CIK仍拒，不猜缺字段，不补写旧版本或原冻结来源。

## 验证及首次失败

- [原8项边界检查](../runs/diagnostics/fixture_audit_alignment_20261024_v1/driver/old-boundary-tests.log)
  在旧代码出现6个fail、3个error（含nonstring subcases）；修后8项通过。
- [407项关联检查](../runs/diagnostics/fixture_audit_alignment_20261024_v1/driver/associated-final-tests.log)
  通过，覆盖真实freeze、candidate/fixture author、财务测量、更新/准入、
  seed、modality migration、Plan/core消费者。重叠批次不相加。
- [独立候选审查](../runs/diagnostics/approved_financial_publication_20261024_v1/independent/fixture-audit-candidate-review.json)
  核20组边界与原candidate行为一致、11份批准fixture两入口通过、当前seed
  安装/冻结14项正控通过；原18项仍9项拒绝，原Registry198文件保持。
  74次纯通用fixture batch，0真实GPRE/生产角色/发布/外网/标签。
- 独立比较7个财务kernel、解析与共同classifier的AST同原基线；没有改测量、
  分类阈值或准入政策。LLM skill/override、wrong issuer、nonstring、PIT/
  future、技术失败与domain状态的反例分别保留。
- 首296项关联检查有1个既有modality测试错误：两份测试作者fixture缺CIK，
  [旧审计原体重验](../runs/diagnostics/fixture_audit_alignment_20261024_v1/driver/old-modality-fixture-baseline.log)
  也失败。只为这两份新建合成测试明确写body和metadata CIK，原数值/预期
  不改；没有让共享helper猜值。另36个seed subcase原来断言旧泛化错误
  文案，改为断言明确validation_failed，原executor状态断言保留。
  两项独立review harness错误与最初日志也保留。

当前seed的14项成功不替代原冻结18项。历史9份缺issuer证明与审计适配器
漂移是不同问题，代码修复不能把它们一起报成“发布已恢复”。

## 当前真实输入与下一步

[当前完整输入预演](../runs/diagnostics/classification_fresh_consumer_20261024_v1/input-only/result.json)
重新核whole-bootstrap、同一真实runway测量/两个operand及实际分类声明，
1847来源绑定不变；停止在Reflect request-ready，未生成inbox或角色答复。
旧消费者235851/4次消耗完整保留，只余20149/1次，不能派发完整新链。

已将新增固定验收额度与受限Registry修复迁移整理成
[两个待决方案](mvp-next-boundaries-20261024.md)。等待明确资源/接口决策期间，
不重入旧stage、不修旧fixture、不重置额度、不运行替代简化探针。

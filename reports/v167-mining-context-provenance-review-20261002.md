# v167 Mining 必要输入与来源关联修复

本次完成隔离实现和实际材料离线验证，尚未通过最新代码的完整真实 Fast/Slow 验收。
真实运行仍位于 `/Users/l/Project/Recommandation/runs/cold_start/minimal_rounds_v167_integrated`，
冻结 source revision 为 `8c07f38333002db8bcbe639b3a28e3d197c49672`；运行中未替换其源码。
本次隔离实现基于 `d668a5d3`。固定24案两份 Plan 的 Binary F1 为
.7586206896551724 / .7200000000000001；不改样本、标签、分母或最低 .60 要求。

## 从输入到读取的共同机制

Signal 默认工作卡现在从精确版本的原始定义投影能力：输出 schema、执行方式、
取数条件、期间/比较要求、参数及 modality，而不是仅提供名称和一句描述。
卡片按完整条目分页；遗漏、游标、原始 bundle hash 和读取大小向模型披露。
现有 `inspect_catalog(scope=signals,item_refs=...)` 按精确版本读取整个 `{spec,skill}`。
与需求原文读取共用完整条目选择器：去重选择、未知 ref 拒绝、16KB 上限、
不截断、不猜版本；只掩码模型视图，保留源 hash 和 `content_is_masked`。
保持现有 light 预算与 Registry/候选验收边界。

需求默认卡披露原案例与当前 dev 的匿名关系，以及实际已知的预测时间；
来源未知、时间未知、超出当前 cohort 和部分重合均有明确状态。
同时提供当前 dev 的真实截止时点。来源24个 Fast 案例与本次8个 dev 案例
不重合，因此当前样本缺少某发行人的资料，不能证明原需求的发行人没有披露。
缺失来源时间不从案例名称猜测。共有规则要求保留测量、比较基准、主体层级和
时间限定；部分覆盖须说明未支持的部分，目录/局部读取也不证明全样本不存在。

共享输入检测在 transport 前要求 Mining 的匿名案例 refs、预测时点和目录披露
封套，避免提示词要求的信息被输入构建器遗漏；领域 validator 仍拥有证据权威。

## 证据身份与增量保存

新 fact/event ref 包含案例作用域。event 身份还独立于查询摘要长度，避免
共享同一文档的不同预测截面相互覆盖、同一案例改变检索词则凭空变成新证据。
目录保留每个文档/hash的全部 `(case_ref,event_ref)` 关联；event read返回所选案例，
document read返回已取到的全部案例。已读范围 receipt 合并案例范围并保留次数，
随后目录操作不会抹掉关联。标签仅由原有 Slow label map 提供。
同一原文只扫描一次，再按实际案例关联投影属性；纯缓存仍可清空重建。
历史 event/fact refs、请求、已保存处置和原始来源均不迁移或重写。

## 实际材料验证及范围

[离线来源回放](v167-mining-context-provenance-replay-20261002.json) 读取原始
v167 Registry v7、原始 capability backlog、冻结 Discovery 案例和99份本地来源，
使用原来两份有效付费 fetch 动作，通过新的生产工具在新 ref 命名空间验证：

- 18个精确版本 Signal bundle 全部可读/hash一致。分成14+4两批，均在16KB上限内；
  加上一次需求原文读取，light仍剩1；两次取数及一次结构化读取后heavy剩25，三次叙事读取后browse剩21。
- 四个已确认存在语义替代问题的需求保留完整限定，并披露来源不在当前 dev 内；
  截止时点来自实际 Case，而非模型推断。
- 66个取到的叙事目录条目均能连接到已产生的案例/event；三个实际原文读取保留
  案例和 verbatim hash；另一次实际结构化数值读取保留案例、来源文档/hash及可用时点。
  99份来源文件 hash 不变，Registry仍为v7。
- 首次属性摘要约2.65秒；之前去重/缓存机制仍生效。

重建初始工作输入约22.5KB，历史约25.5KB；附加记忆/需求集合不同，这两个
总大小只作描述，不是同输入的优化比例。精确工厂测试另外验证 Registry定义
和读取结果确实抵达 MiningAgentRoleModel 的实际 caller payload。
新增5项来源/身份回归，同时更新精确工厂和真实 transport 缓存测试的必要输入。
198项 Mining/Engine/来源专项和1,363项全量回归通过，lint PASS。

## 仍待实测

输入缺口已经局部闭合，不能据此认定模型会正确处理每个复合需求。
原来四个语义替代错误、51条未证实的 cohort absence 和既有 staged intent
仍保留原始历史；离线回放不把它们改判为正确。新代码需要真实模型输出、
完整 Slow（含 Update/候选合法跳过理由、提交及后继消费）和 Fast 再验收。
最新 live 指针/进程需按当前实际状态检查；这里不把运行进展当作代码验收。

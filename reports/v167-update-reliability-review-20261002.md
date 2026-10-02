# v167 Update 的程序修复与完整校验

源运行 `/Users/l/Project/Recommandation/runs/cold_start/minimal_rounds_v167_integrated`
冻结 `8c07f38333002db8bcbe639b3a28e3d197c49672`，Fast/Slow 已提交1/1。
这次修改不重写该运行、标签、Registry或付费请求/响应。固定24案旧F1
.7586206896551724/.7200000000000001 不是新代码实测。

## 实际问题与共同机制

请求 `5f8b916b1c7d6c15c36afeba5d048ce993bb8cae58e956fa3a00ba77f7f20248`
的case-001/003第二个fact都改变JSON字段顺序并重复相同数值/类型的`fy`。
之前仅用普通JSON解码判断“只有字段顺序”，掩盖重复键；现在严格核验。
共享修复选择器要求完整对象/数组等价、字段集合/值/类型一致、同case/document下
唯一的无重复key原文。重复引用键仅在每个值/类型一致时允许；冲突、缺字段、
非有限值、数值类型变化、跨case或多种字节原文均不获程序修复权限。

owning validator 为两个exact_span签发typed leaf替换。changed_paths还多报
`spec.parameters`与`spec.raw_retrieval.minimum_observations`；候选基础校验通过
后，validator为该无效元数据容器签发唯一实际diff的替换。二者通过同一个
snapshot-bound补丁引擎在LLM之前执行，完整parser每次重验，剩余错误携带修复后的
baseline继续。旧Update末尾的单独diff兜底已删除，避免并行修复路径。

Update的LLM纠错同样使用既有增量补丁协议。嵌套gap删除是精确member操作；
缺失case只授予现有数组的有界append，空必需rationale明确授权无效容器替换。
允许的模块替换在离线完整输出fixture中编码为原子操作，仍保留越权修改作为
拒绝的操作，不能过滤掉漂移制造成功。标准持久化v2决策和不可变fixtures不变。

deterministic description概念词要求移到同一表，由Mining/Update真实生产
candidate_contract披露，validator使用同一表。现金流公式的正确描述可以通过
已有误标检查；程序不补关键词、不改模型定义。概念词匹配仍只是有界检查，
不能证明研究语义正确，公式和fixtures继续独立校验。

## 三案实际内容审查

三个诊断都声称没有可比的上年operating cash flow，实际输入都有对应记录：

| case | concept / unit | current duration / val | prior duration / val | filed / prediction |
| --- | --- | --- | --- | --- |
| 001 | us-gaap NetCashProvidedByUsedInOperatingActivities / USD | 2024-01-01..2024-12-31 / -6987201 | 2023-01-01..2023-12-31 / -7160538 | 2025-04-22 / 2025-07-31 |
| 002 | ifrs-full CashFlowsFromUsedInOperatingActivities / USD | 2024-07-01..2024-12-31 / -2588886 | 2023-07-01..2023-12-31 / -802732 | 2025-03-19 / 2025-05-30 |
| 003 | us-gaap NetCashProvidedByUsedInOperatingActivities / USD | 2025-01-01..2025-06-30 / -27774000 | 2024-01-01..2024-06-30 / -13271000 | 2025-08-06 / 2025-09-30 |

adapter现在把已执行锚点与同文档/同concept/unit、确切上年日历起止的记录组成
可见对照，明确发送给模型。对照保留原records下标，避免重复发送literal原文。对应的显式不存在声明得到gap leaf的replace/remove
权限，LLM须修正事实描述；程序不代写研究结论。若insufficient的所有gap均被
证明错误，还显式授予evidence_verdict的replace-only依赖权限，避免要求模型编造新gap。文件是否缺其他内容、经济可比性、
未来催化和未知同义词并不由该有界availability检查证明。所有原始literal仍可引用。

## 完整验证结果与边界

[零网络真实响应重放](v167-update-literal-repair-replay-20261002.json) 复用原始响应，
绑定生产`_validate_update_candidate_for_role`和真实v7 Registry/validator。
它恢复两个引用及diff后，首个LLM反馈含三处错误的缺失声明和candidate fixture错误。
三份不可变fixture只有1个period/0天span，候选却要求2 periods/365天span，因此
positive/neutral/negative期望均变unavailable；完整校验正确拒绝。第四个unavailable
fixture并未被改写。候选“原fixtures已满足新要求”的自然语言声明不能覆盖执行结果。

报告第二次响应是明确脚本化的native无操作delta，用于证明部分程序修复保持且
未解决的语义/fixture错误仍失败；它不是新LLM行为或模型质量证据。初始适配、补丁
归并和确定性fixtures已覆盖，完整生产工厂的candidate契约由engine测试覆盖。
整个新Fast/Slow、真实增量纠错、跨周期消费和幅度预测质量仍需后继运行审查。

新增13项回归；12项source/patch专项与1,384项原生全量通过，lint PASS。

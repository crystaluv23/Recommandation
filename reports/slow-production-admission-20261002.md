# Slow生产技术准入迁移与可靠性验收（2026-10-02）

本次把已批准的“技术正确先入库、效果持续观察”接到生产 Slow 决策、Registry 发布和 Fast 输入。完整目标仍在进行：真实新周期的近零技术排除率、持续 target 评价生产写入及 magnitude 独立增益尚未验收。

## 技术排除与评分

冻结 v168 第二份固定24案中有4个技术排除（16.7%），其中1个正类形成技术FN，另外3个为负类失败占位。不能把这4例从评分分母删去，也不能因恢复成功而预先认定预测正确。详情及四份原付费最终答重放证据见 `v168-runtime-reliability-repair-20261002.md`。该证据证明已定位的校验误拒家族可恢复，不代表最新代码完整周期已达到零排除。

共同问题是生产者提示、校验器的解释和修复权限未完全一致：正常否定范围、市场预期分析及跨价格关系被误拒；局部修复也无法修好不合理的检测目标。共享修复必须和统一词汇、准确错误范围、完整复验及保留失败诊断一起验收，不能只增加重试次数。

## 本次生产改动

- 方向、magnitude及Update新版本走同一技术准入：完整结构、PIT/来源/语义、真实执行fixture、版本和重复检查通过才可发布。新候选没有额外效果数量门。
- 准入前不执行配对效果调用；因此独立实验的预算、网络或缺样本不会阻断有效因子入库。技术检查自身的控制/提供者异常仍按控制面处理。
- accepted检查点只在候选内容、输入Registry、实际validator/executor与模型策略、目标均完全一致时复用；失败候选继续检查。当前批次内语义/执行重复拒绝。
- 原子transition仍绑定exact candidate/admission key；中断后按原批次恢复。旧effect评估及历史transition不改，旧provisional候选有界技术复验；删除旧池化晋升引擎。
- 每个版本保存技术准入及原生成样本来源；后续独立研究继续排除生成/induction样本。vNext继承measurement用途，效果保持未验证。
- 实际Selector、H_reflect及最终Predictor的compact signal_rounds都会收到当前版本“效果待验证”；历史无新metadata的消费者兼容，回顾标签和样本来源不会披露给盲预测。
- 独立effect记录单独保存成功或失败观察，不能改写准入、不能伪造0样本或收益。接口已测试，生产持续观察写入仍需接通。

## 验证及限度

实际v168已物化的 `revenue_growth_yoy:v3` 在临时Registry副本重放：只注入已完成上游的候选收集，生产 `_validate_cycle`、真实fixture、独立准入、原子发布、重启读取及发布后SignalExecutor均未替换。1/1技术fixture通过、v3发布并保持effect unverified；旧无增益effect记录保留，源signals/candidates逐文件hash不变，外部调用0。机器证据：`v168-production-admission-replay-20261002.json`。

完整周期集成测试覆盖技术发布中断/恢复及后继Fast；方向/magnitude/vNext、错误fixture、重命名重复、检查点复用、effect失败隔离、原authoring lineage、实际模型输入披露均有回归。最新专项7项PASS；最终1426全量测试PASS（47.595秒），repository lint PASS。配对纯评估器仍有独立测试，旧冻结研究证据保持可读。

这些测试证明生产接线和确定性技术契约，不能证明新LLM Mining的内容质量、最新完整真实周期排除率或因子收益。固定提示允许未验证measurement被考虑，但不强制把预测改成更大倍数。

## 下一前沿

1. 把已提交Fast使用轨迹接到version/target绑定的持续观察ledger，区分选中、执行、可用、决策关联和独立收益，避免同case多Plan重复计效。
2. 基于不可变输入重放受影响Fast/Slow前沿；必要时最小真实外部调用，审查逐阶段实际请求、产物与后续消费。
3. 取得方向/magnitude真实新候选入库及后继使用；用固定cohort的独立对照检验幅度区分，不把“调大倍数”当作改善。

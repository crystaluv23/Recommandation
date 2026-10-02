# v170 提交后 Signal 使用身份与恢复

2026-10-02。可靠性和 Slow 双轴产出目标继续，技术排除尽可能为零。

v170 冻结 ab63de3b，Fast 指针1、Slow0。c02已完整24案提交，却在衍生学习记录阶段遇到7个同ID异内容冲突；旧值全部来自v168。旧ID只绑定本地轮次、Plan名称及使用位置，跨工作区复用plan_r0001_c02时无法区分来源。Registry拒绝覆盖旧值正确，不捕获并跳过冲突、不删除旧事件。

## 修复契约

先更新 owning specs。共享生产者的新v2事件身份绑定canonical immutable PlanRecord哈希、案例、精确Signal版本和原Signal轮/结果位置；事件携带source hash/position并校验ID。不同执行记录不再因同名碰撞，canonical恢复和原样复制身份相同。执行统计也采用同一源记录命名空间，避免新事件可写但统计被旧slot静默抑制。

v1 canonical形状和身份原样保留，导入/后继导出不转换旧事件，不在冻结旧run内重新派生v2并混写。新 committed-Fast bootstrap 在新工作区从不可变源记录派生v2。物理observation_key与target evaluation去重身份不改，重复选择不是独立因子效果证据；同ID异内容仍拒绝。

## 实际完整生产衍生重放

[机器证据](v170-signal-use-identity-replay-20261002.json)从真实contract/pointer恢复唯一提交c02，用生产producer、PlanEvolutionEngine的恢复构造和shared tracking写入，在临时Registry验证。旧v168274事件全部逐条匹配其pointer-reachable源记录（按原v1身份投影），保留原序列化。

- 旧规则准确复现7个冲突；新v2134事件与旧274事件共存，合计408，0身份冲突。
- 真实canonical记录round-trip生成相同新事件；原Plan记录SHA与canonical source hash分别记录。
- 模拟target derivative写入中断，生产Fast恢复补齐；第二次恢复事件、target bytes及learning hash均不变。所有旧event ledger原前缀保持。
- 生产build/validate/apply_slow_bootstrap_manifest派生134事件与Fast producer逐条相同，不再次新增已导入事件；1条原meta恢复。预Slow边界仍从源指针与hash核验，没有复制源完成指针。
- 原408选择事件合并后218物理观察、29争议观察；争议保留、效果unverified。不能当408个独立样本或因果增益。
- 0外部调用，原source contracts/pointers/records/meta/ledgers全部hash不变；这是衍生恢复验收，不能算新Slow周期完成或新因子入库。

新增4个跨工作区、v1/v2、精确冲突及中断恢复回归；88项相关测试PASS，1458项全量PASS（86.845秒）。repository lint PASS，完整输出已读取。

## 下一前沿

v170剩余正类技术排除的实际Reflect输入同时含相似的untargeted need0和targeted need1。付费native patch删除need1并保留need0，但cosmetic guard跨所有当前需求匹配，把必须保留的need0误认成need1的伪装。独立语义/来源义务仍需完整验证；后续修复应限制cosmetic检查只匹配未分配给保留/精确residual义务的剩余occurrences，不能宽免真正新增的伪装需求或删除untargeted反证。双轴新候选真实产出入库、后继消费及近零技术排除仍未验收。

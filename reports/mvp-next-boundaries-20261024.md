# MVP 下一步的两个实际边界

本轮已按当前真实产物复核。两个待决定项分别是资源上限与 Registry
修复接口；它们不改变研究测量、评分、PIT、失败分母或效果标准。
AGENTS.md 将资源边界和 canonical 接口/准入政策的实质取舍交给用户。

## A. 修后分类消费者：独立固定验收额度

旧 financial-context-consumer 已完成，语义0/1保留。真实累计为
61888初始化＋49144路由＋57862 Reflect＋66957 Predictor＝235851，
4次调用；原上限256000/5次，剩20149/1次，不能再跑完整两角色链。
MVP goal active/unbounded 不自动重置这个 case 的合同。

[当前代码的真实输入预演](../runs/diagnostics/classification_fresh_consumer_20261024_v1/input-only/result.json)
已完整重建原bootstrap，并实际计算同一runway v3，数值和原成功结果一致；
执行器实际sidecar进入完整Reflect请求，逻辑预留59446，Predictor估算
62262/62262/65303。全部在request-ready、cache/receive/inbox前停止，
0角色答复/0新外部API/0标签；这是输入与估算证据，不是F9语义通过。

建议授权一个修后固定消费者验收，新增预算最多144968逻辑单位及3次
角色响应（Reflect、Predictor及两者共享至多一次纠错）。原235851/4次
作为不可变历史债务保留；跨两次消费者的累计上限为380819/7次。
本次原生case实例仍计入原H_init/route111032/2次，其上限仍256000/5次，
单请求131072和finalization reserve64000保持。共享原H_init/route只计
一次历史消费，不重复生成，也不清除旧消费者的124819/2次新角色成本。

冻结原5个needs、context-only权限、同一来源/版本/阈值、当前代码和
[条件性独立oracle](../runs/diagnostics/classification_fresh_consumer_20261024_v1/independent/conditional-consumer-oracle.json)
后才派发。通过须有真实首答/纠错、分类含义正确、原需求保留、完整
最终上下文及预测sink；沉默不等于已理解分类，方向/概率不设答案。
失败/预算止保留终态，不追加样本、换目录或增加调用求过。旧0/1不改。

## B. 历史 Registry：显式受限修复事务

两已批准财务版本的正常发布准备实际被完整18项能力审计阻断：其中
9项历史财务fixtures缺body和metadata CIK。原审计在此应继续拒绝；
不能猜CIK、改写旧版本测试、拿新seed的14项替代原18项或绕过freeze。
另外发现的候选/发布fixture适配器不一致正在单独修复；修好该代码
也不会补出历史缺失的身份依据，不能据此宣称原Registry已可发布。

建议批准一个明确的`capability_repair`本地迁移接口，随后先细化spec，
再实现、反例审查和运行。范围仅为另建的后继Registry：

1. 输入保持原v12/18版本与全部原件hash；预先冻结9个disabled refs及
   缺身份的具体原因。普通`promote_validated_batch`的健康输入要求不变。
2. 新的受限入口允许该已知不健康基线进入**修复准备**，须为每个disabled
   ref提供恰好下一版本；不得漏修、删除Signal或偷偷改变其他定义。
   两已批准口径使用GMv4、accelv3；其余7项仅新fixture/版本，测量、
   参数、阈值、单位、期间和预期输出不改。旧版本所有文件保留。
3. 每份新fixture由作者明确声明合成CIK，正文/metadata一致，不冒称
   修复了旧记录的历史来源。所有候选走原完整validator、稳定/批内去重、
   非空全部fixtures及admission-v1；研究provenance保持真实/unknown。
4. 一次原子事务提交9个更新。输出必须通过原完整18项能力审计，才推进
   Registry版本和applied标记；prepared状态拒绝普通读取，恢复精确绑定
   原候选/准入key，错hash/漏项/更大范围失败均拒绝。原Registry不动。
5. 输出全部effect-unverified。new Mining count仍0；此迁移不证明S4、
   fresh消费、真实Slow完成、收益或MVP整体收敛。

这是修复入口与事务身份的实质取舍，尚未实现或放行。若暂缓，可保留
当前隔离候选与原失败状态，继续不依赖该发布的其他已授权验收。

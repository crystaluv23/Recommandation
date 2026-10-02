# v167 已提交 Slow 的状态与工具契约审查

v167 已真实结束，监督进程退出0，Fast/Slow提交指针为1/1。
源运行仍冻结 `8c07f38333002db8bcbe639b3a28e3d197c49672`，Registry v7输入/输出hash一致，
没有晋升新Signal。固定24案两份Plan Binary F1=.7586206896551724/.7200000000000001，
仍满足用户至少.60的要求。这是执行完成，不是完整内容验收。

[原始终点及逐请求审查](v167-final-slow-content-audit-20261002.json) 保留源结果文件hash，
没有改写原始结果、需求单元、请求或标签。

## 真实终点

| 轴 | 种子 | 真实 terminal | 原保存status | 新解释 |
| --- | --- | --- | --- | --- |
| direction | hypothesis | no_pattern_with_coverage | completed | completed，但语义/预算理由已有已知缺口 |
| direction | discovery | technical_failure | completed | failed |
| magnitude | hypothesis | technical_failure | completed | failed |
| magnitude | discovery | technical_failure | completed | failed |

幅度 hypothesis 保存137条独立处置，但仍有96个pending need refs；并未形成完整终态。
所有种子总计96次叙事读取只证明发生过读取，不能把三个技术终止变成研究结论。
旧 `magnitude_contribution.target_mining_assessed=true` 源于上层固定填写completed；
在没有幅度候选的情况下不成立。新读取解释为幅度failed/未评估，direction为partial。

Update实际尝试3个目标：cash_reserves:v3和cash_to_current_liabilities_ratio:v3通过物化，
都因缺少方向证据、超过半数正例未覆盖及无严格paired gain被拒绝；cash-burn更新在
literal facts及definition校验阶段失败，没有成为已验证的研究反例。最终0晋升，Registry不变。
后续需要核对cash-burn输入/validator兼容性；当前不能把所有未晋升概括为经济假设失败。

## 本次实现

运行时将候选/支持的no-pattern标为completed，技术失败标为failed，预算/证据延期
标为deferred；轴及多轴保留partial。Legacy读取优先解释真实terminal元数据，不重写历史。
Update只消费完整且独立完成种子的validated intent，兄弟失败不抹掉有效行；partial/staged
行和技术失败行不进入该消费入口。可用modality的分母保留全部机会，不因失败缩小。

三个实际 `compute_statistic(rule=median)` 输出暴露输入不披露冻结rule enum的问题。
现在模型每一步可见工具实际共享的三个规则、同案例两操作数顺序、数值约束，及read的
唯一目标字段/窗口边界/预算维度。shared input preflight要求这些契约存在；provider未被
添加不支持的原生schema功能。未知rule反馈列出实际枚举，不由程序选择另一种研究运算。

数值运算对非有限输入、零除数和非有限结果抛出typed ValidationError；失败不会写成功
relation或扣成功动作预算，已保存需求/事实保留。恢复测试先保存有效需求，再读真实
零值fixture，经零除拒绝和模型选择的受支持终态完成，保留正确增量单元与invalid ledger。
这只证明恢复契约，不证明脚本化研究终态具有实际效果。

显式维度预算数量及“positive/available”事实也对照运行时counter校验。动作预算禁用
先于该动作的错误预算理由，保持两次重复禁用后deferred_budget的既有控制规则。
免费terminal/disposition动作不被错误描述为只有record_deferred；证据及modality前置条件仍适用。
这些程序检查有明确范围，不会证明所有自然语言因果/控制推论。

新增8项工具/数值/预算/状态回归，206项专项与1,371项全量通过，lint PASS。
整体目标仍待最新代码的真实Fast/Slow产物、合法跳过理由与后继消费验收，不能用旧F1
或本地测试代替。幅度选择集中、原需求代理覆盖及absence问题也不因本次修复自动消失。

## 主目录整合与进一步定位

已在监督进程确认退出后将隔离检查点快进整合到主目录 `0ee86a83`；
主目录原生1,371测试通过，历史v167和用户已有v151产物修改保持。
进一步对照cash-burn请求 `5f8b916b...`：执行过的literal源已在输入中，
case-001和case-003的失败引用解码后与唯一原始JSON记录完全相同，仅字段顺序不同。
不能把它归为缺少输入证据；逐字校验拒绝有理，但尚未调用可验证的JSON引用
程序性复原。原记录value/time/fields不能由程序猜测、增加或改值；下一步应绑定
原响应及case/document scope，只在完整结构相同且唯一源匹配时恢复原始引用，再完整校验。
这个程序性修复尚未实现。另有case-001的“未看到prior”声明与可见2023年度现金流
记录冲突，以及函数文档和description关键词守卫未对齐的问题，须分别解决，
不能由修正引用格式推定整个诊断正确。

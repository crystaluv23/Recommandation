# 新代码验收的历史消费与恢复边界

本轮只完成验收驱动的本地修复，**没有启动正式v4验收、没有fresh生产作者或新Signal**。外部API、网络、provider GET、新业务标签、完整后继均0；工程MVP仍open。

旧v3在single262144边界终止，不能补h011。前两次修复已分别解决完整引用表示和真实query-origin导航；新代码重新验收必须保旧失败、同一来源/语义/分母和原额度。本轮把“保消费”落实到模型预算输入、真实提交硬限制、缓存重建、双seed与完成快照，避免新目录清零或恢复时重复扣账。

## 授权、固定输入与旧失败

[独立方案审查](../runs/diagnostics/mining_preserved_budget_20261023_v1/independent/initial-review.md)亲读用户采用的MVP附件第134行：允许修复后在新版本重新验收，禁止换样本、改答案或追加调用。因此不重复请求已有许可；新代码版本的验收与恢复旧终态分开。方案审查不是实现独立通过。

[父确定性核验](../runs/diagnostics/mining_preserved_budget_20261023_v1/preserved-inputs.json)重新核三个旧控制的真实wire/原答/receipt、source/archive绑定与封存。v1保12次/2,001,316、h013未答；v2保11次/1,837,419、h012未答；v3保10次/2,055,941，无第十一份inbox。三个历史合计33次/5,894,676逻辑预留，不是host tokens或货币成本。v3仍312封存hash行、316全文件；263原始来源、18定义绑定和三份旧oracle的已提交原字节均同。

新分支继承v3的资源债务，不改写前两控制的独立合同：

| 范围 | 原上限 | 不可撤销已用 | 可供新回答使用 |
|---|---:|---:|---:|
| Mining calls | 80 | 10 | 70 |
| Mining bytes+output | 12,582,912 | 2,055,941 | 10,526,971 |
| Global calls | 728 | 10 | 718 |
| Global bytes+output | 58,720,256 | 2,055,941 | 56,664,315 |
| 每份完整请求 | 262,144 | 每请求约束 | 上限不变 |

263来源/dev8/原group与cutoff/stable18/完整265needs/六披露、方向语义、PIT、身份及固定候选1/消费者4均未改。不能将这些本地绑定或资源余量称为候选成功、技术准入、精确消费或独立收益。

## 实现与反例

先改[owning spec](../spec/scripts/run_icfr_native_capability_stage.md)，再改驱动：所有旧三root及其解析后的路径拒绝执行。新合同绑定原v3 terminal/archive和实际已答身份/成本；每个gate核真实原件，缺失、改值、归属错误、未答混入、bool/负值或嵌套历史前缀均拒绝。`Budget.records()`仍只列新回执；`used()`合历史与新回答，旧身份不能进入新缓存，global与Mining均扣原消费，candidate/Fast不另扣一次Mining债务。终态单列历史/新答/合计逻辑消费。

同一native Mining model每次进程重建只初始化历史前缀一次，之后按本地cache原顺序计入；新运行usage从0开始，不伪造历史host usage。双seed共用该model。完成seed保存其新答快照及累计reserved；保存和恢复两端必须等于历史加该快照，另有不可变receipt绑定已接受checkpoint的精确字节。后续receipt不能倒灌到早期payload；较早checkpoint遗失而目录已有未来答复时明确停止，不能把未来成本伪装为早期前缀。

首次22项旧阶段测试通过。新增首四组有一条harness失败：误把传输初始化的空目录当作答案导入；第二次仍误把合法`exchange/contract.json`当答案缓存。原日志保留，断言改为核实际inbox/outbox/receipt/cache内容后四组通过。不是两次产品缺陷。随后扩展global/Mining exact-fit与超一单位、malformed原答真实扣费、双seed两份答复后按序重放、快照reset/混入future及早期checkpoint遗失；全部通过。

前版497关联通过后，父自审追加“快照与计数同时改为后来已答集合”的反例，旧检查确实漏过（[首失败](../runs/diagnostics/mining_preserved_budget_20261023_v1/joint-checkpoint-rewrite-before.log)）。只比较两者等额并不能证明它们是原先接受的那份快照；补不可变checkpoint hash receipt，并验证receipt缺失、共同改写和原生双seed恢复。修复前关联日志/bindings与preserved-inputs分别另存`*-before-checkpoint-binding`。这是一处真实本地恢复保护缺口，区别于前两条harness错误；不是独立实现审查发现。

最终[497关联测试](../runs/diagnostics/mining_preserved_budget_20261023_v1/associated-test-bindings.json)通过，测试前后源码hash同、socket tripwire0。真实263来源/18版本/265needs的临时native prepare/input-only/pending控制也在其中：首payload披露已用10/2,055,941，重复进入hash相同，新增回执0。该临时fixture只重绑旧oracle的当前代码字段，无生产作者；没有修改三份旧oracle，也没有创建正式`oracle-v4`或`stage-v4`。

首次lint被拒是父在最终测试尚运行时提前stage了部分日志：最后一行`... `未写完，含尾空格。精确被拒index字节和已亲读feedback以gzip无损保存，见`first-lint-packaging.json`；等待进程完成后重新stage完整日志，不修改历史输出凑PASS。该错误不改变测试或研究结论。

## 资源阻塞与声明限制

方案独立审查完成后，工具在续接实现审查和新建只读审查者时均返回 **`agent thread limit reached`**。当时枚举有三个历史`pending_init`子节点；中断它们后续接仍返回相同上限，新建一次也被拒绝。没有绕过限制、借别的入口派作者或调用外部API。

所以实现层目前只有父测试/确定性自审，**独立实现反例审查未完成，fresh模型验收未开始**。不据此冻结正式v4 oracle/创建stage/增加任何生产回答。值得继续的下一步仅在subagent服务确实恢复后，先补实现独立反例审查，再冻结同一义务与不变资源账户，随后才给fresh节点精确native inbox；不得重开旧v3、重置额度或用脚本替作者。分类canonical A/B决策、完整方向/magnitude候选链、Committed S8及双环恢复仍待。

# 保留消费的新代码验收：初始只读审查

审查基线：HEAD `330ecb81cfcb1cf2d0af6fa7399fcf4662428642`；读取了用户所附MVP全文、AGENTS、agent-workflow、现driver及owning spec、v3终态和全部十份原生inbox/outbox/receipt。审查过程中父正在spec-first准备v4草案；本文审的是资源合同方案及现有连接风险，不是对尚未冻结实现的通过结论。没有运行prepare/advance/submit、生产节点、provider、网络、LabelStore或旧stage入口；只新增本报告。

## 结论与授权依据

**该方案原则上在已有用户授权内，不需要重复索取“修复后新版本重新验收”的许可；前提是执行的是严格保留旧消费的、预先冻结的新代码验收，而非恢复v3或另开一份完整余额。**

授权依据不是spec/status的自述。我亲读了用户附件
`/Users/l/.codex/attachments/0b5917f1-3c17-43f0-aeb0-e16e3e449e45/pasted-text-1.txt`，其第134行明确：

> 修复后可以在新版本上重新验收，但必须保留旧失败。不能不断换样本、改答案或追加调用，直到出现一次成功。

父提供的直接用户请求为“/goal 按照该MVP收敛验收标准迭代吧”，并提供最近“不调用外部api、LLM节点由subagent处理”的直接授权上下文。因此，新代码验收本身已有许可；本次只读审查没有独立检索完整聊天或目标服务当前状态，不能代替派节点前对更高层usage/budget限制的核实。

AGENTS第52–55行要求旧完成/冻结状态保持、目标资源限制立即停且不得换名恢复；agent-workflow第98–100行禁止借新目标绕过usageLimited/budgetLimited。两者与上述用户新版本验收条款可以同时满足：v3永久保持终态；v4不得继承其执行状态、答案或缓存，只继承不可撤销的历史资源债务；各次新请求仍受同一原资源上限约束。若存在更高层目标服务资源限制，v4也不得绕过。换目录、换演员或改宣称均不能单独建立这个区别。

本案v3触发的是**一份完整请求超过single cap**，而不是已用尽aggregate/call余额。原失败仍是失败；无损引用表示和真实query-origin连接修复，是可以区分的新代码变量。修复后的脚本请求能装入single cap只证明前提，不证明新模型规划、候选、准入或消费者已经成功，也不能成为不断重试直至成功的理由。

## 独立核定的原始资源事实

本次重新逐十份receipt核inbox与原答hash，以完整messages的compact/sorted/UTF-8 JSON字节加实际output allowance求和：

| 项目 | 原上限 | v3已答消费 | 可用于v4新增回答的剩余量 |
|---|---:|---:|---:|
| Mining调用 | 80 | 10 | 70 |
| Mining逻辑预留 | 12,582,912 | 2,055,941 | 10,526,971 |
| Global调用 | 728 | 10 | 718 |
| Global逻辑预留 | 58,720,256 | 2,055,941 | 56,664,315 |
| 单请求 | 262,144 | 每请求独立约束 | 不增加 |

旧十份inbox/receipt齐全；没有第十一份。completion仍为`terminal_resource_or_control_stop / MiningRequestBudgetExhausted`，固定candidate分母1、consumer分母4不变。312个completion绑定hash均通过，当前共316文件。这里不把旧progress里最后一次pending标记当作可续执行授权。

v1/v2的12/2,001,316及11/1,837,419继续独立保留；三个旧版本已答历史合计33次/5,894,676，不能在成本汇报里消失。拟议v4资源账户继承v3这一已明确冻结的分支，不应暗中改写v1/v2原合同。也不能把新账户的10/2,055,941说成整个MVP历史总成本。上述数字是逻辑bytes-plus-output预留，不是host模型tokens或货币成本。

## 最小可靠实现

1. **一个不可变历史资源prefix即可。** 新contract/manifest绑定v3 completion、原runtime archive及十份原生request/inbox/outbox/receipt/scope证明；通过现有Budget.records校验实际wire/hash/answer identity并重新计算成本。记录精确10/2,055,941及global+mining归属，不仅保存两个可任意改写的总数。缺失、重复、改hash、错误scope、历史root漂移均fail closed。旧三stage的所有mutating入口继续拒绝，不能调用原advance以取得这个prefix。
2. **历史资源与新执行分开。** `used(global)=historical+local unique answered`；`used(mining)=historical mining+local mining`。历史不计入candidate/Fast子scope，但始终计global。新request身份与历史身份重合直接拒绝，不能当免费cache命中。只从旧原答文件核hash，不将其内容、action sequence、controller ledger、候选或语义笔记放入v4作者输入或新cache。合同中可保审计绑定，生产作者只需正常预算状态。
3. **双seed共用一份预算状态。** 原生axis只创建一个MiningAgentRoleModel，再为hypothesis/discovery分别建controller。每次新的进程重建将这个共享model的reserved计数初始化为历史prefix一次；不能每个seed加一次，也不能第二seed重置为10/2,055,941。hypothesis保完整265needs，discovery保原生空backlog；每个seed的工具预算按原合同，不挪用light/heavy/browse。两seed合计仍是80/12MiB。
4. **恢复按有序本地prefix重建。** model初始只有历史10/2,055,941，再按本次真正经过的v4原生cache答复逐条消费。Budget的全目录记录可用于实际入账上限检查，但不能在重放首请求前灌入model payload counters；否则较早request hash会变化，形成额外作者请求。已答本地cache重放不能重复入账；pending/pre-dispatch阻断不算已答，malformed/identity-rejected真实提交仍算。
5. **完成seed checkpoint不额外追加历史消费。** 快照明确区分历史prefix、已顺序消费的v4 Mining身份/成本与新运行usage；恢复累计reserved值必须等于历史加该本地快照。赋值恢复，不是再次`+= historical`；不得包含后来receipt。最小防线是在保存和恢复两端都核model累计计数与快照一致，可直接使用已有model request trace限定实际消费身份，不需要第二套通用账本。原driver完成seed恢复会直接赋model_prefix，新增初始化必须与此保持同一个定义。
6. **原scope gate贯穿所有阶段。** 每次dispatch前按真实完整消息检查single/global/当前scope。S5/S7和Fast各有原上限，不继承H1额度；global仍扣历史前缀。精确边界允许，超一单位或第81个Mining已答应在receive前硬停，不走model内容纠错。input-only只证明原生首请求与预算连接，不新增已答消费。

当前草案顶部仍称“new diagnostic host ceilings”，而后文明确继承旧上限，容易被读为新余额。建议最终spec用“本次继承的不变diagnostic ceilings”消除歧义。checkpoint条款也应明确快照是**仅v4有序本地身份**，累计计数才是其与历史prefix之和，避免双加解释。两者是实施表述修正，不构成新的用户决策。

## 冻结/派节点前必须能拒绝的反例

- 历史prefix缺失、零值/负值/bool冒integer、只填声明总额、删一个receipt、同一receipt重复列出、额外pending算成已答、原wire/output allowance被替换。
- global漏扣历史、Mining漏扣历史、反而扣两次；把历史消费塞到candidate scope；第一次seed正确而第二seed重置或再加prefix。
- 新本地request复用历史身份，或复制旧outbox/cache使fresh演员没有实际作答；不同新请求却因内容相同被合并为一次物理回答。
- 已有本地h1/h2/h3答复时，从prefix重放h1必须得到原预算字段和原request hash；不能一开始用prefix+h1+h2+h3作h1的used。重复replay/重启不增加实际unique consumption。
- hypothesis完成checkpoint→discovery pending→重新进入时，hypothesis快照不含discovery将来成本；恢复后首次discovery请求必须逐字同。遗失/篡改checkpoint或将全部未来receipt塞进snapshot必须拒绝，不默默修成一个新prefix。
- 第一次input-only捕获后0新receipt；malformed或identity错误的实际答复被计费；未dispatch的预算拒绝0新receipt。exact-fit可过，cap+1、call+1均前置拒绝。
- v3 completion仍存在时直接advance/submit/h011、通过软链接路径别名写旧root、prepare覆盖已存在v4、复制旧active_cycle/验证半成品或改旧oracle，全部拒绝。
- 同263源/stable18/dev8/原group及cutoff/完整backlog/六披露、原source/PIT/身份屏蔽/Signals覆盖和固定1+4分母不变；不得给新作者私有答案、研究坐标或脚本假设action。
- 若这次新版本再次达到原资源限制，保留终态与剩余未知，不能再靠v5 fresh余额重开。当前实现若不支持传递历史prefix，应明确拒绝nested继承；不能只取v4 local成本而漏掉v3债务。

结论限于**方案在既有授权内且资源守恒路径可实现**。尚未做v4实现反例、native双seed/replay、input-only或freeze验收；这些检查完成后可依既有授权继续，不需要另设用户审批。若任何权威状态、固定义务或资源计费矛盾，保持v4未启动，先处理具体冲突，不能靠修改记录获得PASS。

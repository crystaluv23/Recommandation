# v169 真实前沿：Plan 来源集合修复与 Slow 文案对齐

正在运行的诊断根目录为 `/Users/l/Project/Recommandation/runs/cold_start/minimal_rounds_v169_integrated`，冻结源 `1f26845df7a0f747a08133e46c5be6be92c2c6b9`，contract `ead055e1da52e2797777e46d71bc44d88912f467640c0a78ac85045891693019`。本文及本轮补丁在隔离工作区，不注入正在运行的代码，也不改原请求、缓存和评分。

## 已核验的运行状态

原进程退出 1，Signal 调用出现 `RetryableOpenAIClientError` / SSL UNEXPECTED_EOF。退出时 ledger 为 34 completed、1 failed，已记录费用 $0.10225572；Fast/Slow提交指针0/0。供应商异常传播到运行边界，没有被吞成因子不可用或预测 FN。同根目录、同冻结源恢复，继续保留先前完成响应；恢复日志为 `/tmp/v169-resume-01.log`。这是进行中运行，不是已完成研究或已验证低技术排除率。

最初两个保存的案例 trajectory.stop_reason 均为 finalized，预测 unlikely，不是 exclusion 会话；它们是中间工作产物，尚不是已提交 round。检查 guidance 的真实接受结果：明确比较基准缺失时返回 neutral 并披露不确定性；不能据此推断全部抽取正确。原始 Signal 回答中曾有一条引用范围或字面失败，初始失败与最终技术排除必须分别计数。

## 实际可修复缺陷

首次 Plan 提案把 10-k、20-f、10-q 用作 Basic Info source_types，超出封闭来源家族菜单。局部修正把它们替换为允许的值，却生成 `[filing, filing_body, sec_filing, filing]`。重复检查拒绝后唯一模型纠错机会已耗尽，该 Plan 被抛弃。来源类型是集合语义，重复并不增加覆盖；让模型再判断没有必要。

在共享 repair registry 添加 Plan 来源集合家族：只去除完全相同的非空字符串重复项，保留首次顺序和所有不同值。不转换大小写、不映射未知类型、不删除不支持的唯一类型、不修改其他请求或研究内容。Proposer 在原生补丁与 scope 验证之后、完整 Plan 验证之前调用同一注册家族，并输出精确修复操作。原始回答不变；坏成员、菜单外类型和语义问题仍交原校验器。

[真实响应重放](v169-plan-source-set-replay-20261002.json)复用原付费初始 JSON 和原生 patch（base_hash 原样匹配），通过生产 proposer、完整补丁/范围/Plan校验。仅 source_types 一处精确去重，其余字段逐项一致，原四文件 SHA 不变，外部调用0。这不是新模型遵循提示或新周期性能的证明。

## Slow 定义说明的漂移

生产技术准入早已迁移，但默认 magnitude_contribution.reason 和角色文档仍称只有方向效果门。默认现在只声明独立 Fast 消费效果未评估，技术入库不证明收益。已有显式历史理由原样读取，不回写历史。清理误导性的当前角色文档及 controller 说明；完整定义、标签、目标人群和独立收益要求不变。

## 验证

专项112项通过（修复、生产 proposer、routing 和 magnitude）。全量1,436项通过（88.568秒），覆盖新初始重复、纠正后重复、成员/顺序/兄弟内容保留及未知/坏类型反例；历史显式默认理由与缺省读取也验证。仓库 lint 在本轮隔离提交前运行。

剩余验收仍为：完成最新真实 Fast/Slow 并逐产物审查技术失败，真实新方向/magnitude候选入库、下一Fast消费、追踪，以及同输入独立幅度效果对照。没有把恢复/通过测试替代这些目标。

## 新出现的身份前沿（未修复）

恢复期间五份真实案例 trajectory 中出现一份 Initialize 技术排除：Morgan Stanley / MS，错误为 `model guessed target identity outside supplied tokens`。[原始三文件审计](v169-short-ticker-table-audit-20261002.json)证实模型输入证券登记表已有14处MS，失败输出的 exact_text 完整复制其中一段。短 ticker 匹配器在 `MS New York Stock Exchange` 上不匹配，却在同一支持项的 `stock symbol MS` claim上匹配，触发“猜名”。这是输入盲化遗漏与身份判断归因错误，不能直接怪模型。当前补丁未包含该新前沿，也没有消除这份冻结失败。

下一动作应对明确证券登记表/交易所关联位置泛化短代码盲化并核验实际出站、逆映射与合法引用，保留普通研究缩写反例，避免无条件屏蔽短词或放开身份防线。原数据、评分和失败诊断保持。最后监测恢复进程仍在外部调用，Fast/Slow指针尚未提交；完整验收继续。

终态补充：恢复进程随后再次因同类SSL错误退出1，handle与PID均确认终止。ledger最终72条（70 completed、2 failed），记录费用$0.22800092；六份案例trajectory、一份技术排除，round/cycle仍0/0。鉴于已确认出站盲化遗漏，本轮不再重启该冻结源发送新请求；保留原件，在修复后继中继续全目标验收。这不代表目标被暂停或已完成。

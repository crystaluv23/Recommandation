# 已提交导入反馈的共同消费边界修复

2026-10-02。对应已复现的[source/local轮次消费缺口](v170-bootstrap-consumer-frontier-20261002.md)，不改旧运行、评分、指针或原事件轮次。

## 修复范围

Signal tracking统一读取冻结run contract绑定的bootstrap/history manifest，校验envelope、manifest hash、event结构、重复ID和Registry逐条内容。无契约的导入、缺失/改变的事件、未知Signal和损坏JSON失败关闭。history绑定也适用于fast_then_slow后继，原Control仅按slow_only模式读取history的重复分支删除，转为共同reader，传递性导出与消费相同。

Registry共同选择本地cutoff范围与明确导入事件的并集。Slow usage、target summaries、Update learned profile/target use和Fast-cycle freeze使用此选择；源最高轮次不扩大本地权限。Update work fingerprint加入共同反馈hash，避免已有no_change抑制新反馈。H1仍不可读取target outcome摘要；观察仍unverified，物理输入去重规则不改。

## 实际证据

[机器重放证据](v170-bootstrap-consumer-repair-20261002.json)继续使用原v168/v170不可变源记录、生产producer/恢复、build/validate/apply bootstrap和实际SignalEvolutionEngine消费者。只有manifest明确授权的134条v2源事件进入Slow（此前0），17份target观察摘要进入来源目录（此前0）。临时库另有274条真实旧事件，但不在本次清单，本地Fast指针0下全部隔离。Fast bounded freeze恰含134条，重复冻结hash一致。导入/消费不追加既有事件或target records；原源文件hash不变，0外部调用。

原v170提交c02仍为固定24案F1=.6923077、2技术排除/1技术FN，Fast/Slow指针1/0。消费恢复并不消除历史技术失败，不代表新Slow产出或独立预测收益。

## 验证与剩余验收

189项相关测试通过；新增6项回归检查本地0指针、清单外/本地pending隔离、Fast部分完成后的cycle-start画像恢复、fast_then_slow history转出、篡改/缺失/无契约/损坏JSON拒绝，以及实际Update模型输入与no_change去重。最终原生全量1468项通过（91.062秒），repository lint通过。

下一步冻结继任，先实际执行未完成的Slow：保留原已提交Fast范围作为导入来源，审计direction/magnitude挖掘、技术入库和消费；随后用新代码完整Fast/Slow核验技术排除目标0。单测、已付费产物的局部重放和本次反馈消费均不能代替此完整真实验收。

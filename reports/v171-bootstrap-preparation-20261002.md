# committed-Fast 后继准备与入口验证

2026-10-02。源为`/Users/l/Project/Recommandation/runs/cold_start/minimal_rounds_v170_integrated`（冻结ab63de3b，Fast/Slow=1/0），目标为`/Users/l/Project/Recommandation/runs/cold_start/minimal_rounds_v171_slow_bootstrap`。源旧运行不修改，不再运行旧冻结代码。

新增诊断入口`--slow-bootstrap-from SOURCE`连接已有生产build/validate/apply manifest、DualLoop、SignalEvolutionEngine和技术入库路径。source/local commit权限保持独立。初始有序版本refs进入frozen input，Registry `snapshot_from_refs`重算不可变定义hash，用于出版后恢复时核验原输入，不继承动态画像或伪造旧hash。此前内部transition重建函数共用这个接口，不保留重复旧实现。

祖先spec补齐现有committed-Fast恢复路径，与用户确认的“已正确工作及时保存、增量推进”一致；rejected-gap路径仍只接受pre-label需要，committed路径不改变原Fast评分或blind披露。新契约仍单次Slow、零Fast、原技术正确性门和外部预算。

[准备证据](v171-bootstrap-preparation-20261002.json)：相同anchor16、Discovery16、validation8；原来源/标签清单和evaluation保持不变。definition-only seed v7/hash保持，0本地Fast指针，134条源事件写入manifest，未复制源可变ledger/stats/candidates。manifest hash与前轮生产重放完全相同`6ac4aa5e896ee45edc59b200e9a20d0ea386a43184b3119ddff62d2c3006a72b`。准备时0外部调用，尚未冻结执行契约或执行Slow。

新增3项入口回归（该模块共7项）核验实际committed producer、定义复制、源文件不改、换源/换seed拒绝、zero-Fast参数、负编号meta、两个真实引擎共用反馈、真实Registry导入；执行入口测试在DualLoop开始处显式拦截，外部I/O为替身，不能据此宣称模型Mining完成。193相关测试及最终1471原生全量通过（91.318秒），lint通过。首次测试夹具未创建Raw Info oracle identity被正确拒绝，修正夹具初始化后验证通过；未放宽生产oracle校验。

下一步在已提交、冻结代码下实际启动新Slow，审计每个paid请求/响应、纠错、候选、验证、publication与pointer。direction/magnitude真实产出/入库、后继调用和完整Fast技术排除目标0仍未验收；原v170两排除/一技术FN不修改。

# 整合验证与 committed-Fast bootstrap 消费前沿

2026-10-02。主工作区已fast-forward到539e4e5d，整合时间门、身份结果隔离、native patch机械纠错、source-bound Signal use及need occurrence误拒修复。主原有v151两份tracked改动diff SHA保持801b23f1102b5afd877abfbbf4ccfb2abecb48719fe577f01c5e32b639be8d03。原v170监督器和子进程不存在，不重启冻结ab63de3b。

主原生全量1462项PASS（86.356秒），仓库lint PASS；这是代码/重放验证，不是最新完整真实Fast/Slow或零技术排除验收。源v170仍Fast1/Slow0，唯一提交c02固定24案F1=.6923077、2技术排除/1技术FN，历史分数不修改。

## 消费缺口，已用生产调用复现

[机器证据](v170-bootstrap-consumer-frontier-20261002.json)重新走真实v168/v170源记录恢复、producer/Registry/target导入、production build/validate/apply bootstrap。新工作区保留空Fast指针0，源范围含134条v2事件；临时库连同已验证的旧274事件共408条，恢复不重复。随后构造真实SignalEvolutionEngine，使用实际批准Discovery/identity cases、rebased原meta及生产_committed_slow_feedback；mining/update外部角色是不调用的空对象，没有替换此生产消费边界。

结果：usage rows=0、target rows=0。消费代码按event.round_id > workspace.last_completed_round过滤，target_use_profiles也只用本地round cutoff。源已提交轮次1不能解释为新工作区未提交轮次1：持久化成功不等于Slow已消费。生产factory的rebased历史meta不改变原使用事件的round_id，也不能修复该缺口。

此行为同样提示slow-only及跨workspace后继的源/local轮次不能混用。不能简单将本地cutoff提高到源最高round，否则可能把新工作区尚未提交的事件一并放行。下一步应以hash-verified、contract-bound导入清单中的exact event ids明确授权源观察，保留本地pointer cutoff，逐条检查Registry内容一致。共同target profile、Slow使用/Update消费及Fast profile冻结都需核验该源/local权限，物理观察去重和blind标签边界不变。不能靠复制源Fast指针、重写event轮次或删掉失败来修复。

0外部调用，原源文件hash不变。完整目标继续：先关闭此消费缺口，再冻结继任执行验证近零技术排除及direction/magnitude真实新因子入库、后继消费；测试通过和此诊断不代表新Slow完成。

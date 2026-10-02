# v175 已提交 Slow 后继与历史版本消费修复

2026-10-02，源 v171 Fast/Slow=0/1、Registry v8。诊断入口新增 `--slow-history-from`，复用生产 history manifest/build/apply/validate 和普通 Fast→Slow 模式，不复制源指针，不改变案例、标签或评分分母。原40案（anchor16/discovery16/validation8）、来源与评价配置完全保留，导入134条授权学习事件及已提交历史；financing_listing_action:v4、guidance_acceleration:v3 保持已发布/可调用/效果待验证。v174 customer_concentration:v3 仅组件stage，未被导入。

[离线证据及hash](v175-history-preparation-20261002.json)：实际 reader/freeze 重放发现旧版本31条使用被当前card菜单误判unknown，阻断后继。回归再发现Slow同样仅遍历当前card，漏掉旧版本usage/target source。共同 committed-event selection 本已验证 exact spec 和 ledger copy，删除重复latest-menu拒绝；新增共享immutable版本inventory用于Slow反馈和Control历史导出，删除后者重复遍历。各版本只消费自身记录，当前v4/v3新画像0次，不把旧版效果转移。未知版本、缺失/改写copy、未授权未来事件仍拒绝/隔离。

专项203项通过；新增回归走实际技术准入+原子publication、共同reader/freezer、真实DualLoop新建/恢复和Slow反馈，另保留本地旧版cutoff反例。入口测试此前停在run_cycle入口遗漏消费边界，本次补实际reader/freeze。最终1481全量（105.587秒）与repository lint PASS；不把离线成功当作完整live验收。

v175当前仅prepare，本地0/0；explicit-bound离线读取不构造执行授权。下一步提交代码、隔离干净checkout冻结运行完整Fast→Slow，检查固定24案技术排除目标0，以及双轴新Mining、technical publication/持续效果追踪和后继消费。旧v170两技术排除/一技术FN保持原统计；整体目标仍未完成。

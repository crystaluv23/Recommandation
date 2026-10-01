# v167：真实内容审查与期间修复

主目录真实运行冻结在 `8c07f383`、Registry v7，原 fixed24 输入、标签、评分分母和 Locked Test 边界保持。本修复在隔离工作区，尚未用于 v167。Fast/Slow 完成指针仍为 0/0；首个 Plan 已有 24 案产物，其中 22 案完成研究、2 案技术排除。本记录不批准这些产物为语义正确。

## 本次已修复

运行时 price_shape/return_between 卡给出的首尾日期和交易日计数拥有期间语义。Controller 保留原始卡用于验证，readable 同时披露首尾日期。共享检查发现相邻的 month-return 或同一分句内 month-trend/return_pct 与唯一匹配计算窗口不符时，发出精确字段和原文绑定的期间修复权限。程序只改期间标签，整对象重验后才接受；模糊归属、未来假设、否定示例或缺少日期不推断修复。

State、Predictor、Posthoc 共用此检查。中途工具计算在解析 State 前加入检查，并保留到同案后续反思；新案例初始化即使没有 bootstrap 价格卡也清空旧计算上下文。没有改写计算公式、数值、来源元数据、判断、标签或评分。

真实首案反思把 Jan 10→Sep 29 的 180 个交易日收益写成 “14.35% six-month return”；真实另一案例 Predictor 把 Nov 7→Jul 30 的价格窗口写成 “six-month uptrend”。生产 adapter 离线回放证明：只改这两个标签，正确 sibling、数值、来源、判断和评分字段保持；首案四条反思全部保留，保存/重载/归档/Proposer 来源解析通过。冻结原始产物 SHA256 未变。详见 [精确回放](v167-computed-period-replay-20261002.json)。

验证：新增 9 测试通过，全量 1,334 测试通过。lint 初次发现隔离 checkout 缺少 20 个主目录现存历史 fixture 链接，引用这些既有 fixture 后通过；没有修改历史文档或主目录文件。

## 其他审查发现与后续工作

- 价格距离方向/分母：`cik_0001164727:20250731` 的 Predictor 把上涨约 104% 的需求写成低于正目标约 104%；反思又继承了错误。必须区分从现价到目标的所需收益与以目标为分母的差距，不能程序猜选分母改数字。
- 学习规则越界：`cik_0001521036:20250331` 的 action 要求 stated path 才允许 possible，否则降为 non-surge；现有 proof-gate 词法检查漏检，违背可选分析、机会筛选的既定语义。
- PIT 误拒绝（已在隔离代码修复）：`cik_0000701818:20250930` 的更正后 need 明确请求截止日已披露的 2027 notes 偿还/再融资意向，仍被未来内容检查拒绝。共享 expectation/schedule 词汇已纳入 plans/intentions，仍要求明确截止日并拒绝实际结果、晚披露和无界请求。生产 Controller 回放真实首次输出，六条 need 保持、无需追加纠错模型调用；详见 [PIT 回放](v167-pit-plan-replay-20261002.json)。冻结 v167 失败记录保持原样。
- 身份边界：`cik_0000723125:20250731` 初始化被 “model guessed target identity outside supplied tokens” 排除。需检查精确响应与字段局部纠错权限，不能取消匿名边界或把技术排除解释成研究失败。

请求结构、阶段计数、实际原文路径、失败产物、SHA 和当前运行快照见 [阶段审查](v167-content-audit-20261002.json)。这些发现尚未全部解决，且第二 Plan、Critic、Round、Slow 仍需实际内容审查。Binary F1 下限为 0.60；当前没有完整新轮验收分数，也没有完成目标或质量增益结论。

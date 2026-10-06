# v182 Enbridge 双 Plan 内容复核与固定提示补充

本次核对 `cik_0000895728:20250930` 的两个实际 Fast 案例。两案都预测
`unlikely / magnitude=null`，正式结果均为 non-surge，实际最大倍数
1.1216689319988467。这能核对输出和结果格式，不能证明原因正确、magnitude
扩展成功或自进化有效。本次不给端到端 PASS。

## 证据绑定与亲读范围

- 原运行：`runs/cold_start/minimal_rounds_v182_integrated`；冻结代码
  `85ffff9ed976cc4597b7e6e26a2dfe7537ab4099`。不修改冻结工作树、旧数据或指针。
- c01 原始请求/响应 5–13；c02 247–253，共 16 个 completed 调用。
  逐一核对原 `requests/<hash>.json` 的实际 user 内容和 response cache；与
  本次读取的 payload/output 完全一致。6 种固定 system prompt 全文已读。
- 亲读两案 H_init 输入、原答与修正，Signal 可见原文、执行/纠错原答，
  H_reflect 原答、最终预测和事后反思；核对不同 Plan 的 B、H_init、H_reflect、
  H_analyse。6 组源视图为 23/21/19/16/17/17 个投影，共 74 个不同 projection id。
  重复内容用逐字段差异核对；不同请求的身份 alias 不被误报为原文相同。
  这不表示全部 selector card、resolution 轨迹或更高层后续消费已完整亲读验收。
- 两个 Predictor 请求与保存 context 的差别仅是 CIK 数字和一处 `enb` taxonomy
  前缀的传输匿名化。保存 prediction 文件与 checkpoint context/prediction 一致，
  模型原答的全部预测字段一致；canonical 另有运行时派生的 `is_surge=false`。
- 本案冻结输入中的 73 个源文件 SHA 全部重验一致。hash 一致不等于发布时间正确。
- 两个反思 catalog 都只展示 70 个可用文档的首 20 项，剩余 50 项明确 omitted；
  两页内容除 alias 外一致，展示的是 2024-02 至 2024-08 的旧文档。未发生文档读取；
  未把这些 preview 当作全文证据。剩余页是否可由当前 H_reflect 通道有效到达待审查。
- 全部 48 个案例阶段已机械索引：实际 H_init 时间/投影 id 集合绑定对应 checkpoint，
  并定位 Predictor、posthoc 和其修正。这只是定位；其余 46 案未在本报告中亲读验收。

## 内容发现与跨环节路径

| 发现 | 实际证据与消费 | 判断 |
| --- | --- | --- |
| 建设成本被写成协议金额 | 8 的订单输出把 `$900 million project cost` 写为 agreement 的 `stated value`；10/251、12/252 均收到同一订单结果 | 数字真实，但金额归属不准确。v2 skill 允许 implied value/volume/schedule；不能因此自动改成 neutral/unavailable，也不能将 MW 直接当单位数量 |
| 同一项目被描述成两个催化剂 | 8 的两段引用分别描述 Clear Fork 的 $900M 投入和 600MW 容量；12 和 13 以“项目 and 设施 / both”描述它们 | 是同一 Meta offtake 项目的不同属性，不是两个独立项目。Sequoia 815MW 是源中另一个项目，应保留区别 |
| 未引证的非数值 belief 残留 | 5 编造了一条不在初始可见窗口中的 Gulf Coast 标题引文；6 按唯一授权删除该 evidence 行，7/12 的 belief 仍保留相应断言 | 删除错误引文没有自动删除非数值 belief。之后 Signal 输入确实有另一条 Gulf Coast 新闻，但这不能反过来证明 H_init 当时已经看到它；本次不猜关联、不扩大 typed 删除权限 |
| 文本汇总自行计算金额 | 9 的 summary 写 US$2.25B；16 个可见投影给出四项本金，但无 `2.25`、`2,250,000,000` 或 `2250000000`，也无该总额的运行时计算卡 | 即使相加正确，也不能把 LLM 算出的数当作源披露或运行时计算。本次补固定计算归属要求，不重写旧结果 |
| 投产时点可能变成过强筛选条件 | 输入确有 Clear Fork 2027 投产披露；12 将其用于否定六个月翻倍，13 action 还写 require within-horizon monetization，但同时声明不是正向判断条件 | 时点是可考虑的事实；远期现金流也可能通过近期预期重估影响股价。矛盾的 action 及其后续采用仍待审查，未新增现金实现门槛 |
| guidance 修正仍留下技术失败 | 249 引用窗口起点半句；250 找到新的完整 reaffirmation，却又引用 Q2 窗口起点 `end of ...` | 原始与修正均不能作为有效 Signal；正式保留 `validation_failed`。该失败不是 guidance 不存在的经济证据 |
| 正确结果仍产生解释性 fact | 13/253 的部分 decision_drivers fact 将公司体量、项目时间或价格漂移与“支持拒绝翻倍”相连 | 单案正确不能验证筛选规律或因果解释；已有固定提示已经要求区分事实/假设，现有有限文本校验没有证明任意语义正确 |

c01 routing 选 4 个 Signal，但固定 `max_llm_signals_per_round=2` 只执行前两个
LLM Signal 加 deterministic negative_word_count；c02 执行订单和 guidance。
这是实际冻结限额裁剪，不是已执行后丢失结果。两案订单 canonical result 完全一致；
c02 没有新的订单模型调用，不能把重复使用当新独立订单观察。

另亲读 negative_word_count 实际选择的 10 份完整新闻，按原 v2 配置调用生产
deterministic 函数，包含引用和 measurement 的完整 result 与保存原件逐值一致。
4 次匹配为一处 `delay`、三处 `risk`；其中两处是同一 PSNC 收购的两篇新闻里的
`low-risk`。这证明 literal 计数实现正确，不代表四个负面经济事件或语义情绪。
原函数也明确声明只测 lexical frequency；本次不偷换其定义或分类。

c01 最终有 3 个 success；c02 有订单 success 和 guidance validation_failed。
最终 Predictor 接收到明确的 execution status。253 也将 guidance 归为技术缺口，
并建议另行验证，而不是把它当作有效因子预测失败。252 将“没有验证结果”放进
负向理由的写法仍有解释偏差风险，不能以 canonical 状态保留为由免除内容复核。

## 本次必要修改

先更新四个叶子 spec，再加入一份共享固定源事实指令。它要求保留对象、单位、币种、
期间和事件身份，区分项目成本与合同价格等金额，明确推断关系，同一事件的多项属性/
重复披露只作佐证，保留确实不同的事件，数值总额/转换来自源或 deterministic 结果。

实际接入 Plan roles 的 8 个固定构造点、Signal roles 的 6 个固定构造点，以及生产
`MiningAgentRoleModel`。首次请求和普通修正共用对应构造；原有 patch grammar、
validators、权限、采样、技术准入、版本、fitness、PIT 和 Locked Test 合同不变。
没有修改 v2/v3 skill 或旧预测，也没有新增公司关键词、金额配额或“高档必须出现”的规则。

这是一条固定 authoring 要求，不是语义真值检测器。旧金额解释、预测和 no-pattern
理由仍可能通过既有解析器；本次明确保留这个限制。

## 验证与未验收事项

- 373 个相关既有测试通过，覆盖角色适配、Signal 首答/纠错、状态 patch、预算预留和
  实际 Mining 适配器；日志 `/tmp/v182-source-fact-focused.log`。
- 用实际 12/252 payload 和原预测跑生产 `LLMBlindPredictor.predict`，用实际 556/581
  payload/原答跑生产 `MiningAgentRoleModel.next_action`。4 次均仅脚本供答，0 外部
  模型调用；payload 未变、原预测/动作仍被接受，新指令确实进入构造出的 prompt。
  这是组装/解析兼容性，既不证明模型服从，也不证明 no-pattern 研究穷尽。
- 原始量级、顺序与反例已用于范围审查：项目成本≠合同价格、容量≠单位数量；
  Clear Fork 多属性≠两个项目；Clear Fork/Sequoia 也不能合并为一个项目。
  未把这些语义例子写成固定 regex 分类或声称脚本能验证模型理解。
- 仓库 lint PASS，`.lint-feedback/pre-push-last.log` 已读取；本任务 git checkpoint
  见本轮完成记录。未 push。

原 v182 仍是：case technical exclusion 0，但 180 个 Signal 中 6 个 validation_failed；
两个 Plan 的 14/15 个正向预测仍全部 2–3x；新 magnitude Signal 0；Slow memory
failed/3518 pending；已发布的方向 v3 为 pending_use/unverified。这些没有被本次修复
“升级”为通过。待完成其余案例内容审查、源时钟新输入、真实 successor 记忆/版本消费、
新 magnitude 入库及有效宽幅场景、独立增益；既有 PIT 定义和独立评估方案等待用户选择。

机器证据、48 案定位、原始请求/响应 SHA、原输出和完整新 adapter prompt：
[`v182-enbridge-pair-content-audit-20261007.json`](v182-enbridge-pair-content-audit-20261007.json)。

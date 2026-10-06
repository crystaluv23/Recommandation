# v182 终态与 Slow 学习阻断审计

2026-10-07。v182 冻结代码 `85ffff9e`；本批本地修复没有进入该运行。
目标仍 active，未作整体验收或研究增益声明。

## 实际结果

- runner 退出 0，正式 Fast/Slow 指针 1/1；608 attempts，603 completed、5 failed。
  3 次 SSL EOF 按原 request hash 恢复成功，2 份坏 JSON 原答已亲读并保留，controller 后续反馈继续执行。
  ledger cost 合计 $2.74348592，包含失败保守预留，不是精确账单。
- 两 Plan 都完成固定 24 案，case 技术排除 0；180 次 case Signal 执行中
  159 success、15 domain_unavailable、6 validation_failed。Signal 技术失败仍未清零。
- Binary F1 为 .785714/.827586；magnitude macro-F1 为 .148148/.175439。
  14/15 个正向判断全部为 2–3x，不能认定幅度有效扩展或独立提升。
- Mining 新候选、新验证、新发布均 0。实际更新发布的是方向因子
  `order_confirmation_disclosed:v3`，Registry 11→12，效果状态 `pending_use/unverified`。
  它不是新 magnitude 因子，也尚无后继 Fast 使用证据。

完整来源：[机器可审计报告](v182-terminal-slow-and-source-partition-audit-20261007.json)。

## 反思为何没有进入学习

实际 450 首答含 3 episodes/3 lessons。唯一汇总 episode 将 paired comparison
和两份 Slow 结果/验证汇总混引。原 451 typed patch 只允许替换该 episode，
却把它改成另一条 comparison；其他两条已覆盖 comparison，结果与验证汇总
从 episodes 中消失。严格完整覆盖检查因此拒收整份 delta。

正式 Slow memory 为 `failed`：0 processed、3518 pending、0 episodes、0 lessons。
后续 Mining/Update 实际 payload 都收到失败说明和空学习条目。
不能把初答中的反思文本当作真实写入或有效消费。

本地修复维持既有分离和完整覆盖规则：初始固定提示明确 episode 来源并集必须
覆盖所有反馈，lesson 引用不能替代；mixed-source 诊断列出两组 refs 与其他
有效 episodes 的覆盖，明确哪些来源不能丢。没有扩大 typed 写入权限。

用真实初答在生产 adapter 离线回放：脚本只去掉汇总 episode 的冗余 comparison
引用，保留其两份汇总来源；全部模型正文、正确兄弟和 lessons 保持。
adapter 与实际持久化 validator 通过，既有消费投影可见全部 6 条。
原 paid 451 patch 仍拒收。**这证明可合法修复及消费 wiring，不是新模型答复、
不是改写 v182 failed memory，也不是新 live 周期验证。**

## 内容验收仍有缺口

亲读两个 magnitude seeds 的 5 份原始 read receipts：hypothesis 只读同一高幅度案
13G/A 的两个窗口；discovery 读一个高幅度案的 SEC 加速生效函两个窗口和一个
control 的新闻摘要。没有 compute/compare/物化/验证动作。
终态 light=0，但 heavy=27，browse=21/5；模型把轻量目录不可继续泛化为没有
可执行探索动作。该 `no_pattern` 不能证明经济因子不存在。

亲读 Plan/Round 全部 16 条新增反思与三次 native patch。c01 提议强制生成两个
高档场景，后续必须检查证据支撑与无配额原则；本批未采纳该行动。
Round item1 的 brief 说 precision 未变且为 .80，与 runtime 的 .785714/.8 不符，
虽 detail 引用正确，仍是内容缺陷。case completion=1 不消除 6 次 Signal 技术失败。

方向 v3 确有独立准入、8 fixture 验证与原子发布；definition/spec 除 version
外相同，fixtures 字节不变。新增 ceiling-only 和 distribution 规则缺少针对性
反例，Update 对 neutral counter-evidence 的理由仍需语义复核。技术入库不证明效果。

3606 个批准来源文件逐个 hash 核对通过；这不验证其日期元数据真实。
[会议时间合同评审](transcript-availability-policy-review-20261007.md) 和四条离线纠正
预览已准备，尚待用户定义公开会议信息时间还是逐字稿文件公开时间；不改旧 oracle。

## 验证与后续

4 个新回归包含来源分组/行序变体及拒收反例；旧源码缺诊断上下文出现 6 个错误，
严格拒绝丢失 coverage 的反例在旧/新代码均成立。163 相关测试、1604 全量测试通过，
pre-push lint PASS，完整日志已核对。

603 个阶段调用、48 个结果身份和3606来源 hash 为机械库存；完整48案研究上下文和
26份 transcript 实际日期仍未全部人工验收。继续源时间修复、完整语义审查、
新 magnitude 技术入库、exact-version 后继使用及独立效果验证。
40 issuer×2 replicate 四臂独立协议仍待确认；不得自行执行或据开发 cohort 声称增益。

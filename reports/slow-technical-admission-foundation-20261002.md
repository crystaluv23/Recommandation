# Slow 技术准入基础：已实现范围与剩余工作

2026-10-02。承接用户批准的“先保证技术正确并入库、允许 Fast 调用效果待验证因子、持续追踪效果”。当前完整目标仍在进行。

## 本阶段实现

独立 `signal-candidate-admission-v1` 绑定候选 spec/skill/tests、输入 Registry hash、validator policy hash、研究目标和完整技术检查结果。允许技术通过且效果未知，不包含或伪造 effectiveness.accepted。要求所有非空 fixtures 真正通过；技术失败保留诊断。

沿用 keyed records、prepared/applied 原子 Registry transition、版本物化和恢复。每个发布版本保存准入原件，manifest 保存各版本的准入 key；重启重验身份、源内容、输入 Registry 和可执行表面。丢失/篡改 proof 失败关闭，新的候选 pointer 不改变已选择或已发布版本的依据。历史 v2/v3 效果记录按原语义保留。

当前 cards 与 FrozenSignalRegistry 增加不可变、版本绑定的 research_status，标明技术已准入、effect_status=unverified 及目标；状态参与 learning_hash，没有新记录的历史快照维持既有哈希规则。新版本重新待观察，旧版本 proof 保留。

## 实际候选重放

[重放原件](v168-technical-admission-replay-20261002.json)：复制 v168 的 Registry 和 staging 到临时目录，实际 `revenue_growth_yoy:v3` 经生产 SignalCandidateValidator 执行原真实 fixture（1/1，通过）；调用生产 Registry 准入、原子发布、freeze 和新实例恢复。候选 hash `bdaaf8a8705f4497d7ad088a06dca8779dcfed7c2e56a22e9e2d49ce5f24754c` 不变，发布副本状态“效果待验证”。原始 Registry/staging 全文件 hash 不变，原 strict paired 无收益拒绝记录可按原 key 读取且不改写，0外部调用。

这证明实际已物化 Update 候选可以走独立技术准入与恢复；不代表 v168 历史入库、不代表新 Mining 产出，也不证明 magnitude 收益。实际候选原研究目标是 direction，本次不人为标为 magnitude 因子；共享两目标能力由回归测试覆盖。

## 验证

- 原 Registry/Slow/角色与新增准入专项：223项通过（当时9项新测试）；随后补充 vNext 旧 proof 保留测试。
- 最终全量：1421项通过，78.324秒。
- lint PASS，git diff --check 通过。
- 覆盖 effect未知准入、两目标声明、完整 fixture 执行、技术拒绝、输入 hash 不符、显式 key 与最新 pointer 隔离、manifest/版本递增后中断恢复、缺失/篡改 proof、已发布内容篡改、vNext 不继承效果及旧 proof 保存。

## 仍未完成

生产 Slow 主循环仍走旧 paired/provisional 效果 gate，未改成新准入。因此不能宣称“生产因子入库已打通”。下一步接独立 effect records、Slow 双轴与 Update 准入、旧 resident 的技术复验、Fast 实际披露/选择/执行，以及 committed cutoff 下方向/magnitude 持续追踪。要同步收敛旧准入分支，不能只在旧 accepted 上伪造效果通过。

完整验收仍需冻结原样本、标签、分母的 Fast/Slow 全流程；技术排除率接近零和 magnitude 有帮助分别以真实过程与同输入对照证明。四份误拒的解析重放及1411项基础修复测试见[v168修复报告](v168-runtime-reliability-repair-20261002.md)。

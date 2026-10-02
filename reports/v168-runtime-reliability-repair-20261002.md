# v168 误拒、恢复及 Mining 动作修复

2026-10-02。继续完整 Fast/Slow 目标；本阶段完成实际四条误拒所属错误家族、技术失败恢复及 Slow action rationale 的增量修复。新技术准入/因子入库/持续目标追踪仍待实现，不将本地测试当完整目标完成。

## 已实现

- temporal：尾部 reference-to/referring-to/using 等未来资料排除按局部否定处理，正向主句和真正未来结果请求仍核验；原问题不改。
- runtime anchor：当前价格是否 discount/reflect/price-in 市场预期属于分析引用，不是 scalar lookup；每个 anchor 独立判断，混合问题里的实际查价仍拒绝。分析需求放在哪个字段的质量问题独立，不因为放宽该误判而豁免其他规则。
- arithmetic：只把与 percent 明确相连的价格目标用于算式，不把同段历史窗口的 to-price 拼到 required gain。已有明确错误端点/分母检查保留；不替模型选数字或改变判断。
- restart：恢复 exclusion trajectory 时同时恢复相邻 input-hash/case/schema 绑定的 failure 原件；损坏/丢失原件显式拒绝。完整与部分恢复保留相同失败明细、原评分分母和累计排除上限。
- Mining：缺/空/坏 rationale 只授权对应字段/成员的 native patch；非法补丁保留同一 snapshot/hash/权限，正确参数和兄弟理由不重写。已有非空 scalar rationale 先由共享 repair family 转为单项数组并记录操作；缺失理由由 LLM提供，程序不编造。合并后完整动作/状态/预算/工具检查再运行。
- Mining ledger：invalid fetch 不再计为 completed fetch，不能满足候选/no-pattern 探索前提。
- 固定 prompt：Predictor/Proposer/Critic 明确 H_analyse 管证据组织/权重，固定 shell 管最终方向和条件幅度分类，shell 强制输出优先。未宣称新的 prompt 改善预测效果。

## 实际重放与测试

[真实四项重放](v168-guard-relations-replay-20261002.json)：原付费 Initialize/Predictor 回答经生产角色完整解析，四项均接受，研究内容不改、0外部调用。两个 Initialize 原始答另有独立 temporal 义务，复用原有付费局部 correction；一项原付费否定修正也被复用。为从模型视图重建 delta，只重绑定模型视图的 snapshot hash，操作/权限保持原样，未改原文件。Initialize 的 readable computed control input保持原发送数据，未重建 typed period cards；该专项完整源期间校验由现有测试覆盖。因此这不是无条件的所有真实输入重建或最新模型遵循新 prompt 的证明。

新回归同时覆盖真越界、混合查价、否定主句、错误明确算式、恢复冲突/缺失、native局部补丁及非法补丁、已正确兄弟保留、机械修复、工具预算复验、invalid fetch 的探索计数。

- Fast/recovery专项215项通过。
- Mining动作专项54项通过。
- 全量1411项通过，67.137秒。
- lint PASS。

## 尚待完成的完整验收

冻结v168仍为7e6be2e3，指针1/1、0因子入库、Registry hash不变；历史技术排除及F1不重写。不能从“4项解析通过”推断后续全案无失败、技术FN必然成为TP、或技术排除率已经接近零。

接下来贯通独立 technical admission 与 empirical effect records、原子入库恢复、待观察 Fast 卡/实际消费、direction/magnitude 按版本持续追踪；同时处理 Slow 控制动作和各模块物化的真实 frontier。随后以冻结原案例/标签/评分分母做全流程验证，分别报告技术完成率和预测质量；因子幅度帮助以同输入对照证明。详见[因子设计](slow-signal-system-design-20261002.md)。

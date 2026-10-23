# 分类声明随 meta 保存：方案 A 落地

用户于 2026-10-23 明确选择完整声明随 meta 保存。在隔离分支 `codex/classification-meta-context` 实施并完成独立审查后，于 Mining v4 停止策略及原代码/来源封存（42bb9a4b）后合入当前 checkout。**实际保存→重读→Critic/Slow/Mining 原件读取的离线连接通过；真实模型语义消费、Fast 总体与工程 MVP 仍未通过。** 不启动完整后继、不修改业务完成指针，也不重置旧诊断预算。

## 最终行为

`CaseReflectionEvidence.signal_classification_context` 是可选的完整声明数组，按实际保存的 round、exact ref 和 canonical result_hash 绑定。新记录只提取同轮实际执行结果的已存声明；旧记录缺字段保持原形和 hash，不查今天的 Registry 或默认函数补写。whole-case 技术排除不携带该字段，缺输入和技术失败不编造分类意义。

每份声明成为原 case/Plan scope 下的独立 source unit。初始目录仅显示版本、轮次、范围和完整读取成本，正文通过已有 read_refs 完整读取。匿名化保留 source_contract_hash 并重算 view hash；声明不授予评分、PIT、outcome 或 typed 修复权限。

独立反例发现初版只补存储仍不够：24 个合成 issuer × 2 次真实 executor 结果的 48 份声明中，初始 Critic 仅露出 2 份；原 browse_memory 只列 ReflectionItem，余下 46 份虽然 resolver 存在却始终找不到引用。此前小案例/直接已知 ref 读取检查漏掉了目录容量边界。现统一分页目录增加可选 sources headers，共用 cursor、level/exact-version 筛选和全包字节预算；无新字段时目录与旧实现逐包相等。H1 的原件 selector 也考虑初始 slice 之外可读的 runtime 声明，并保留既有 32KB manifest、48KB whole-source 限制。

## 证据与限制

- [关联测试](../runs/diagnostics/classification_meta_context_20261023_v1/driver/classification-meta-associated-tests.log)：354 项、1 skip、其余通过；含 10 项新增控制及实际执行、保存/重读、反思、Slow、Mining 和双环关联模块。后续未改生产代码；不与重叠测试批次相加。
- [独立候选审查](../runs/diagnostics/classification_meta_context_20261023_v1/independent/review-candidate.md)：实际 Critic browse→新增 header 选 ref→完整 read；真实 H1 selector→初始 slice 外 ref→原件；native Mining 完整 run 的 memory browse/read 均连通。独立 48 声明+1 item 在小页混合目录无遗漏/重复，另核 exact-fit/minus-one、超大 header 前进、精确版本、legacy、匿名 hash、第四请求拒绝、aggregate 和超长 whole-unit 拒绝。原首失败与 harness 错误日志保留，网络尝试0。
- H1 此控制在32KB内露出42/48声明 header，仍有12条总目录遗漏（其中6条是声明）；明确计数未被删除。完整 native 目录可分页找到全部48，但这不保证单次角色预算足以全部读完。Critic仍最多3次读取交换、累计48KB；超长原件明确拒绝而不剪裁。
- 这些调用的模型答复是脚本控制，只证明实际生产入口连接与权限/预算行为，不能声称 fresh 模型已正确解释定义或形成研究诊断。下一次真实 Critic/Slow 触发须检查实际请求、原答、纠错和保存，旧 financial consumer 语义0/1保持。

根目录在 v4 停止并封存后应用精确 ba309796 产品补丁，保留已有非本任务改动；根目录新增分类控制、reflection memory 及历史回放30项通过。v4不得以当前代码重入。原测量、分类、评分、标签、准入、PIT 和所有已完成 stage 产物不变。

`.githooks/pre-push` 最终通过，已亲读 `.lint-feedback/pre-push-last.log`（status0 / PASS）。初次隔离 worktree 缺少 git-ignored 历史运行原件，旧文档20个链接导致 lint 失败；仅为存在于原 checkout 的目标建立本地读取引用后复验通过，未改旧报告、原件或 lint 政策。原反馈和引用清单已保存；此项属于工作区检查，不是研究证据。

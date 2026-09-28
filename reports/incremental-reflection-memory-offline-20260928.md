# 增量纠错与可溯源反思：离线验收

日期：2026-09-28。机器可读结果见 [JSON 报告](incremental-reflection-memory-offline-20260928.json)，重放入口见 [replay_incremental_reflection_memory.py](../scripts/replay_incremental_reflection_memory.py)。

本次真实历史材料的生产协议重放通过。DNS、socket 连接和发送入口被测试阻断；外部模型调用为 **0**，重放中的网络尝试为 **0**。没有新跑 Fast/Slow live cycle，也没有改变其提交指针。新格式 delta、brief 和读取请求使用显式脚本响应，因此通过的是程序合同、来源保真与消费链路；不代表已证明模型会稳定生成优质反思或研究收益。

## 冻结材料与历史问题

- V126（2026-09-20）的已保存路由纠错请求：`selection_reason` / residual 的合同冲突。
- V138（2026-09-22）的 Ciena、Wynn 纠错请求与响应：错误描述指向 evidence index，旧的授权路径却只有 claim。
- V141（2026-09-26）的 round-0001 meta、两个实际 PlanRecord、携带导入 meta 的 proposer 请求：本地 48 案例，导入后合计 72 案例。c02 的 5 条技术排除保持为技术失败；c01 case 21 的程序结论为严重漏报，但历史 critic 将其列入成功模式。

共读取 **9 个历史 JSON 文件**；每个文件读取前后 SHA-256 完全一致。完整路径及两份哈希逐一保存在 JSON 的 `source_hashes` 中。原 run 目录只读，脚本禁止将报告写回 run 目录。

## 验证结果

1. **增量纠错保留已正确部分。** V138 真实错误状态和真实第一次 index 修改进入当前生产 `_complete_parsed_role`、typed validator 与 patch 应用链。第一次补正引用坐标后仍缺一条金额证据；第二次只追加该引用，第一次修复和所有无关状态均保留。旧 hash、修改无关 decision、整体替换证据列表均被拒绝。两次响应分别只有一条操作。
2. **brief → item → 原件可恢复。** 实际 V141 反思原件及程序反馈可按授权 ref 原样读取；brief 不替代原件。目录分页可发现所有未进入首屏的条目。缺失 ref、文件路径、被篡改的 item hash、盲测角色访问、超预算原件读取均失败关闭；不会静默截断原件。
3. **高层可以直接选择低层经验。** 真实 proposer、两个 Plan Critic、Round Reflector 均经本地 caller 完成“按 case 层浏览目录 → 读取实际原件 → 返回最终 Plan 或选择未改写的低层 item”的三次调用。消费对象是完整匿名单案例反思与程序反馈，不是原始文档或完整研究轨迹。
4. **结构性错误与研究归因分离。** 已知错误案例的成功 outcome claim 被拒绝；技术排除不能支撑研究成功/失败归因。`sources_checked` 只说明引用存在与结构约束通过，不能解释成内容已经为真。历史文字保留 `legacy_unreviewed`，不伪造新的模型 brief 或追认其正确性。
5. **失败也计入预算。** [读取边界测试](../tests/test_reflection_memory_replay.py) 覆盖 missing/repeated refs、非法 level、读取后的预算/调用失败，核对累计 usage、剩余预算和已完成披露不丢失。

## 实际 payload 体积

以下均为紧凑 JSON 的 **UTF-8 字节**，不是 tokenizer token，也不是 provider 计费数据。统计对象是发给 caller 的完整 payload，包括目录、来源元数据和披露内容；不含 system prompt 等传输 envelope。

| 对象 | 对照 / 初始 | 新格式 / 按需披露后 |
| --- | ---: | ---: |
| V138 完整状态响应 vs 第一次 delta 响应 | 9,653 | 170 |
| V138 完整状态响应 vs 第二次 delta 响应 | 9,653 | 520 |
| 72 案例 proposer：相同当前 payload 放入全部保留 meta vs brief 首屏 | 341,321 | 55,765 |
| proposer：首屏 → 目录和原件披露后 | 55,765 | 70,816 |
| V141 c01 Plan Critic：首屏 → 披露后 | 88,762 | 104,354 |
| V141 c02 Plan Critic：首屏 → 披露后 | 87,734 | 103,146 |
| V141 Round Reflector：首屏 → 披露后 | 90,826 | 106,238 |

proposer 在上述同构对照中首屏减少 **83.66%**。这不是新旧 provider 请求的 token 节省率，也未证明模型实际需要多少次原件读取。Plan/Round 首屏保留程序反馈和固定 Plan 内容，所以不会缩减至 brief 预算本身。

独立 Fast → Slow H1 探针另以**小型脚本 fixture**验证真实 `_run_hypothesis_mining`，其尺寸不属于历史 V141：完整 H1 payload 从未读取原件时的 **14,288 B** 变为选择性披露后的 **27,424 B**；其中 meta brief 1,076 B、catalog 2,109 B、读取目录 2,003 B。完整 detail 的哨兵文本在所有未读字段中均不存在，包括 action backlog 和 audit；按 ref 读取后逐字恢复。空读取、成功读取、读取后 H1 被拒三个分支均累计 selector 的 7 tokens 与 H1 的 23 tokens，保留两次调用及双方 request refs。另一次 1,500 来源的目录压力探针，完整 selector payload 为 **31,839 B**（上限 **32,000 B**），目录不含原文，选中来源可精确恢复。这些是本地脚本 caller 的实际序列化与计数，不能解释为真实模型用量。永久覆盖见 `FastToSlowConsumptionTests` 与 `test_source_selection_envelope_bounds_large_brief_and_directory`。

## 新生命周期覆盖与限制

H1 当前对本轮 brief、catalog 和研究需求中已公开的索引按需读取原件；它没有 Fast proposer／Critic／Round 的分层分页接口。共同遗漏的历史条目仍在归档中，遗漏数量可见，但 H1 不能在本轮主动遍历全部 Fast 历史。此处不宣称全部历史都已被检索或消费。

[生产角色测试](../tests/test_structured_reflection_roles.py) 覆盖 Fast 的案例结构化反思 → Plan 反思与低层选择 → Round → JSON 重载 → 导入 round 编号变更 → proposer 按 ref 读取；引用及原件跨重载保持一致。Slow 覆盖同次产生 kind/brief 与完整反思、完整 lesson，按既有 reader 恢复原件，下一轮 `_prepare_slow_memory` 先见 brief、按需读原件再产生新反馈；旧文本不被编造出 brief。上述测试使用脚本 caller，Slow 持久化边界使用本地 fixture，不能替代真实新周期验收。

共享历史测试 adapter 只在收到真实 issued patch/source contract 时显式转换旧 fixture，保留原文并标明非 brief 质量评估；生产解析器不接受旧 full-output 纠错作为降级协议。Jev 重放保留程序拥有的不可变预测与反馈，技术反思失败只记 `no_findings_reason`，不制造研究教训。

仍需另行授权的外部验证：模型独立生成局部 delta 的稳定性、brief 是否保留关键条件和反例、引用是否语义上支撑结论、按需读取是否遗漏重要少数案例，以及相同冻结评价条件下是否产生可复现研究收益。当前按用户要求停留在离线验证范围。

复现命令：

```sh
PYTHONPATH=src python scripts/replay_incremental_reflection_memory.py --output reports/incremental-reflection-memory-offline-20260928.json
PYTHONPATH=src python -m unittest tests.test_reflection_memory_replay tests.test_structured_reflection_roles
```

## 最终本地验证

最终代码全量执行 `python -m unittest discover -s tests`：**1,144 项通过**（63.039 秒）；`scripts/lint_repo.sh` 和 `git diff --check` 通过。另执行冻结历史零网络重放，9 份输入文件均保持原始 SHA-256。读取器的最后一个边界也由真实适配器回归覆盖：选择器已成功调用后，50KB 原件超过 48KB 读取预算时仍拒绝读取，同时保留该次调用的完整 usage 和 request refs。

测试使用项目兼容的 bundled Python 和 `PYTHONPATH=src`，没有新外部模型调用。这份记录是离线实现验收，不是新 live cycle 或研究收益确认。

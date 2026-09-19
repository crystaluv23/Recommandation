# Round15 最终报告：V119 重复出现诊断纠正 + 出现级转换校验 + 安全列表回收收口

基线 c0a5bc2（888 测试）；round-14 部分编辑保留于工作树并按更正诊断修复。无生产调用、无 commit/push。

## A. 出现/多重性感知的靶向 need 转换校验（先改 spec）

诊断更正已被真实工件证实：`v119/c02-case2-rejection.json` 中 request202 的
`research_state.next_information_needs[2]` 与 `[3]` 字节相同，仅 `[2]` 被靶向；
202 原始响应把 `[2]` 换成精确残余并保留 `[3]`。旧
`_targeted_answer_need_transition_errors` 用全局文本成员（`need in current`、
`.index(need)`）把保留副本误判为目标失败。工件内 203 请求的
validation_feedback 正是那次误报（旧 `'path': 'next_information_needs[2]'`）。

修复（evolution_research_validation.py，机制级非索引重映射）：
- 按出现计数的义务匹配：每个未靶向出现必须逐字保留；每个靶向出现须产出
  有界残余（partial）或被移除（full）；selection 绑定 `target_need_indices`
  全部下标（与契约构建器逐下标规则一致，旧代码只注册 `[0]`）；一个返回
  出现不得满足两个先前出现；remove 义务不计入"须保留"计数。
- 诊断坐标由算法给出盈余出现位置（returned_path），保留副本不再被指为目标；
  `_need_transition_validation_issue` 删除全局 `.index()` 回退，
  write_scope_complete 改为 returned_path 存在性。
- 不可表示残余的专属错误文案与 signal_refs 保留（round-06 行为不变）；
  cosmetic 扫描排除与原文相同的候选（恢复旧语义里被全局成员分支挡住的情形）。
- 确定性回退（evolution_output_validation.py
  `_research_need_transition_fallback`）每条指令只转换一个出现：
  remove 不再删除全部同文副本，replace 保持单出现替换。契约构建器
  `_reflection_need_transition_contract` 本就逐下标发布，无需改动。

## B. 安全列表回收收口（evolution_output_validation.py）

- 评审反例封堵：`member_removal_allowances` 已提供但缺根键时，
  `_project_scoped_correction` 现传 `.get(list, ())` ⇒ 该集合零移除授权
  （旧 `.get→None→covered 全可删`）。反例
  `({'rows':['invalid','keep1','keep2']},{'rows':['keep2']},['rows[0]'],allowances={})`
  现返回 None。
- 歧义拒绝：锚点间授权槽数多于返回行数的短 run 不再 zip 猜首槽，直接 None。
- 保留成果：c01 Newmont actual179 仍和解为 beliefs 0,1,3,5,6,7（授权删 2/4、
  恢复 valid5、还原 6/7 顺序），无关字段逐字保留；重复内容、无授权消失、
  超预算插入等 fail-closed 负例全绿。

## v89 回归调查（round-14 遗留）

`test_v89_blind_predictor_discards_unrelated_correction_drift` 失败是容器类型
而非范围问题：探针证明投影输出为正确 list
['Strong momentum…','Management reaffirmed…']，而 `BlindPrediction.from_dict`
对任何输入都存 canonical tuple。修正测试期望为 tuple（内容/顺序断言不变，
前面的 candidate_judgment/magnitude 断言原本已通过）——未削弱断言。

## 测试（tests/test_evolution_output_validation.py 等，均在允许清单内）

- round-14 错误期望的重复先行测试改写为
  `test_v119_duplicate_need_transition_accepts_targeted_occurrence`：断言原始
  V119 转换零错误。
- `test_need_transition_feedback_targets_returned_path_not_prior_index` 改用
  互异先行 need + 移位返回（returned[2]/prior[1]），保留 round-14 的
  returned_path/prior_state_path 坐标与 write_scope_complete 断言。
- 新增：多重性（单出现不得满足两份保留、靶向+未靶向重复、多目标/多残余、
  full vs partial）、回退单出现转换、空授权反例、歧义短 run、以及经
  `_complete_parsed_role` 的 replace-only 守卫测试（parser 仅拒绝初始无效
  成员并接受缺席，守卫必须阻断未授权整员删除，正向对照替换成功）。

## 实际命令与结果（exit code）

- focused：`PYTHONPATH=src …python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v` → exit 0，Ran 32 tests OK。
- full：`… -m unittest discover -s tests -v` → exit 0，Ran 897 tests OK。
- lint：`sh scripts/lint_repo.sh` → exit 0，Lint result: PASS。
- replay：`…python3 .delegation/…/round-15/replay.py` → exit 0，ALL ROUND-15
  REPLAY CHECKS PASSED。
- `git status --short`、`git diff --check` → 无空白错误；改动仅限允许文件
  （两源码、两 spec、三测试、progress 两文件、round-15 目录）；round-14/v119
  审计文件原样保留。

## replay 内容（生产代码重建，无模型调用）

- c02：202/203/204 三个 attempt 的 need-transition 错误全部为 0（误报消失）；
  工件记录的数值证据缺陷类别仍在（203 请求反馈含
  "supporting_evidence[8] claim contains numeric quantities absent from all
  referenced Signal evidence items…"，即 signal 数值层校验未被本轮改动削弱）；
  202 自身的 raw basic/assertion 数值检查为空，说明其数值缺陷在更深的
  signal-claim 数量层（见局限）。
- 空授权反例 → None；c01 和解与两个 fail-closed 探针通过。

## 局限

- 未在本地完整重建 `_validate_signal_claim_quantities` 所需的 batch 证据上下文
  （需要 202 的 signal batch），"numeric validation stays" 由工件记录的错误
  字符串与零回归测试佐证，而非端到端重放该数值拒绝。
- 203 "safe scope 下 eligible" 以转换零错误 + 数值-only 修复路径论证，未逐字
  复放 203 的 scoped 投影（其 must_change 路径未含 need 字段，与该结论一致）。
- round-10 高级反馈行为与 round-13 参照守卫未单独复放，由 897 全量测试覆盖。
- 消耗约 25 个模型轮次，超出 20 轮 advisory 预算（诊断与三轮测试迭代所需）。

# Round 05 Report

- round_id: fast-slow-20260919/round-05
- status: completed（本地验证完成；真实 Fast+Slow 复跑未做，见 outstanding）

## changed files

- src/stock_opportunity_agent/research/evolution_research_validation.py
- src/stock_opportunity_agent/research/evolution_plan_roles.py
- src/stock_opportunity_agent/research/evolution_output_validation.py
- spec/src/stock_opportunity_agent/research/{evolution_research_validation,evolution_plan_roles,evolution_output_validation}.md（spec 先行）
- tests/test_evolution_reflection_roles.py、tests/test_evolution_routing_plan_roles.py（新增 V117 链回归）、tests/test_evolution_output_validation.py（漂移反例+fail-closed）、tests/test_evolution_execution_roles.py（恢复语义更新）
- reports/fast-slow-joint-correctness-20260919.md（新）、progress/status.md、progress/changelog.md、本报告

## findings（要点）

1. 初始审计不完整：v117-required-residual.json（请求 12 义务原文）证明矛盾源头在路由生产者——partial 残差 "Cost per ounce guidance … remainder of 2025 and 2026 …" 丢失了父需求的 "disclosed by 2025-09-30" 截止子句，select 校验只查 grounding/非装饰性、从未查时间范围，于是持久化了一个无界 SignalSelectionDecision；下游 `_reflection_need_transition_contract`/`_targeted_answer_need_transition_errors` 逐字强求该不安全残差，而时间守卫必拒之——输出 11 的有界更窄残差反而被判 research_need_transition_invalid。模型在两个守卫间振荡，sibling 保全修不了被授权字段本身。
2. 修复：共享规则 `_bounded_residual_need`——残差已合规则原样返回；丢截止子句则以父需求子句原样缀回（保留字面量），产出的必需表示同时满足 transition 与时间守卫；无法有界化则降级 remove-or-narrow，不再强求不可用字面量。生产者边界：select 拒绝日历范围超出目标需求显式 as-of 界的残差（以父界为锚，无需 prediction_time；生产者接受⇒消费侧接受）。四个消费点（契约、intents、transition 校验、`_restore_inherited_need_cutoffs`）统一走该规则；恢复目标由"整条已答父需求"改为"残差+截止子句"（真正更窄且保留 PIT；旧整条恢复仅作兜底）。
3. round-03 整对象回退已按 review 移除：lenient 模式下投影仅可被"投影对象自身复检产生的结构化 issue 路径"扩展；整对象仅当全部漂移都是列表成员增删（裸列表根、长度变化）且全量复检通过时可替代投影；标量/嵌套叶/同长条目漂移一律 fail closed。v11/v22/v23/v70/v73/v74/v79 的合法联动/列表修复继续可用，review 的无关漂移反例被拒。未为绿灯弱化任何守卫或既有断言（仅 execution roles 恢复测试期望按新语义更正：有界更窄残差而非整条父需求，此即 round-05 目标行为）。

## tests（实际命令与退出码）

- focused：`PYTHONPATH=src …/python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v` → exit 0，14 tests OK → round-05/focused.log
- full：`PYTHONPATH=src …/python3 -m unittest discover -s tests -v` → exit 0，Ran 862 tests，OK → round-05/full-tests.log
- lint：`sh scripts/lint_repo.sh` → exit 0，Lint result: PASS → round-05/lint.log
- `git status --short` / `git diff --check` → 干净（无空白错误）。按 brief 本轮不 commit/push。

## outstanding

- 真实 Fast+Slow（V117 后继工作区）复跑以验证修复后的契约在真实模型下闭环——本轮零生产模型调用，全部为本地 ScriptedRoleCaller 走生产 role/validator 路径。
- 原始请求工件字节哈希未能在本轮许可命令清单内重算（已在联合审计报告中注明，留作机械跟进）。
- 无接口契约变更需要用户裁决：均为模块内私有函数签名扩展与既有语义收紧，spec 已同步。

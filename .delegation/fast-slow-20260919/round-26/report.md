# Round 26 最终报告：否定式归属说明在 Fast proposal 阶段被误拒（V125）

日期 2026-09-20。仅 round-26 范围；无子代理/付费调用，未 commit/push，未改任何
frozen run。报告先以 partial 状态在编码前保存，本版为实际结果回填。

## 结论
确认的误拒已修复并通过全部实际检查：focused 77 测试、full 949 测试（943 存量 +
6 新增）、lint PASS、V125 原始 wire attempts 1-6 复放 failures=0——六次尝试的
`source_ownership_not_guaranteed` 假拒绝全部消失，且经原始 available_source_types
复放完整 proposer 上下文校验后全部接受，无其他真实校验问题残留。守卫语义未放宽：
肯定式归属、混合否定+肯定、早子句无关否定、not only/but still 对比仍拒；被否定的
第一方短语不再给无界 competitor 请求假授权。三对 proposal/correction 假拒绝（1/2、
3/4、5/6）不可计入正常质量拒绝。

## 代码修改（spec 先行）
- `spec/src/stock_opportunity_agent/research/evolution_output_validation.md`：新增
  "Proposal request-scope ownership guard (round 26)" 不变量段（occurrence-aware、
  局部否定豁免的严格条件、cross-issuer 同规则、无 NLP/公司特例、未识别措辞保守仍拒）。
- `src/stock_opportunity_agent/research/evolution_output_validation.py`：
  1. 新增共享规则 `_OWNERSHIP_SCOPE_NEGATION_PRECEDING` +
     `_scope_match_is_locally_negated` + `_has_affirmative_scope_match`：仅当
     not/never cue（排除 not only/just/merely/simply）与短语在同一子句（截断于
     `,;:.!?\n`）72 字符窗口内、且经 "as ..."（至多 4 个间隔词 + 限定词）或裸限定词
     连接时，该次出现记为被否定；沿用仓库既有否定先例
     （`_PRICE_OUTCOME_NEGATION` 的 cue+有界同句窗口+负向先行断言风格）。
  2. 三个消费点改为"至少一个肯定出现"：B.requests 的 description/query 归属守卫、
     `_TARGET_ISSUER_REQUEST_SCOPE` 的 cross-issuer 授权（否定短语不再授权）、
     H_init/H_reflect/H_analyse 技能字段守卫。
  3. 计划外修复（首跑发现）：工作区 `_FIRST_PARTY_OWNERSHIP_REQUEST_SCOPE`
     缺最外层右括号（`news)\b` vs 兄弟模式的 `news))\b`），模块 import 即
     `re.error: missing ), unterminated subpattern`——修复为兄弟模式同构的平衡形态。
- `tests/test_evolution_output_validation.py`：新增 `OwnershipScopeLocalNegationTests`
  6 条测试（覆盖实际1 原文、raw2 加强 never、brief 确认的最小探针、do-not-treat /
  must-not 禁止式通过；4 种肯定形态仍拒含无关否定、not only/but also、同字段混合；
  query 字段逐出现；技能字段否定通过/肯定拒绝；cross-issuer 否定不授权 + 肯定
  scoped 授权）。
- `.delegation/fast-slow-20260919/round-26/replay.py`：见下。

## 实际执行的命令与结果（均用允许清单原命令，exit 码如注）
1. focused：`PYTHONPATH=src .../python3 -m unittest discover -s tests -p
   test_evolution_output_validation.py -v` → 最终 exit 0，`Ran 77 tests ... OK`
   （71 存量 + 6 新增）。
2. full：`... -m unittest discover -s tests -v` → exit 0，`Ran 949 tests in
   20.971s OK`（943 存量 + 6 新增）。
3. lint：`sh scripts/lint_repo.sh` → exit 0，`Lint result: PASS`（7 项全 PASS）。
4. replay：`... python3 .delegation/fast-slow-20260919/round-26/replay.py` →
   最终 exit 0，`failures=0`（6×payload 等值 + 6×假拒绝消失 + 4 独立守卫探针，
   共 16 项 PASS）。
5. `git status --short`：本任务改动为 src/evolution_output_validation.py、
   tests/test_evolution_output_validation.py、spec/evolution_output_validation.md、
   progress/status.md、progress/changelog.md 与 round-26/ 产物；未提交（按 brief，
   commit 属 Codex 评审后）。`git diff --check` 无空白错误。

### 迭代过程中的失败（如实记录）
- 首次 focused/replay 均 exit 1：`_FIRST_PARTY_OWNERSHIP_REQUEST_SCOPE` 既有
  括号缺陷导致模块不可 import（见上，已修复）。会话开始时 git 快照显示 src 无
  未提交改动，即该缺陷先于本轮存在；因 `git show` 不在允许清单内，无法进一步
  核对 HEAD 提交内容与工作区的差异来源。
- 第二次 replay exit 1：replay 自身 wire 路径（parents[2]→parents[1]）与
  `RawInfoRequest` 约束（query 必须省略或非空）两处脚本缺陷；另 focused 的技能
 字段子测试把 `H_reflect` 大写关键字直传 `**kwargs` 致 TypeError。均已修复后
  全绿。

## 重放关键结果（round-26/replay.py）
- wire 条目结构：`{attempt_id, hash, stage, payload, output}`；原始请求存于
  `runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v125/
  requests/<hash>.json`，六次尝试全部按 hash 命中。
- 六次尝试（1、2、3、4、5、6 = 三对 proposal/correction）：解码
  `messages[-1].content` JSON 与审计 payload 做解码对象比较，全部相等（此前报告
  所谓 escaping/compaction 之说不成立）；用原始 `available_source_types` 复放
  `_validate_proposed_request_scope` 与 `_validate_plan_for_proposer_context`
  （含 market backbone、source types、fixed semantics、技能完整性、request scope），
  六次全部 accepted——移除假拒绝后原始提案在本层无其他真实问题。
- 独立探针：否定式通过；肯定式与 not-only-but-仍 `source_ownership_not_guaranteed`；
  否定式 scoped 短语不授权 cross-issuer（返回原 cross-issuer ValidationError）。

## 局限
- change-focus 检查未复放：wire 内无 parents 内容（brief 的 "as available"）。
- 未驱动 `LLMInformationPlanProposer` 的 prompt 构造/role caller 外壳；复放的是
  adapter 所调用的同一组实际校验函数（helper 级复放，按 brief 要求明示）。
- 局部否定豁免仅覆盖明确的 not/never + as-连接（或裸限定词）形态；未识别的措辞
  保守仍拒（宁可误拒不放过）。
- 仅本地静态验证与冻结 wire 复放；无生产模型调用。V125 已 STOPPED（owned 62808，
  exit 130），生产重跑待 Codex 独立评审与 commit。Fast+Slow 主目标仍未完成。

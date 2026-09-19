# Round09 Report: explicit member-deletion authority, no generic leaf escalation

- round_id: round-09（fast-slow-20260919）
- status: 完成（本地就绪，待独立验收；真实 Fast+Slow 复跑仍未执行）
- executor: 单执行者，无嵌套 agent；未做 deadline/live 调用/commit/无关改动

## 问题与机制诊断

round-08 附加验收的独立生产复放证明：`_complete_parsed_role` 里的
removal_allowances 构建器对任何带下标的叶子义务路径（如 `rows[0].fix`）
无条件授权删除父行——反例：invalid={rows:[{fix:0,keep:"original"},
{fix:2,keep:"protected"}]}，纠错纯删除 rows[0]，解析器只拒绝 fix==0
（allowed_repairs=("replace",)），生产 reflect 旗标（exact_compaction_scope=
True, enforce_scoped_correction=True, stable_correction_prefix=True）下整个
对象被接受：replace 叶子权限被升级成父行删除。round-08 的"被义务点名的成员
（含叶子之下）可删除"规则用一种越权替换了另一种。

附带小缺陷：`_authorized_equivalent` 未先处理精确路径——节点自身路径被显式
授权（如 `rows[0].tags`）时仍递归进同长 list 元素（未列出的 `tags[0]`），
导致邻行被授权删除时同长 list 值叶子替换被误拒。

## 修复（删除通用推断，而非叠加例外）

evolution_output_validation.py：

- removal_allowances 只由两种显式授权来源填充：(a) 所属验证器 issue 的
  repair_context `authorized_member_removals` 显式点名精确成员路径；
  (b) 义务自身以整成员路径 `root[i]` 命名且 allowed_repairs 含 "remove"。
  叶子路径、叶子 remove 语义、整对象有效性永不授予父行删除（原通用
  member-regex 推断构建器被删除）。
- `_authorized_equivalent` 在 `old != new` 后先检查 `path in allowed`：
  精确授权路径先放行其整个子树再递归（与 drift visit 的既有精确路径短路
  同语义）；文档字符串同步。

evolution_signal_roles.py（本轮新增授权写入范围，刻意纳入）：

- `h1_unknown_need_refs` 验证器（原 ~1935 行）现在为被诊断行显式签发整行
  删除授权：保留原叶子诊断（paths/message/source_refs 不变），新增
  allowed_repairs=("replace","remove") 与 repair_context=
  {"authorized_member_removals": ["need_dispositions[i]"]}。授权仅覆盖
  refs 在实际运行时需求集下确实无效的那一行；纠错对象仍须通过完整 H1
  解析；不做 H1 全局豁免或全叶子路径豁免。

spec 先行更新：evolution_signal_roles.md（H1 需求台账聚合 invariant 记录
显式成员删除元数据）、evolution_output_validation.md（成员删除权限来源与
比较器精确路径规则，替换原"叶子之下可删除"表述）。

## 变更文件

- src/stock_opportunity_agent/research/evolution_output_validation.py
- src/stock_opportunity_agent/research/evolution_signal_roles.py
- spec/src/stock_opportunity_agent/research/evolution_signal_roles.md
- spec/src/stock_opportunity_agent/research/evolution_output_validation.md
- tests/test_evolution_output_validation.py（重写 1 个掩蔽负例 + 新增 2 个）
- tests/test_evolution_signal_role_adapters.py（现有 H1 测试加元数据断言）
- progress/status.md、progress/changelog.md
- reports/fast-slow-joint-correctness-20260919.md（追记 Round 09 节）
- .delegation/fast-slow-20260919/round-09/{report.md,focused.log,full-tests.log,lint.log}

（evolution_research_validation.py / evolution_plan_roles.md 及其测试的既有
修改来自更早轮次，本轮未触碰；无 commit，按 brief。）

## 结果与证据

- 重写 `test_leaf_correction_cannot_rewrite_members_or_change_membership`：
  解析器只拒绝无效 fix（不再镜像 scope 保全），"否则有效仍被拒/被丢弃"成为
  守卫真实性的独立证据——纯删除（即生产反例）与替换+新增在 2 调用后被
  CandidateExecutionRejected；同长兄弟改写被投影丢弃、原值逐字节保留；
  插入变体保留仍被拒；并断言义务不含 authorized_member_removals、
  allowed_repairs=["replace"]。
- 新增 `test_member_removal_requires_explicit_validator_authorization`：
  整成员 remove 义务正例与 authorized_member_removals 元数据正例均 2 调用
  通过，且元数据出现在发给模型的 validation_feedback。
- 新增 `test_authorized_leaf_list_replacement_survives_neighbor_removal`：
  组合正例（授权 rows[0].tags 同长替换 + rows[1] 显式删除 + rows[0].keep
  保留）通过；无比较器修复时该例必失败（验证判别力）。
- 现有 H1 测试 `test_h1_aggregates_history_refs_in_ledger_and_terminal_reason`
  原样通过（obligation_count=2、required_change_paths 精确不变），新增断言
  authorized_member_removals=["need_dispositions[0]"] 与
  allowed_repairs=["replace","remove"]。
- round-08 成果全部保留：叶子扩步拒绝（A）、compaction 精确删除（B）、无
  blanket current_beliefs 权限、有界追加、round-06 routing→reflect→routing
  组合链、全部历史夹具。

命令（brief 原样执行）与退出码：

- focused：`unittest discover -p test_evolution_output_validation.py -v`
  → 21 tests OK，退出码 0（round-08 为 19，+2）
- full：`unittest discover -s tests -v` → 875 tests OK，退出码 0
  （round-08 为 873，+2）
- lint：`sh scripts/lint_repo.sh` → PASS，退出码 0
- `git status --short` → 仅本轮任务文件与既有未提交改动；`git diff --check`
  → 干净
- 日志：.delegation/fast-slow-20260919/round-09/{focused,full-tests,lint}.log

## 独立核验说明（负例确实依赖守卫）

三个被拒/被丢弃的纠错对象在解析器语义下均有效（不含 fix==0 的行），
因此 CandidateExecutionRejected 与投影丢弃只能来自 scoped-correction 守卫；
解析器不再自带成员保全断言（原掩蔽已删除）。

## 遗留

- 本地 ScriptedRoleCaller 复放不等于运行时验收：真实 Fast+Slow 双循环在
  V117 后继工作区的复跑与独立验收仍未执行；V117 及各诊断工作区保持不可变。
- h1_unknown_need_refs 之外的 H1 issue（如 h1_disposition_row_shape_invalid，
  整成员路径但 allowed_repairs=("replace",)）现在不再隐式授予行删除——若
  生产中该行的合法修复确需删除，应由该验证器同样显式签发元数据（本轮按
  brief 未动，现有测试全绿）。

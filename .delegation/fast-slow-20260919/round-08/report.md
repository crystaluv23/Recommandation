# Round08 报告：路径扩步全程保持字段/成员粒度

- round_id: round-08（fast-slow-20260919）
- status: 完成（本地就绪，待独立验收；真实 Fast+Slow 复跑仍未执行）

## 问题与机制诊断

round-07 附加验收的两个反例同属一个机制缺陷——每一步路径扩步都丢失了
字段/成员粒度：

A（叶子→成员越权）：issue 仅授权 `rows[0].fix` 时，变长成员检查把叶子
路径计入授权槽位（round-07 把基数上界从 len(protected)+slots 放宽到
len(old)+slots），纠错得以改写兄弟 `keep` 并插入任意记录；同长情形本就
由逐位访问拦截，变长分支成为旁路。

B（容器根→整表越权）：投影复检发现 `research_state_item_over_limit`
（paths=("rows",)，repair_context 含 required_compaction_remove_paths=
["rows[1]"]）时，`_structured_revalidation_paths` 平铺 issue.paths，把
容器根当裸根授权，`_project_scoped_correction` 整表复制 corrected.rows，
rows[0] 漂移被接受、精确删除元数据被无视。

另有两处无条件 `dependent_paths=("current_beliefs",)`（visible_answer_
need_retained / research_need_transition_invalid）授权 need 纠错改写全部
信念，属 round-07 为过测引入的 blanket 权限。

## 修复（机制级，非补字符串）

evolution_output_validation.py：仅精确成员路径 root[i] 授予整成员替换/
受限拆分；叶子路径永不改写兄弟/换整成员/插记录；被义务点名的成员可删除
（对齐纠错契约"或在不允许省略时删除"，合法保留 h1 台账删除行等修复），
未点名成员按原序幸存且仅允许自身授权叶子编辑（新增递归 `_authorized_
equivalent`，漂移检测与投影守卫同规则）；插入仅由 allowed_repairs 含
add 的义务按缺失字面量数授予有界追加预算（v11 同 claim 追加由此合法，
超预算 fail closed）；`_structured_revalidation_paths` 改为返回(复制路径,
精确删除路径)——compaction issue 只贡献 required_compaction_remove_paths，
容器根不授权、无元数据不扩展；投影新增确定性整成员删除；`_authorized_
correction_paths` 在精确删除已枚举容器后不再追加其根路径（同规则覆盖
首轮压缩模式）。删除漂移 visit 内不可达的 `_authorized_membership_edit`
分支与冗余 `preserve_descendant_list_shape` 旗标（proposer 行为不变）。
evolution_research_validation.py：移除两处 blanket 信念依赖，信念改动须
由真实同 claim 链接（claim issue 已精确签发）或真实压缩义务授权。
spec 三份先行更新；plan_roles 仅去除死旗标传参。

## 变更文件

src/.../evolution_output_validation.py、evolution_research_validation.py、
evolution_plan_roles.py；spec/src/.../evolution_output_validation.md、
evolution_research_validation.md、evolution_plan_roles.md；
tests/test_evolution_output_validation.py（+3）、
test_evolution_reflection_roles.py（+1）；progress/status.md、
progress/changelog.md；reports/fast-slow-joint-correctness-20260919.md
（追记 Round 08 节）；本轮三份日志。

## 结果与证据

新增回归：反例 A 插入+删除两变体（生产 reflect 旗标，均 2 调用后
CandidateExecutionRejected）；反例 B 两调用接受且 rows[0] 逐字节保留；
有界追加正/负例；need 纠错期间无关有效信念逐字节不变（生产角色负例）。
v6/v11/v15/v62/v70/v74/v77/v79/v102-v107 真实形态夹具、压缩/依赖/
lenient 链、round-06 routing→reflect→routing 组合链全部原样通过。

- 命令（brief 原样）：unittest discover -p test_evolution_output_validation.py
  → 19 tests OK；unittest discover -s tests → 873 tests OK；sh scripts/
  lint_repo.sh → PASS；git status --short / git diff --check → 干净
  （仅本轮任务文件改动，按 brief 不提交 commit）。
- 日志：.delegation/fast-slow-20260919/round-08/{focused,full-tests,lint}.log
- 退出码：focused 0；full 0（中途两轮迭代曾 1，修复后 0）；lint 0。

## 遗留

本地 ScriptedRoleCaller 复放不等于运行时验收：真实 Fast+Slow 双循环在
V117 后继工作区的复跑与独立验收仍未执行；V117 及各诊断工作区保持不可变。

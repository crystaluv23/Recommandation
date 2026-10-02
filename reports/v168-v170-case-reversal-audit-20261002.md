# v168 → v170 两案例反转：输入、内容与经验消费审计

日期：2026-10-02。当前代码1269fabe；仅审计及设计建议，没有修改生产代码、固定prompt、canonical记录、标签、评分或Registry，没有外部调用。整体Fast/Slow目标仍受DeepSeek余额阻塞，本文不将局部审计视为完整验收。

## 结论

两案值得保留为成对研究诊断，但尚不满足“全部流程和交付内容正确，剩下只是同输入模型摇摆”的前提。实际输入、Plan、固定prompt和部分Signal观测不同；四次输入均完整交付其已选Basic卡片、研究状态与增量，方向均来自模型原答。未发现这四次最终交付把方向改写或把所选卡片丢掉；这不等于原始资料选择全面或任意叙述语义正确。

ATI负面答引用未交付的市值比较；两负面答仍有把当前价格离翻倍目标的距离当反证、要求定量价格桥的倾向。固定shell明确禁止该证明门，但code生成的context_contract还含范围过宽的numeric_decision_inputs_permitted_only_in表述。因此不能宣布prompt完全无干扰，更不能把反转归因已查明为模型随机性。

现有逐案experience、Plan/Round反思、引用索引和Slow消费链存在；显式的跨工作区成对反转诊断没有。v170这两案的十条逐案经验完整归档进入v171 bootstrap，但检查v171全部24次实际mining_controller_step用户payload，十个item_ref均未出现。初始controller页5项，目录可翻阅其收到的21项上游选择池；上游100项中的79项不在此池。不能用“已存经验/有入口”代替这两案已被实际消费。这个有限视图不等于丢失归档，也不证明所有摘要完全没有相似研究主题。

完整[机器证据](v168-v170-case-reversal-audit-20261002.json)绑定源文件hash、四个实际请求与响应、匿名投影及逆向恢复、原patch重放与Slow请求逐项追踪。

## 两案与同条件范围

| 案例 | v168 c02 | v170 c02 | canonical实际结果 | 反转前后的变化 |
| --- | --- | --- | --- | --- |
| Newmont，cik_0001164727:20250731 | possible / 2-3x | unlikely / null | 2.0177998x / 暴涨 | 所选Basic文档8→11、卡21→22；Plan指令与Signal选择/结果不同 |
| ATI，cik_0001018963:20250930 | possible / 2-3x | unlikely / null | 2.0645243x / 暴涨 | 所选Basic文档8→11、卡20→22；Plan指令与Signal选择/结果不同 |

同一案例、同一预测时点、标签与价格计算相同；模型deepseek-v4-flash、temperature=0、max_output_tokens=2000相同。输入和固定prompt不同，不能称严格同输入重复实验；temperature=0也不保证跨不同输入结果一致。两案的实际结果都略高于2x边界，是方向判断边界案例；不是magnitude_ge3_v1正例。

四个最终Predictor请求：

- v168 Newmont：304eb19a3a836882595cf3586906782fdcf9bbc8ca1b6c71fbb2942608a042c4。
- v168 ATI：ac803ce7c2e28b81db24cff6b974ee6adde5359df29846f47f555e54ab520bd5。
- v170 Newmont：e6a7c124bd42b2b7d52a6944178ce735ee1620b92c7864272304a30bbace0238。
- v170 ATI：3283ebab681142d6578a756321ea2032642102dcf93987624e2bd0c41c656b1d。

逐请求canonical hash和合同绑定、响应hash与完成attempt核验通过；保存的HTTP body字节数/hash、实际input消息及模型/温度/输出额度与request记录完全一致。用生产_CaseIdentityProjection在实际案例别名下重建请求，四份payload与原发送内容逐字结构相等；逆投影返回原final_context。85张所选Basic卡片全部保留，完整final_state和state_deltas匹配，所选卡available_at不晚于预测时点，未发现current-case outcome字段。身份投影改变CIK/accession等表示而非财务值；不能直接用未投影的canonical context与wire差异认定丢证据。

核验范围明确：已选可见卡、四份最终请求和原答；没有对所有原始文件做独立事实真伪验证，没有逐条证明所有Signal引用的期间语义，没有隔离prompt/Plan/数据变化的独立外部实验。

## 程序修复是否删掉了有效正面内容

ATI Reflect请求d5fdc794...的原付费patch在原canonical initial_state及原base_hash下实际apply_state_patch成功。_validate_assertive_state_claim_links准确复现三处assertion_without_support：current_beliefs[0:3]。模型把多条含数值的证据改写合并为belief，却没有逐字对应的accepted claim，第三处还增加未对应claim的as-of日期。

这三处移除由既有确定性fallback执行，不是模型原patch直接删除原belief。是删除不合契约的数值替换；原Basic卡、hypotheses和正面Signal引用仍保留。最终实际请求仍含raised the midpoint、guaranteed volume、worth nearly $1 billion与3.7 billion。不能宣称这些支持证据在交付中消失；摘要变化也可能改变模型注意力，需受控视图实验检验，不能凭保留hash断言权重无影响。

## Prompt与回答内容

实际system diff仅新增角色权限澄清：admitted/unverified的测量可以使用但不能声称收益，H_analyse管理组织权重，固定shell拥有方向与条件幅度输出，Plan的不得预测句不撤销shell能力。新增段不是要求定量证明翻倍的指令；是否改变预测保守性未做消融，不能声称没有效果。

两次shell均明确：当前价接近翻倍门槛的一半是定义结果，不是独立反证；possible不要求量化估值桥或明确未来目标价。两个Plan分析段不同，均要求证据组织/权重和不自行预测；v170新增显式shell权限说明，未发现Plan明确引入强制价格证明门。

仍需整改/验证的内容风险：

1. code生成的context_contract写numeric_decision_inputs_permitted_only_in=[prediction_baseline,computed_metrics]，注释亦泛称numeric decision inputs。字面范围会把已来源接地的收入、现金、订单等数值排除在外；实际意图应仅限runtime价格锚和市场算术。它两次都存在，不能单独解释本次下降，但妨碍宣称当前合同无歧义。建议后续在owning spec中明确scope并用实际完整请求回归检查。
2. ATI原答称合同数额相对current market capitalization不够大。实际最终用户payload无market_cap/market capitalization/market value/equity value文本或有来源市值块；来源合同与经营数据仍在。不能接受这个未展示的比较为已验证内容，更不能因为历史结果为正就反过来规定合同必然支持正面判断。
3. 当前价格/历史涨幅没有翻倍，被写作未来翻倍的负面依据；缺定量桥又被用于否定机会。属于输出任务理解/依据问题，prompt已禁止但未保证遵循。既有validator检查结构、算术、来源与部分语义，不能普遍核验所有推理。应以“只允许交付证据推理、价格锚只定义标签、经营数值正常可用”的干净最小合同做同输入消融，不能加一个强制预测正面的规则。
4. ATI曾将截至预测时点有关Q3实际指标的多面need记resolved，但引用包含不同期间的guidance/合同事实。现有full ownership是通过的模型判断，仍需核验“问题的每个facet与期间确实被回答”；引用存在不证明need完全解决。本报告不据此断言它必然导致负预测。

所以本次没有确认“其余全正确，仅纯能力噪声”，也没有证明哪个prompt改动因果造成反转。可确定的是输入变化、正确交付、输出依据有缺口、实际经验消费未覆盖目标项。

## 已有机制及缺口

已有链路：Posthoc结构化reflection_items → Case/Plan/Round additive archive → ReflectionMemoryIndex的稳定来源/brief/原文读取 → Slow H1 meta_info及选读原文 → Mining候选。source/indexes负责可追溯；fact、hypothesis、action分开，sources_checked不等于语义真。技术排除不能被当作经济研究失败。

v170两案共10项，事实描述FN，假设讨论价格目标/历史价格锚/催化剂权重，动作建议拆开binary与magnitude。它们已写入canonical记录和提交meta，并由v171 bootstrap完整导入。读取实际controller payload发现0/10到达；不是“尚未保存experience”，而是没有成对比较层、有限选择未覆盖这两案。其他案的事实和部分动作进入21项池/5项初始页，所以不能称整个experience链都不工作。

现有parent comparison主要给Plan结构及同snapshot aggregate metric_delta；Round reflector只比较当前新Plans，v170只有一个完整Plan而明确skip。Signal ledger的disputed_observations关注相同case/signal/input的因子结果冲突，不能替代最终Predictor跨运行反转。没有发现自动按同case+time组成v168/v170原始输入、输出、差异和技术排除的pair记录及专用消费契约。

## 建议如何补齐（设计建议，未实现）

复用现有不可变trajectory、ReflectionItem/索引与Slow消费通道，不另起一套自由文本经验库。完整反转不自动升级为可信经济规律。

1. **先建派生对照。** 只读取当前contract授权且pointer可达的记录，按证券身份+prediction_time+标签合同对齐。保留双侧源record/prediction/request hash、Plan/Registry/模型/参数/实际payload hash、方向及幅度结果、选中证据/固定prompt/修复差异。身份hash由不可变内容决定；不要按同名plan_r0001_c02合并，也不要扫描未授权目录凑pair。
2. **分层归因。** 技术失败进工程诊断；错误PIT/引用/未回答facet进内容审计；输入不同标changed-input reversal；只有实际payload与参数相同、独立生成不同答时才标same-input instability。当前两案属于输入变化且归因未闭合，不能打“纯模型摇摆”标签。归因未知也保留原件。
3. **经验仍用content+indexes。** content分为机器可证的反转/输入变化事实、待检验解释、可在预测时点执行的研究动作；indexes同时指向双侧原件和关键证据，反证/限制同行保存。学到的不能是“该股票后来上涨，所以遇到它就预测正面”。LLM只补解释和研究假设，不填写hash、分组、数值统计或裁定技术清洁。
4. **消费闭包。** Slow按当前方向/幅度研究目标选取成对经验的完整小单元，可翻页到全部授权项并按ref读取双侧来源。预算限制context而不让上游deferred项永远不可发现。记录available/selected/disclosed/referenced/disposition，区分读取、采取研究动作、提出候选与实际入库；有代表性的反转可以先于重复FN描述，仍要保留稳定失败、成功与反例。
5. **分流研究对象。** prompt理解/组织敏感首先给Plan或固定合同实验；经济因子必须能从预测时点Raw Info执行，不能把“LLM反转”“未来上涨”本身当因子。方向可测试guidance/新合同与历史价格反证的条件关系；幅度应在独立高/低幅度组比较，同案2.018x/2.065x是ge3控制而非高幅度正例。候选通过既有技术门即可入库unverified，再持续追踪效果。
6. **验收。** 实际双侧来源构造派生pair；技术失败与未知归因隔离；新周期实际Mining请求能发现、读取并引用该经验，未读可见；重启/导入身份稳定、重复同案不算独立样本；blind Fast不收到pair标签。独立Plan/prompt消融及因子absent/present实验才证明收益，不增加召回率评分捷径。

这是一类高价值诊断，价值来自可定位差异和可检验条件，不来自“摇摆越大越值得信”。本次不新增生产schema、读权限或自动反转优先规则，相关合同更新与实现是后续工作。

## 验证

0外部调用。四份实际request/response hash、85 selected Basic卡完整留存、生产身份投影及逆恢复、原canonical base的ATI native patch/量化claim-link检查、v171 24份实际controller payload trace通过；机器报告保留可复核hash。未重跑全量代码测试（没有运行代码修改），未声称prompt改善、全流程无技术失败或新因子完成。仓库lint与git diff --check通过；本轮只提交审计报告、进度和经验咨询记录，未重跑全量代码测试。

# v174 真实Update候选与不可变fixture验收

2026-10-02，冻结fec68554，独立诊断区`runs/cold_start/live_stage_validation_v174`，单独4 attempts/$2上限；无Fast/Slow pointer提交。使用v171真实截断请求的原target、案例/证据和immutable template，不改变原v170固定24评分、标签或v171两已有发布更新。

[实际产物与请求hash](v174-update-component-acceptance-20261002.json)：静态prompt去掉复制baseline歧义后，一次真实Update输出2010 tokens，完整parser通过；共享程序仅把错误的changed_paths声明恢复为实际diff `spec.raw_retrieval.query_terms,skill`。模型实际追加customer-level evidence要求、排除内部property/segment mix和无归属的aggregate order-book proxy，未翻转不可变定义/fixture的负向含义。模型选择source refs，canonical facts恢复为完整原文，没有抄写长HTML造成截断。

生产`validate_signal_update_candidate`再次核验stable spec/skill/tests和精确diff，候选实际stage为`customer_concentration:v3`。真实`SignalCandidateValidator`经`StructuredLLMSignalRunner`执行原“One customer represented 72 percent of revenue.” fixture：negative预期通过，1 executed test，0技术/契约拒绝，tests原样；输出151 tokens。schema、版本、来源/PIT、执行和语义去重门未放宽。两次paid调用合计$0.01055852。

原v172两个不同axis缺rationale的真实native patch均已通过；v172/v173的零diff错误和缓存保留。这次证明了修复后的真实Update产物和不可变fixture执行，**不是完整新Slow发布**，candidate只在独立诊断区stage，不是已提交/可调用生产因子。v171的financing_listing_action:v4和guidance_acceleration:v3仍是已提交、效果unverified的两个更新。最终250相关、1475全量和lint PASS。

继续验收：保留v171已提交发布，进入生产后继Fast/Slow；固定24完整Fast技术排除目标0，direction/magnitude新挖掘及publication、跨周期消费/性能追踪与独立magnitude贡献仍未完成。不依据这个组件的两次成功调用推断总体失败率0。

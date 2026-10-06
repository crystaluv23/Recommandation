# v182 Reflect 目录与读取链路审计

本次修复恢复已有渐进披露合同中的可达读取，不改变研究分类、Signal 技能、评分、来源时间定义、Registry 或正式完成指针。没有新外部模型调用。

## 原始证据与缺口

- 固定运行：`runs/cold_start/minimal_rounds_v182_integrated`，冻结代码 `85ffff9ed976cc4597b7e6e26a2dfe7537ab4099`；终态 Fast/Slow 1/1，未重启或热修改。
- Enbridge 的原 Reflect 10 与 251 均展示最旧 20/70 张卡，`next_cursor=20`、遗漏 50。底层 `document_catalog(cursor=...)` 已支持分页；私有 provider 和 Reflect 适配器没有可用的翻页动作。
- 原按 ID 的 fetch 只查时间，未查公司。受控跨公司反例证明已知另一公司 ID 可被读取；没有宣称原运行发生了这样的读取。
- 原语义纠错重新调用时只重建第一页，已读正文和计算卡没有再次提供给模型。最终上下文仍存正文，这不弥补纠错当时的不可见。
- 原提示称 fetch 返回完整文档且可作为 State 证据；实际 fetch 对大文档返回有遗漏标记的有界视图，ResearchState 只接受已有 Basic Info/Signal 引用。

## 通用修复

先更新两份 owning spec，再修改真实 producer/provider/adapter：

1. `inspect_document_catalog` 调用原 data-owned cursor API。既可复制 next_cursor，也可用合格范围中的整数位置直接访问后页；第一页排序和 20 卡上限保持。
2. 分页、fetch、compute 共用原两次交换预算，重复页、非整数/越界 cursor、批内及跨交换重复 fetch 均拒绝。没有新增免费模型交换。预算/候选停止异常保留此前交换的真实用量并原样传播。
3. fetch 在产出视图前对完整批次检查公司和截止时间；混合无效批次不持久化部分视图。
4. 普通语义纠错保留已读目录页、正文及计算卡；机械专用纠错继续没有读取通道。
5. 固定提示说明有界视图与最终 Predictor 的 provenance 消费，不承诺读取会生成新的 State 引用资格。

## 真实资料回放与亲读范围

重验本案 73 份冻结源文件 hash；原请求 10 的文件和 payload 精确绑定，第一页面的 20 个 document ID/content hash 与 data-owned 输出逐值相同。底层四页共 70 个唯一合格 ID。本人亲读后续 50 张目录卡；这些是目录内容，不等于审读了所有原始文档全文。

脚本在原私有适配器的真实 payload 上发出 cursor 60 和一次 fetch，共两次交换，读到 `avnews_3721f2ced165d723c23e210c`，hash `c601740ac91214457e242c74c87de9afd14b546e69c8408ab68a21813810646e`。本人查看完整 492 字来源和 verbatim 产物：这是 2025-08-14 的 EGLE 公共意见期 provider title/summary，明确截至 8 月 29 日；不能在 9 月 30 日写成仍开放的活动，也不能称为 publisher 完整文章。

另以原 canonical initial_state 和 Signal batch 进入生产 `LLMResearchController.reflect`，保留原 paid patch 的真实 base_hash/operations，三次脚本响应后通过完整生产 State 验证。直接使用匿名 wire state 会有另一 snapshot hash，不能冒充 canonical base 或改写旧 patch。

随后以生产 final-context assembler 将新读取视图追加到原案例上下文，保留原文 hash/offset 与身份投影，JSON 保存/重载后逐值一致。生产 Predictor 收到这个上下文并接受原 12 预测。原 Reflect patch、旧预测、旧来源和正式指针均没有修改。读取动作和旧回答由脚本提供；没有证明模型会自行选择该页面、利用新证据或改善预测。外部 HTTP wire 全链身份投影不属于这份回放。

## 验证与剩余验收

9 个新测试方法覆盖真实 Controller → provider → page/fetch → final-context JSON 消费、语义纠错与机械隔离、计算卡保留、公司/PIT/混合批次/重复/预算和下一案例隔离。156 相关测试 PASS，1613 全量测试 PASS（53.877s）。同一组新测试对冻结旧代码预期失败：11 个 assertion failure、5 个 error，包含未注册动作提前返回和已读内容缺失；不是新代码的失败。

lint PASS，最新 pre-push feedback 已逐项读取。实际运行仍有 6 个 Signal 校验失败，新 magnitude 入库数 0，全部正向幅度 2–3x；方向 v3 的后继使用、真实学习收益和其余案例内容仍未验收。来源可用时间合同与独立评价方案仍待用户选择，本修复没有替代该选择。

完整来源卡、所选原文、真实输出、新固定 Reflect prompt 和验证信息保存于同名 JSON。后续 live 必须固定新代码和经确认的新输入，分别验证读取采用、真实 Registry/反馈消费及独立增益。

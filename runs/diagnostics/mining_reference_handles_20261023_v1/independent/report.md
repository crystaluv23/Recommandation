# Mining reference handles 独立反例复验

最终产品 `mining_role_model.py` SHA256为 `2a77e131596e4cefd9dff8a91ea38fcc36bbb5e790ccb205949158c2acd06910`；本轮24/24通过，结果为 `retest-2a77e131596e.json`。只新增独立诊断脚本/结果/本报告与bindings，未改产品；未读取LabelStore/真实标签、未访问网络/API、未重入封存stage或修改source/oracle。

首轮15控9过6失败；先保留过宽operand整对象断言的 `first-results.json`，修正为仅要求fact.value原样后 `latest-results.json` 仍9/15。产品修复后原15全过，扩展24控22过2失败（`retest-9f64aabfc313.json`）：默认Signal目录scope=None与inspect_manifest的last result重复投影仍改原始内容。此次按action保护后24全过。系统Python3.9导入失败保存在 `first-environment-failure.txt`，实际控制使用项目兼容bundled Python。早期脚本修订未单独存档，最终脚本保留原15及新增9控；各历史结果绑定其实际产品SHA，不能据此声称已重现早期脚本的逐字版本。

通过项涵盖原始memory/content/Signal spec、任意semantic field/value、嵌套fact.value、manifest与默认/显式目录结果保真；patch引用与rationale分离、measurement整体保真、exact权限与guard往返；未知/错类alias和重复反投影key拒绝；typed索引决定类型；异图cache scope区分；原生identity projection后handle inverse。原始失败均保留。

关闭范围仅为这些合成离线反例的本地连接与保真。本审查的cache检查是scope discriminator不同，identity检查是原生投影器的纯内存往返；未独立重复完整生产caller/cache试验、完整payload费用估算或任何fresh模型行为。4221refs/完整请求装入结果由父流程另验，不能替代fresh Mining终态、候选准入、consumer执行或研究收益。产品后续改变SHA时本结论需重新绑定。具体文件SHA及命令见 `bindings.json`；bindings不包含自身hash。

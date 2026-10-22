# 分类定义进入 critic / Slow 的持久化方案

当前修复可让实际执行的分类声明到达 Reflect、最终 Predictor 和 Posthoc；但真正的 Plan Critic 会再次压缩轨迹。它的原件来自 `CaseReflectionEvidence.from_trajectory().to_model_dict()`，只保留反馈、自反思和执行失败摘要。该 canonical meta 记录没有分类声明，`ReflectionMemoryIndex._cases` 因而也没有相应可读原件。仅修中间 `_plan_critic_trajectory` 不能关闭这条消费链。

需要决策的是如何保存这份 runtime control data；不改变 Signal 测量/类别/阈值、评分、PIT、准入、标签边界或模型权限。用户的 AGENTS.md 要求涉及 canonical schema / 接口实质取舍先准备具体方案并取得决策，因此以下新增 canonical meta 字段尚未实现。

| 方案 | 具体实现 | 代价 |
|---|---|---|
| A：CaseReflectionEvidence 增加可选完整声明字段（推荐） | 新记录可保存 `signal_classification_context`；每项为 exact round/ref 和实际保存的声明。复用现有 case source、catalog、read_refs 与 meta 序列化。 | canonical meta 体积增加；无需另建文件、resolver 或提交协议。 |
| B：只保存可选声明引用，正文另存不可变档案 | meta 新增 typed source handles；正文按 hash append-only，新增档案解析、源读取及恢复绑定。 | meta 较小，但新增存储/查找接口、路径权限和原子持久化/恢复要求；实施面更大。 |

A 的新字段形状如下；`contract` 是现已实现的执行声明对象，不是模型作者字段。

```json
{
  "signal_classification_context": [
    {
      "signal_round": 1,
      "signal_ref": "liquidity_runway_months:v3",
      "contract": {
        "signal_ref": "liquidity_runway_months:v3",
        "spec_hash": "<frozen spec hash>",
        "result_hash": "<canonical executed result hash>",
        "definition": "<exact frozen description>",
        "execution": "<complete actual callable declaration and configured parameters, or frozen LLM skill>",
        "declaration_available": true,
        "source_contract_hash": "<present only after identity projection>",
        "contract_hash": "<current declaration/view hash>"
      }
    }
  ]
}
```

落地时 `execution` 仍是现有完整对象，上例仅缩写显示。字段缺失表示未知；旧记录读回/重建/保存保持原形与 hash，不追加今天的定义。新字段只能从实际 trajectory 的保存声明提取，并逐 round 对 canonical result_hash 校验；不能按 ref 合并、从 validator/default 函数表重建，也不从模型反思文本恢复。

`ReflectionMemoryIndex` 为每个声明注册独立 case source unit，沿原 case/plan/round scope 与 source refs 供 Plan Critic、Round Reflector、Slow 读取。原反馈事实 snapshot、outcome 身份及反思修复权限不扩展。初始 catalog 只给身份、范围和完整字节数；读定义仍计入现有阅读与实际 request/case 预算。正文完整保留；超大 unit 若在原预算下不可读，明确显示大小/不可读缺口，不能剪裁后当完整定义或擅自加预算。没有这份声明时保持分类含义 unknown，也不能从股票方向或数值正负号推断。

验收需要走实际 source unit、catalog/read_refs、最终 Critic/Slow 请求，而非仅调用中间 helper。至少核对同 ref 不同 round/result、旧记录无字段、错误结果/版本绑定、override、非默认/重叠阈值、unbounded/technical failure、匿名后 hash、超长 skill 与多 case payload。新模型遵循另以预先冻结的原生 inbox/outbox 独立 subagent 验收；外部 API 继续为0，旧消费者语义0/1保留。

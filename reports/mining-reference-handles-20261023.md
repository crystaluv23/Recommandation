# Mining大图引用的无损表示

本轮在封存v3之外修复完整角色请求的引用表示。外部API/网络/新业务标签0；没有生产作者、候选、准入、发布、业务指针推进或旧stage续答。原v3的10答/2055941消费及single-budget终态保持。方向/magnitude新能力及MVP仍未关闭；真实query原文坐标交付是下一独立修复项。

## 问题与最小修复

v3下一完整输入264980，比single262144高2836；2879个fact和1342个relation引用共4221个，索引占115160（43.4599%）。局部正文/目录页各自未超限，首次请求能装入不能证明后继完整图谱能装入。此处不删事实、不裁正文、不换source或加cap。

owning spec先声明：compact索引超过8192bytes时，在MiningAgentRoleModel预算估算前将完整已知引用渲染为确定性的request-local短handle。小图保原wire。隐藏双向表来自排序的typed索引，namespace扫描完整payload字符串/key避碰；完整映射hash随payload进入实际请求/cache identity，防同形异图复用错误答案。kind来自索引而非名称前缀。原生identity反投影后、Controller校验/patch前还原引用；未知/错类handle与重复还原key拒绝。全部成本及scope元数据计原预算，旧预算已用值不重置。

只改结构引用槽和既有typed patch的引用值/guard/exact权限；路径、canonical basehash/ledger/source/hash/原件保持。source content、嵌套fact.value、measurement/falsifiers、Signal/backlog/memory原件和whole method memory是opaque literal子树。完整manifest及四scope目录result在last/cache重复投影中同样保护，包括默认scope=None。短handle不给新读证据、测量含义、case或修复权限。

## 反例、首失败与最终验证

[独立反例审查](../runs/diagnostics/mining_reference_handles_20261023_v1/independent/report.md)首15控9过6失败；其中一条过宽operand整对象断言修正后仍9/15。它揭示原始memory/catalog/Signal spec、nested fact.value及semantic threshold内同名字段被误改，另有按fact-字符串猜kind的泛化限制。第一次修复后扩展24控22过，仍漏默认Signal目录与manifest的重复原件；按action补全后最终24/24通过。首轮环境错误、各轮失败及实际产品hash均保留；早期审查脚本改版未逐字另存，不能宣称其早期脚本逐字可复现。

父focused首15有1fail/1error：测试把2879+1342误加为4211，且synthetic view漏原生stage必需字段，原日志保留，纠正为4221/真实Controller基础view后15过。不是两处产品语义错误。新增回归覆盖无损全图/ordered operands、literal碰撞、异图cache scope、wrong-kind/unknown/duplicate-key、typed patch与原生identity/cache往返；均为明确离线fixture，不计fresh模型能力。

首次关联477中476过/1error：旧v3 oracle正确拒绝活跃新版spec的hash drift。没有更新原oracle；测试改为仅在TemporaryDirectory复制原oracle并重绑当前测试代码合同，原15语义义务/来源/资源未改，另新增原frozen oracle必须拒新代码且不建root的断言。该临时fixture无生产作者/答案，不是新的正式验收授权。中间480过后再补重复投影修复，最终[481关联](../runs/diagnostics/mining_reference_handles_20261023_v1/associated-test-bindings.json)全过，31.376秒，测试前后源码hash同，socket tripwire0。独立结论限合成反例；父原生完整caller/cache测试与成本捕获分别出证，不混作同一独立证明。

## 完整实际输入的零接收捕获

[完整成本结果](../runs/diagnostics/mining_reference_handles_20261023_v1/capture-result.json)使用已封存下一输入副本、同一原生Caller/assignment/identity消息构造及原single262144/Mining80与12MiB限额。保reserved_calls10/reserved_tokens2055941，只在request_ready捕获，receive与网络禁止；没有新prepare/inbox/answer/receipt。旧请求只作原始输入，不回放成新模型输出。

4221引用及全部正文/目录/memory逐结构还原与原payload相等；捕获完整消息+output的精确预留**230052**，比264980省**34928**，距原single余**32092**。self-disclosure与完整wire成本相等，原已用预算保持；316封存文件和312终态hash表均同。初版及最终捕获产物分别保留，最终绑定实际代码/spec/tests版本。这个数值只证明该输入在当前表示下装入，不证明未来所有请求装入、模型服从、候选成立或复用完成。

下一步将既有fetch(query)内部真实projection→raw origin交付为有界discovery-only导航，不用近似find锚点、不添加免费读取/引用权；继续普通charged read核原文。先离线反例和完整成本检查，再确定新版本验收的冻结与不重置既有资源的计费边界。已封存v3保持终止，无h011或自动新控制。

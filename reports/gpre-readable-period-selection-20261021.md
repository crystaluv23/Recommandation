# Latest financial measurement inputs: diagnosed selection gap

The completed capture source stage admits the full57-product GPRE set without
changing old records. Its two exact Registry groups each resolve17/18 inputs,
but that fraction does not prove latest-period measurement inputs were selected.
No Signal was executed in this phase.

Each group has nine financial requests. Only two select the structured Q1
document; seven omit it at the ten-document limit. Cash reserves also selects the
latest Q1 narrative filing, so these seven diagnostic flags must not be described
as seven absent latest reports or seven executed measurement failures.

The concrete cash case is independently reproducible from actual saved inputs:
[root parser probe](../runs/diagnostics/reviewed_gpre_capture_preflight_20261021_v1/independent/root-cash-readability-probe.py),
[result](../runs/diagnostics/reviewed_gpre_capture_preflight_20261021_v1/independent/root-cash-readability-result.json).
The saved `cash_reserves:v2` request asks for the latest point-in-time balance.
It selects ten of59 eligible documents, reports its generic contract satisfied,
and marks selection truncated. One selected document is the latest Q1 HTML
filing. The actual native fact parser accepts two JSON schemas and yields no
facts from that HTML. Its latest selected cash fact ends2023-12-31, in USD; the
eligible but unselected structured Q1 document provides a parseable2025-03-31
cash fact in USD. This is a demonstrated input selection/readability gap, not
an executed cash measurement or a claim about all seven outputs.

Read-only driver diagnosis reproduced all18 saved selections in each group
through filtering, deduplication, ranking and bounded selection. The seven
structured-Q1 candidates fall outside the first ten. They are PIT/type eligible;
required tags, currencies and relevant comparison periods are present. Query
ranking uses raw token occurrence counts before availability, favoring long old
annual documents. Generic source-group/period-count coverage does not ensure
the current measurement concept is readable. Cash burn and runway retain Q1
because their publication lookbacks leave only four or six candidates, all below
the limit; those controls do not establish correct ordering under truncation.

The producer is `SignalExecutor._resolve_input`; the consumer's actual financial
callable owns supported schemas, operands and latest/comparable period selection.
The producer currently passes generic source/query/coverage requirements and
omits that measurement relationship. The resolver already supports a
`select_documents` callback after PIT filtering and deduplication, and validates
its returned members and limit. A scoped repair should use this existing entry,
owned by the actual callable, preserving the ten-document ceiling and generic
fallback. It must retain needed comparative material, units, conflicts and missing
input semantics. Do not parse prose to invent a measurement contract, hardcode
Signal/company IDs, globally replace query priority, expand lookbacks or limits,
or add a permanent canonical field to conceal the mismatch.

Earlier fixture consumers had fewer candidates than the limit; source-admission
and minimum-period checks therefore passed without exercising this failure.
Actual57/59-candidate consumption exposes it. Before another model stage, verify
the original case, long old-document repetitions, applicable latest/comparable
variants, missing latest operands, incompatible units and incomplete comparison
periods through the existing selector/consumer path. F7's original0/1 and its
unverified prompt repair remain separate. No complete successor is authorized
by this diagnosis.

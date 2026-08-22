# Live Evolution Context Audit

visit_times: 1

## Trigger

Use this when auditing a real Information Plan / Signal evolution run, especially
when the request asks whether actual prompts and contexts match the design or where
tokens are being spent.

## Lesson

Code inspection is insufficient. Open the exact persisted request and response for
every reached role, parse the user payload, inspect literal source spans, and join
request hashes to attempts, per-case trajectories, rejection artifacts, committed
pointers, and the Registry hash. A failed real run is evidence that the current
contract does not run through; do not replace it with a historical success claim.

Audit value-level boundaries, not only field-name allowlists. Identity can re-enter
compact retrospective context through free-text information needs and then be copied
into Plan critic output, Round meta, and the next proposer even when case ids and Raw
Info fields are absent. Scan actual request values with the exact case alias inventory
before every retrospective/model handoff and before meta persistence.

Token accounting should start from provider-reported input tokens grouped by stage,
then measure repeated payload components directly. In this runtime, high-value checks
include zero learned profiles repeated per Signal card, HTML boilerplate in SEC literal
projections, the same Raw Info sent to several soft Signals, full original context sent
again for post-hoc reflection, repeated case packets across H3 hypotheses, and additive
meta entries sent in full. Keep complete artifacts locally even when the model-facing
view is normalized or compacted.

Finally, verify that selection contexts contain enough information to perform the
promised semantic job. A label-hidden Signal Mining ranker cannot rank hypothesis
applicability when every company brief lacks business, industry, sector, and size
fields, even if its JSON shape and anonymity checks pass.

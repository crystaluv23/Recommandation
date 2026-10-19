# Local role integrity and legal-prior repair

This is the next local repair after checkpoint `929b1911`. No new role outputs
or external API calls are claimed here. The original seven-case v2 outcomes,
thirteen raw responses and receipts remain immutable. The new batch will freeze
separate inputs and independent expectations before fresh role execution.

The old implementation failed two deliberately adversarial production-boundary
checks: two clients simultaneously admitted requests against a one-call ceiling,
and a cached object was accepted after its parsed value/raw answer changed.
The tests failed on the old code before repair. Admission now serializes the
contract check, count and atomic inbox publication with a shared-root OS lock,
across clients, threads and processes. Replays consume no additional slot.
Cache reuse now verifies the original inbox and receipt, reads raw bytes once
for both SHA checking and decoding, reparses with the original parser, and
compares the entire cached record with that verified raw/receipt identity.
Missing originals, changed agent receipt, changed cached JSON or raw bytes reject
without another dispatch. Internal costs/tokens remain unknown, no logprobs.

Temporal acceptance now carries the actual aware runtime instant throughout
initial validation, routing, partial residual construction, disposition and
fallback. Complete ISO timestamps support `Z` and offsets. Equal/earlier and
equivalent-zone bounds pass; same-day later instants, naive/malformed bounds and
future actuals/publication do not gain an allowance. Future source-publication
timestamps are checked independently of a valid as-of clause. The old code
failed seventeen valid-bound variations and one datetime/date comparison; an
additional adversarial pair exposed future publication timestamps that the
date scanner missed. Those failures were reproduced before the corresponding
fix. Date-only/symbolic semantics and explicit-bound/framing requirements remain.

The new driver preflights all seven priors through real normalization,
reference and residual validators. Five synthetic priors now state the complete
aware cutoff. Future-actual material remains an explicitly labelled fault
injection, not trustworthy source input. The consumer branch uses accepted
stage deltas and aliases through the actual production assemblers. A test feeds
the real previously accepted positive shape through this same driver branch;
the old illegal prior fails preflight. Failed stages retain their request trace.
Backend `independent-subagent` identifies execution, while precise inherited
host-model version is explicitly `null`/unknown.

Validation: 1708 full offline unit tests passed; after the final two timestamp
publication counterexamples, all 114 focused temporal/role/driver/consumer/
exchange tests passed. Shared-root concurrency is tested in threads and separate
processes. Local checks establish these mechanical repairs only; fresh role
execution, all production factories (including the direct remote Jev path),
trusted-source admission, Slow and whole-loop recovery remain separate work.

Independent reviewer `/root/acceptance_review` reran the fourteen exchange tests
and additional socket-forbidden counterexamples: eight separate clients against
ceiling three and eight separate processes each yielded exactly three pending,
five exhausted and three inboxes. Ten cache-after-tamper/missing-original cases
all rejected with no new inbox or reconstruction. It found no new blocker in
this local boundary and supports closing the two demonstrated integrity defects
at the local evidence level, not the full MVP.

The existing convergence record now names the approved engineering milestone,
records the real local batch and review, and keeps independent benefit unknown
as a later milestone. The current chat's active goal receipt is the root's actual
tool read; it does not resume the old experiment. No full successor is planned,
and source/manifest plus remaining content/feedback prerequisites remain pending.

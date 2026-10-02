# Committed Signal use tracking

Own the deterministic bridge from committed learning events to target evaluation
records and bounded retrospective profiles. Depends on Signal Library and approved
research target contracts. It performs no model calls, candidate admission,
prediction or causal benefit evaluation.

`record_committed_signal_use(registry, events)` records exact learning events and
then target use records. Only pointer-reachable Fast records or hash-verified
committed imports may call it. Restart rebuilds missing derivatives idempotently.
Direction is the legacy declared purpose; additional targets require exact-version
published admission metadata. No magnitude use is invented for old versions.
A valid execution with revealed outcome is `inconclusive` (observed, effect still
unverified); unavailable measurements are `insufficient_evidence`. Technical
execution failures remain in canonical trajectories/statistics, excluded from
research effect counting by the existing learning-event producer.

Evaluation identity binds physical observation key, exact version, target protocol
and its contract, state/coverage and realized outcome; multiple Plan reasons retain
separate learning events but share a target record. The actual first write time is
saved once and reused on restart. Neither matching direction nor high magnitude
alone is `supported`.

`target_use_profiles(registry, signal_ref, round_cutoff=...)` derives per-target
state/outcome matrices, eligible/outside-population/unavailable/disputed counts,
unique issuer/case observations and mean realized multiple by state. It uses only
record-backed learning events before the cutoff, deduplicates physical observations,
and excludes conflicting state/coverage from measurement association. Conflicting
immutable outcome/source identity fails closed. Profiles preserve a source hash
and never expose issuer/case ids. They are observational selected-use evidence,
not an independent holdout or causal attribution; no-effect-observation stays
unknown rather than zero-filled supported effect.

Slow publishes these summaries as `signal_target_observation` source units visible
to reflection/H3/E2/Update. H1 and blind prediction do not read target outcome
summaries. Existing individual usage source units remain available for audit.
Independent paired evaluations retain their separate protocol and are not folded
into use observations. Technical admission remains independent.

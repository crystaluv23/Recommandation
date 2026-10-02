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

Cross-workspace round numbers are independent. `imported_learning_events(root)`
reads only manifests bound by the hash-verified frozen run contract (bootstrap
or history, including history attached to a Fast/Slow successor). A manifest
without its contract is not authority. Imports retain exact event identity and
source round; conflicting ids, malformed envelopes or changed manifest bytes
fail closed. Evolution Control uses this same reader for transitive export.
Consumers pass these exact events to Registry's committed-event selection and
`target_use_profiles(..., imported_events=...)`. Selection unions local cutoff
events with explicitly imported events only after exact Registry content checks.
Imports may refer to immutable prior versions after a newer version is published;
existence means the exact version definition is readable, not that it appears in
the current stable-card menu. Every imported version's ledger copy is verified.
Older observations remain attached to that version and never become a new
version's routing profile or evidence of effect.
Slow feedback enumerates immutable versions, including historical local versions,
and applies the committed cutoff/import checks to each. Publication does not
erase prior usage or target observations from retrospective research.
The target local pointer remains unchanged. Unknown ledger events beyond that
pointer remain excluded; source round maxima never enlarge local authority.

Slow publishes these summaries as `signal_target_observation` source units visible
to reflection/H3/E2/Update. H1 and blind prediction do not read target outcome
summaries. Existing individual usage source units remain available for audit.
Independent paired evaluations retain their separate protocol and are not folded
into use observations. Technical admission remains independent.

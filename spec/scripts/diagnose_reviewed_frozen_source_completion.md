# Fixed40 explicit source-completion executor

This new source-only diagnostic consumes an explicitly assembled, reviewed local
bundle. It never resumes the completed preappend stage or either earlier input
matrix. `prepare(bundle_path, output)` freezes a new stage without constructing a
global store, appending, materializing a view or running consumers.
`execute(output, expected_plan_hash)` is a separate, single terminal action for
the sole root/driver executor after its concrete freeze has been reviewed.

## Explicit bundle

`schema_version=frozen40-source-completion-bundle-v1`. Bindings name exact local
bytes (`path`, `sha256`): `projection`, `original40_plan`, `base_inputs`,
`preappend_result`, `operating_review`, `collection_plan`,
and `collection_results` (including its actual `dispositions` list). `evidence_bindings` retains supplemental receipt,
market request-record, actual normalization and post-fetch body-review artifacts.
All95 collection plan requests and terminal dispositions must be present; a
successful GET is a candidate only. Do not invent receipt fields or modify old
requests. An additional FTI daily normalization/proofs is explicit supplemental
evidence, never an implicit96th request or an invented retrieval clock.

`candidates` is an explicit list, not an auto-admission flag. Each candidate has
`document` (a binding to the complete canonical RawInfoDocument), `target_keys`,
`proof_profile`, `proofs` and a nonempty `reason`. SEC narrative candidates also
have a `semantic_review` binding and exact `semantic_target` (`case_id`,
`accession`, optionally `document_id`). Before global writes, every candidate
must pass the current native profile and all source/ID/case/PIT/body/canonical
checks. Filing semantic evidence must bind the same body hash and target and
prove complete annual/interim or an explicitly reviewed whole AIF/MD&A body;
form/TOC/length/receipt-success flags alone do not qualify it.

For the existing operating-content review, use its actual per-target
`content_scope_verdict`, exact body hash and an identified actual original.
HITI's wrapper/embedded financial statements and FTI's persisted wrong exact
type stay unknown. Its located AIF/MD&A links do not admit unfetched bodies.
A new narrative content review uses explicit `records` with case_id,
accession, document_id, content_hash, `content_scope`, `qualified=true`, reason,
`review_read_scope`, and literal source bindings. Selected-section/partial-fact
review can establish report material scope; it never claims full model reading
or changes BasicInfo's context-budget flags.
The record's `body_binding` must equal the selected profile's actual body
carrier: `sec_static_archive_body.artifact` for the managed legacy profile, or
`sec_static_archive_body_response.raw_response` for primary/exhibit response
profiles. A submissions root/archive, receipt artifact or exhibit-parent body
is not a substitute even when present among the candidate's proof bindings.
For managed proof, read the exact envelope's whole body string; for response
proof, reuse the native receipt/raw-response decoder with actual compression.
Require that whole decoded string and its content hash equal the canonical
document and semantic record. Binding membership or a declared content hash
alone cannot establish that the semantic reviewer read the proved body.

`target_dispositions` preserves each target from the completed preappend result:
842 financial product IDs, all24 market case families and all41 operating
case/accession targets. Keys are `family|case_id|member` (market member `*`).
Each has a nonempty `reason` and an explicit `candidate_ids` list, possibly empty
for unknown. No case, target or failed proof disappears. Candidate target links
and disposition IDs must agree in both directions. Financial candidates must be
the exact preappend canonical product and use its exact normalization binding;
all full expected-product sets remain bound, including GPRE's57-member set.
The four conflicting GPRE IDs remain unknown; no revised IDs or provenance are
authorized here. Pending/failed new proofs remain explicit unknown dispositions.

New FTI market content may later use the existing HistoricalPriceAdapter recipe
at the original400-day/May30 scope, with actual normalization no earlier than its
actual cache and native last-bar-next-day availability/content-derived ID. Do
not guess bars/clocks, trim an old record, change issuer policy or reuse an old
ID with changed metadata. Its issuer/splits requests require separate exact
post-normalization scope/proofs; the95-request collector does not expand itself.
`additional_market_products` explicitly binds any such new FTI canonical record;
other market candidates must equal a retained original from their frozen case.

## Freeze and one execution

Reuse the original label-free projection validator and native `_snapshot` for
both exact Registry groups (v6/v12,18refs each); there is no substitute
`_registry`/`_capture` API. Preserve fixed40 order/cutoffs/splits, two720 input
matrices and40 default BasicInfo bundles. Neither phase deserializes or hashes
the old mixed v182 container, LabelStore or LockedTest data.

Preparation verifies the base658 review rows/653 admitted documents, all full
financial expected sets, target coverage, current native proof qualification,
complete canonical IDs and collisions against direct exact global paths. It
freezes qualified candidates, dispositions, all data bindings, old view and
current code/spec hashes before execution. Historical code bindings inside old
terminal evidence are historical facts, not requirements to restore old source
bytes. Output must be new and outside every retained oracle/view/stage root.
Unknown candidates without a persisted original remain separate dispositions;
never put an outside prototype into a reviewed manifest's original_record.

Execution rechecks the entire frozen batch and exact IDs before its first append.
Use the existing native RawInfoStore append/load and complete canonical equality;
keep oracle.json and every pre-existing source file hash. Create a new review
preserving all old rows verbatim, adding only proven original records under the
actual oracle root. Materialize one new reviewed view, check worker and restart
canonical membership, and run only native SignalExecutor.prepare_inputs plus
BasicInfo/resolver projections. Never apply Signals, run roles/models/fullprepare,
read labels or acquire data. Reverify frozen bindings and old/new source inventory
at terminal. A durable exclusive execution-start file prohibits reentry after
any execution attempt, including failure; no copying/resetting an old stage.
Per-row unknowns stay in the disposition artifact and case denominators, never
as negative company observations or a claim of overall MVP readiness.

Use temporary native proof fixtures for qualification, explicit target/semantic
mismatches, financial full-set/collision boundaries and source drift. Any focused
consumer orchestration tests use temporary stores only. No real prepare,
execution, global append, network or broad legacy source-snapshot tests are part
of implementation verification.

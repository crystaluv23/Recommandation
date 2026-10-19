# Independent local roles: first engineering MVP batch

This batch implemented a network-free production role handoff and executed fresh
independent agents at the actual Reflect call boundary. It did **not** close the
engineering MVP. Statistical benefit and remote-provider transport were not
tested. The user-approved [MVP contract](../spec/engineering-mvp.md) defines the
current engineering milestone separately from later independent benefit.

## Frozen scope and actual execution

[Frozen batch](../runs/diagnostics/local_roles_mvp_20261019_v2/manifest.json),
[seven-case oracle](../runs/diagnostics/local_roles_mvp_20261019_v2/expectations.json),
[terminal progress](../runs/diagnostics/local_roles_mvp_20261019_v2/progress.json).
Manifest identity: `ac165c118176432d282c9018b6c634ff2b48ab5bae5be5d2fda1ade8b9534dd8`.
Two original v182 inputs and five explicitly synthetic contracts were frozen
before new role outputs. The original inputs retain their upstream historical
source-pollution limitation; this is an isolated stage experiment.

Thirteen unique exact requests were answered by thirteen independent role
invocations: seven first answers, three native corrections and three later
terminal invocations. All raw answers and actual agent identities are preserved
under `exchange/outbox` and hash-bound `exchange/receipts`. Zero external API,
data-provider or web calls occurred. API cost is zero; internal agent cost and
measured token usage are unknown. Conservative byte-plus-output reservations
are accounting bounds, not measured tokens. Token log probabilities are absent.

The transport uses the actual stage dependency check, identity projection,
production system/user messages, original JSON parser, typed correction and
fallback, state validation and persistence. An inbox carries only model-facing
messages, request binding and output contract; role agents received no oracle,
historical chat or unrestricted repository evidence. Pending and local-call
ceiling exhaustion are control flow. The remote external-attempt ledger is unused.
No completed v182 run, oracle record or old goal was resumed or rewritten.

## Findings by evidence layer

| Frozen sample | Production role frontier | Frozen driver result |
| --- | --- | --- |
| original c01 | First answer correctly preserves Q3/FY need; accepted terminal; all six consumer checks pass | mechanical pass, independent review separate |
| original c02 | First answer correctly preserves Q3/comparison need; accepted terminal; all six consumer checks pass | mechanical pass, independent review separate |
| Q2-only | First answer preserves need; correction uses exact ISO cutoff | rejects after correction; illegal fixture prior and ISO parsing defect |
| public future forecast | First answer full, preserves numeric source, finalizes | accepted role; driver consumer TypeError |
| partial numeric | First answer partial, residual retains adjustment question; terminal accepted | accepted role; driver consumer TypeError |
| future actual | Role refuses future actual and keeps guidance unanswered | rejects after correction; illegal prior and preservation obligations conflict |
| terminal empty owner | No owner disposition fabricated | rejects after correction; illegal prior and ISO parsing defect |

The fixed driver denominator remains seven: two mechanical passes and five
failures. Successful role interpretation cannot silently remove driver failures.
First-answer semantic interpretation still needs independent original-material
review; JSON acceptance and self-declared answer_scope do not establish it.

The old prior need “What is the issuer's Q3 2025 revenue guidance?” lacks the
explicit as-of bound required by the existing temporal contract. This was my
fixture construction error: the harness froze it without prevalidating the
prior state. In a retained-need/empty-owner case the prior preservation duty can
conflict with rejecting that invalid prior. These cases cannot support a claim
that a legitimate prior was rejected. Their original results remain intact.

A distinct real defect is independently reproducible: a correction bounded by
`2025-09-30T00:00:00+00:00` still rejects while the same bound expressed as
`2025-09-30` passes. `_EXPLICIT_AS_OF_BOUND` ends its date match with a word
boundary, so the adjacent `T` prevents recognizing a complete ISO timestamp.
The next repair must parse aware timestamp boundaries faithfully, preserve
explicit-bound requirements, and still reject future actuals, later source
publication and mixed requests. It must not broadly exempt guidance words.

The two accepted synthetic outputs then hit my separate harness omission:
`_assemble_final_context` requires `additional_identity_aliases`; the driver
also supplied no state deltas for synthetic consumers. The original 1691-test
suite did not exercise this new driver branch. Passing those tests never
established the consumer branch. Frozen code/outcomes were not hot-fixed.

## Separate downstream verification

[Companion CLI result](../runs/diagnostics/local_roles_mvp_20261019_v2_consumer_check/result.json)
has its own code identity. It reloads accepted production stage envelopes through
the owning validators, reconstructs real deltas, supplies aliases and builds
actual final-context, posthoc and critic projections. Four accepted outputs
(original c01/c02, forecast, partial) preserve exact dispositions through all
three views and persistence/reload. The other three have no accepted stage and
remain missing. This additional local evidence does not rewrite the frozen
driver's failures. No new Predictor, posthoc or critic model was executed;
critic scaffolding explicitly retains historical prediction/label fields only.
Two added real-CLI tests cover the previously missed positive branch and refusal
to promote a missing accepted stage.

## Source policy and remaining work

The user selected public complete-conference-content availability. The owning
[resolution spec](../spec/src/stock_opportunity_agent/data/resolution.md) now
requires proof of complete public content and UTC boundary; scheduled starts and
earnings dates do not suffice. [Inventory](transcript-proof-inventory-20261019.json)
binds all 26 original transcript files; accepted complete-public-content proofs
remain 0/26. Four old correction proposals remain pending, not published. No
oracle writes occurred. Provider news publication clocks still lack historical
body-version assurance; that source family is not repaired by this role bridge.

The generic production StructuredRoleClient constructor can select the explicit
local backend with frozen `max_local_role_calls`; remote mode is rejected.
Only Reflect has fresh independent role execution here. Other roles, full
production cycle factories, trusted-source manifests, Slow feedback, direction/
magnitude Mining→admission→successor use and whole-loop recovery are unverified.

Independent counterexample review additionally reproduced two bridge defects:
two simultaneous requests can both pass a one-call ceiling before either inbox
is created; an accepted exact cache hit can skip revalidating a subsequently
changed raw response/receipt. These do not alter the serialized thirteen-call
batch whose original hashes still match, but prevent closing generic budget
and recovery correctness. The next batch must add shared-root atomic dispatch
admission and validate local raw/receipt/cache consistency before cache reuse.
Passing single-client tests missed both multi-client admission and post-cache
tampering; the original claims are limited accordingly.

Independent reviewer `/root/acceptance_review` checked all thirteen request,
receipt and frozen-code bindings and confirmed the current originals match.
It independently reproduced both defects: a barrier before two inbox publishes
admits two requests against `max_calls=1`; changing raw output after a successful
cache fill lets a new client return the old cached object with zero calls,
although direct exchange receipt validation rejects the changed raw bytes.
Its close recommendation is restricted to the original two local Reflect
answer-scope→terminal→consumer projection chains, not the seven-case batch or
MVP. The root's [separate semantic review](../runs/diagnostics/local_roles_mvp_20261019_v2_consumer_check/independent-review.json)
likewise limits its conclusions to visible answer scope, not all state claims.

Verification: 1691 offline unit tests passed before the companion was added;
11 focused exchange/real-consumer CLI tests subsequently passed. Repository
pre-push lint passed and its saved feedback was read. These establish named
mechanical properties, not source trust, prediction benefit or MVP closure.

Next smallest batch: fix and test timestamp-bound recognition and the driver
consumer branch; prevalidate legal prior states and representable correction
permissions before freezing an otherwise equivalent variant set. Retain all
old failures. Then ask fresh independent roles under the same zero-API limit.

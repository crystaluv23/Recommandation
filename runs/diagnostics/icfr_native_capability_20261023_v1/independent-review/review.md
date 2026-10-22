# Independent narrative readiness and prospective ICFR stage review

This is a local deterministic citation review and a read-only prospective-stage
review, not a native ICFR capability result. No fixed stage was prepared, no
production answer/receipt was written, no agent dispatched, no source acquired,
and no Check/Locked Test or production label was read. All authored observations,
case associations, candidates and label-map values are explicitly synthetic.

## S4 citation readiness: independently reproduced old/current differences

`citation-results.json` binds exact old `f9904bd5` Controller source and the
current Controller/tools/prompt/spec files. The current source hashes stayed
unchanged during the ten independent controls. The old Controller runs with
the same currently bound tool implementations so this comparison isolates the
Controller prerequisite rather than claiming a full old runtime deployment.

Six source-access counterexamples all reach a candidate with old code, despite
one or more citation refs having no nonempty handoff read window. Current code
rejects all six before state, successful-action count, ledger or validation sink
changes: another case's read; another document in the same case; another case's
event on a shared document; hidden-only markup; a whitespace-only requested
range in a valid document; and mixed ready/unready citations. These fixtures
were independently constructed, not imported from the parent's five tests.

Three legitimate controls remain admissible: matching event read, matching
document read supporting an event, and a matching shared-document read exposing
its fetched case associations. The same source units are available to the S5
handoff. The current code resolves readiness through `materialization_evidence`,
thus reusing actual document/hash/case/read lineage rather than relying on a
global narrative-exploration flag. The normal role instruction and owning spec
state the same prerequisite.

A fourth accepted control deliberately cites a readable statement that says
only hypothetical ICFR risk/no management assessment while the synthetic
candidate asks for an actual management material weakness. Both versions admit
it mechanically. This is expected evidence of the gate's limited meaning:
access/lineage are necessary, but semantic support, orientation, scope,
counterevidence and applicability still require original-material review.
Passing this gate cannot close S4 or S5.

One initial harness construction attempted an entirely whitespace source body,
which RawInfoDocument correctly rejects. `harness-error-01.json` and the first
driver snapshot preserve that mistake. The intended control was corrected to a
valid document whose requested six-character window is whitespace only; no
product code or source artifact changed.

## Prospective stage: static chain and boundaries

`driver-review-initial-bindings.json` and `driver-reviewed-interim.py.txt` bind
the interim driver/spec/tests reviewed. The writer was still adding tests, so
this is not a stable final-driver approval or executed stage result.

The declared resource totals compose: Mining 80 calls/12 MiB, up to two native
candidate scopes of 300/16 MiB, and four Fast scopes of 12/3 MiB sum to global
728 calls/56 MiB. Budget accounting reads receipt-verified unique answered
requests and separate scope memberships. Shared answered cache requests may
count once globally and once in each applicable scope. Pending/no-receive
attempts do not count as answered consumption. Mining's shared model uses
prefix counters and saved terminal checkpoints; frozen phase allowances avoid
putting future receipt totals into reconstructed earlier payloads. These are
code-path observations, not new native answer/replay executions by this review.

The real `_run_controller_mining_axis` remains the Mining entry, with both
seeds and original dev groups and no check cases. The engine subclass observes
native Controller output and seed-owned source handoff, then inherits native
S5 spec/skill/tests, fixture execution and staging. It requires a bound
independent semantic review before `_technical_candidate_validation`, native
admission and `promote_validated_batch`. It records effect unverified and uses
the resulting full Registry for autonomous native Fast selection, execution,
Reflect/disposition validation and final context. The consumer review gates
the fixed four-case result. No authored seed, forced new-ref selection,
effectiveness evaluator, scored business commit or committed-use record is
part of the declared path.

The review receipt validator checks bindings and explicit booleans; it cannot
establish that an independent reviewer actually read the originals or that the
booleans are true. That review must be performed against actual candidate and
consumer artifacts. Likewise native functions existing in this driver, and
synthetic wiring tests, do not establish that one real ICFR candidate has made
the complete Mining→S5→admission→publication→consumer chain.

Code/source/prefix/oracle hashes and baseline version files are checked before
advance. The driver checks zero business pointers, blocks LabelStore/network/
source-store mutation/business-cycle/effect execution, uses independent-local
transport with allow_external=False, and seals terminal results against reentry.
Original historical Slow archives remain provenance, not new committed results.
Pending reconstruction and terminal/seal logic need the final writer tests and
actual stage artifact review before any capability claim.

## Concrete interim issues sent to parent and writer

1. `Caller.complete_json` used `kwargs.get('max_request_tokens') or 262144`.
   An explicitly supplied zero was therefore replaced with a positive ceiling.
   Other global/scope checks may still block a request, so this is specifically
   a failure to preserve the caller's exhausted nested budget, not proof of an
   actual overspend. Preserve None versus zero and reject nonpositive explicit
   caps as control flow before request creation.
2. `advance(input_only=True)` originally intercepted only `request_ready`.
   With saved `mining-output.json` and accepted `semantic-review.json`, it could
   skip Mining requests and reach `_publish`; if all later outputs/reviews
   already existed it could reach `_seal(completed_passed)` without another
   request. This violates the spec's input-only/no-capability-success boundary.
   The concrete paths are statically reachable, not an executed whole-stage
   finding. Restrict input-only at entry to the first Mining input, refusing
   pending/answered/accepted-phase state, or make every later boundary read-only.

The writer acknowledged both and is adding scoped fixes/tests. This review
does not change the product, driver, tests or specs, and does not prepare the
fixed stage. A later final-source binding must distinguish the reviewed interim
driver from the final revision.

## Targeted final supplements and claim scope

`document-only-prompt-supplement.json` binds the later prompt revision that now
explicitly permits document refs established by an actual `read_span`. Two
independent legal controls verify the same matching document read can support
either its case-bound event citation or a direct document citation, with the
exact complete readable text and `case-002` window retained at S5. The old ten
controls and their original prompt hashes remain unchanged; they were not
silently reattributed to this later wording.

`driver-corrected-boundary-controls.json` verifies the writer's two concrete
fixes on stable driver/spec bytes during those controls. Zero explicit request
allowance now raises `StageBudgetStop` before native transport; None uses the
declared host cap and a positive explicit cap is preserved. Synthetic saved
phase markers for Mining output, publication, technical decision, Fast output
and terminal seed all cause input-only to reject before construction or seal.
For these pure entry-boundary checks, `verify` is deliberately bypassed and
`construct`/`_seal` are guarded sentinels: they establish the input-only guard,
not source freeze, role behavior, promotion, cache recovery or a complete stage.
All marker files live only inside this independent-review directory.

Writer changes were still occurring during the broader read-only review, so
only the specifically recorded citation run/supplement and corrected-boundary
control source sets claim within-run hash stability. A final all-file snapshot
is a read-time binding, not retroactive proof that interim driver/tests stayed
unchanged throughout the review. No gate/helper existence, passing synthetic
test, bool review receipt or pending request has been counted as full native
chain success.

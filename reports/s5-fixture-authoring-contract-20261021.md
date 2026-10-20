# S5 fixture authoring: producer contract and native validation

The strict SEC Company Facts consumer requires an explicit body issuer and,
for an opaque fixture company, matching document metadata CIK. Shipped positive
templates were repaired earlier, but the independent production tests-author
request still lacked both that requirement and the fixture array schema. A
shared helper alone did not reach this separate call: only the preceding spec
author and legacy candidate/Update contracts received it.

The owning spec now discloses the existing issuer and literal-source contracts.
The actual `_materialize_tests_module` request receives shared execution
semantics and the same existing tests-array schema. The argument view describes
existing content-string and optional metadata fields. Nonfinancial sources do
not acquire a universal metadata requirement. Update still copies stable tests
byte-for-byte; no old version is migrated or given a new efficacy conclusion.

The native deterministic fact parser also requires each used fact's canonical
JSON literal in the source, or a canonical whole body. That existing requirement
is now disclosed to the author; other source types need not be JSON. The parser,
literal/PIT gates, taxonomy, period, unit and numerical functions are unchanged.

## Independently exposed input-shape bypass

An independent complete-validator probe found that a valid financial JSON string
executed positive, but changing its content to the equivalent JSON object and
expecting unavailable also passed. `_execute_fixture` coerced the object with
`str(dict)`, creating non-JSON text which the fact parser skipped. Technical input
corruption therefore looked like a successful domain-unavailable measurement.
The [original probe](../runs/diagnostics/s5_fixture_authoring_20261021_v1/independent/content-shape-probe.json)
and exact pre-fix source are retained.

The existing content-string contract is now checked before RawInfoDocument
construction. Objects, arrays, booleans, numbers and null are rejected without
coercion or automatic serialization. Valid string bytes and existing legitimate
unavailable semantics remain unchanged. The author's new two-schema, two-value
24-subcase regression was red on the retained candidate and passes after repair.

The [final source review](../runs/diagnostics/s5_fixture_authoring_20261021_v1/independent/final-review.json)
passes 22 controls: original-object false acceptance versus new rejection,
independent legacy/typed positives, missing/conflicting/canonical issuer cases,
actual outgoing author payload, native staging/load of unchanged tests,
nonfinancial metadata absence and immutable Update fixtures. One review-harness
changed-path selector was initially too narrow; its failure and corrected native
invocation remain separate from product results. No model or real source is
used in these synthetic checks.

Root's first [66-test connected check](../runs/diagnostics/s5_fixture_authoring_20261021_v1/root-connected-tests.log)
has two failures in old Controller/Update positives. Their Company Facts bodies
declare the synthetic CIK, while their document producers omit metadata binding.
The broader check covers Slow entry paths absent from the earlier 158-test
numeric/runtime suite. The [old-source contrast](../runs/diagnostics/s5_fixture_authoring_20261021_v1/driver/two-old-source-failures-v2.json)
reproduces both failures using the exact saved HEAD engine/shared helper with
current dependencies. It is not a complete old-checkout test. Three explicit
metadata declarations repair only those named positive producers; body values,
dates, assertions and stable Update fixtures are unchanged. Root's
[final connected check](../runs/diagnostics/s5_fixture_authoring_20261021_v1/root-connected-final-tests.log)
passes 66 tests in 1.113 seconds, with all five forbidden-operation tripwires
zero. No full-engine/DualLoop test module or real cycle is executed.

## Next evidence boundary

The new bounded fixture-author diagnostic is module-only: frozen accepted spec,
null skill and synthetic facts, one fresh exact-inbox subagent answer, then the
unchanged native validator and an isolated candidate Registry. It has two
independently executable schema controls and no retries. Preparation, fresh
execution and final review are separate. Independent preflight found an
actual-row versus nonfact-literal-carrier oracle gap: unchanged ratio 0.25 could
pass while the supplied complete rows lived outside `facts`. The final private
oracle binds actual facts-array canonical rows and selected execution evidence,
including a separate execution of each schema's complete document. Same-ratio
alternative operands and dead carriers fail. Legal CIK representations remain
valid; the public sample requires one complete document per schema so no hidden
document-grouping rule is imposed on its author.

Root's [18 safety checks](../runs/diagnostics/s5_fixture_authoring_20261021_v1/stage-preflight/root-stage-safe-final-tests.log)
and [14 independent preflight controls](../runs/diagnostics/s5_fixture_authoring_20261021_v1/stage-preflight/independent/final-stage-review.json)
pass. Original unsafe script, accepted carrier counterexample and two
review-harness errors are retained. The [bounded native runner](../scripts/run_reviewed_fixture_author_stage.py)
permits one 4000-output request, at most 131072 logical reservation units and
zero correction requests. Network/real labels/persistent source stores/seed
installation are blocked. Scripted native pending/receipt/validator/staging/load
and completed restore prove wiring only. Under code checkpoint `c81c1986`, the
unique formal prepare exits 0 with manifest
`cadf061d99611e3dff7564f8357536a0d97b2f7f836a30643d0bf3f320b90f8e`.
The [actual freeze review](../runs/diagnostics/s5_fixture_authoring_20261021_v1/actual-freeze-review.json)
checks every bound code/source file, exact synthetic row/period/unit semantics,
four stage JSON files and absence of an exchange/inbox. This is preparation,
not fresh model acceptance.

This does not test Mining discovery, a new measurement implementation,
publication, effect, successor reuse or complete S5/MVP. The default LLM
cash-ratio retrieval gap and whole Fast/Slow feedback loop remain open. No
external LLM API, real-label read, public-source acquisition, real Registry
publication or completed-stage reentry is authorized by this local repair.

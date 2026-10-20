# Bounded owned-partial Reflect and Predictor stage

2026-10-20. The new single-case stage is implemented and independently reviewed.
At the initial prefreeze boundary no formal prepare or fresh role had run. It tests a known
historical accepted prior/batch through fresh Reflect, durable reread, native
final assembly and fresh Predictor/sink. It cannot establish a fresh F6 result,
whole F7/F9, a completed Fast round or engineering MVP convergence.

The [owning contract](../spec/scripts/run_reviewed_owned_partial_stage.md) fixes
one sample, at most6 independent role requests,512000 case reservation units,
131072 per request and one native typed correction. Each fresh role reads only
its exact inbox; the independent oracle, old49/50 replies, prediction and final
state do not enter requests. No GET, Signal apply, labels or old-run resume.
A valid first answer leaves typed mirror correction `not_exercised`.

Preparation review found two concrete adapter defects before dispatch. The first
used the already assembled historical BasicInfo as bootstrap input: the native
assembler then lost17 existing cards. Empty-BasicInfo temporary tests could not
detect that loss. The adapter now reads the frozen canonical bootstrap in the
old preflight; an anonymous wire journal is not a canonical replacement. Actual
native reassembly preserves all17 IDs, full text, availability and source-index
visibility/omission metadata. The historical prediction envelope supplies only
whitelisted computed metric cards; old prediction/state stay excluded.

The second defect passed the single-request cap as the entire native invocation
allowance, narrowing its correction budget. Independent native execution shows
92778+93709 reservation units, each below131072: the old candidate stopped after
one receipt; the repaired candidate accepts both within the remaining case
allowance. A192778-unit single request still rejects before receive with zero
inboxes/receipts. Oracle referenced bindings and exact source/seed authorities
are checked, and extra nested files cannot hide behind operational filenames.

Root's10 focused tests pass with label/source-store/network/fullprepare
tripwires0. The [independent preflight review](../runs/diagnostics/reviewed_owned_partial_preflight_20261020_v1/independent/independent-review.json)
binds current source, oracle, actual constructor and budget counterexamples;
its own private-API harness failures are retained separately from product
failures. Original9809788 candidate and its9 green tests remain preserved as
evidence of why the empty fixture missed the constructor boundary. No test or
scripted typed response is described as fresh model behavior. Actual behavior,
raw/correction fidelity and completed restore remain to be tested after freeze.

The first formal prepare under0b26a640 failed before creating its stage root or
plan: its source loader passed a JSON string path to a Path-only shared reader.
The source loader had been stubbed in the earlier tests, and the limited native
budget/constructor review did not cover that metadata entry. Original failure,
command,1.669s/exit1 and b417 source are retained; zero roles were dispatched.
The owning adapter now normalizes both serialized strings and Path objects at
one local read boundary. Independent exact-b417 probes reject at the plan path,
and after fixing only that call still reject at the review path, proving the
family rather than a single-line patch. The new full temporary source chain and
pretransport drift controls pass; root's12 safe tests pass with all tripwires0.
Root additionally reads the actual completed source metadata and verifies all
5979 returned bindings in2.868s without Store/model/label/network operations.
The [source-read review](../runs/diagnostics/reviewed_owned_partial_preflight_20261020_v1/independent/source-read-final-review.json)
confirms no other adapter AST changed. This repair does not erase the failed
prepare or prove fresh role behavior; the same sample, oracle and budget remain.

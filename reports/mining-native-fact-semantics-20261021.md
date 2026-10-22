# Mining fact projection and period semantics

The first frozen seven-control native probe completed on revision
`1a2e7f87a56561a3356af89a5a476a5a07d7683a`. It establishes an actual
producer/consumer failure, not Mining capability or an engineering MVP pass.
No LLM, network, Signal, LabelStore, source append or whole-loop execution ran.

## Frozen native observations

[Probe scope](../runs/diagnostics/mining_native_evidence_probe_20261021_v1/spec.md),
[actual observations](../runs/diagnostics/mining_native_evidence_probe_20261021_v1/execution/observations.json)
and [terminal result](../runs/diagnostics/mining_native_evidence_probe_20261021_v1/execution/result.json)
retain the first execution. Script SHA is `00c34ffab06a28c0f6dafa7e3d4e8367b6e06eae939d24cd001676a12a7614a3`;
plan SHA is `3e3416fd3f1fe830d1ece62ba9769e508c166f605ee4226c4a91e6d8c20f006e`.
All 4,135 frozen source/code bindings were byte-identical before and after;
forbidden-call counters were empty. The actual observations SHA is
`0472edbe90bc4b0a6876aedde9328ba0ea281efe3328c9c15db0fa814380c228`.
[Independent original-to-output review](../runs/diagnostics/mining_native_evidence_probe_20261021_v1/independent/actual-review.json)
confirmed all seven controls, source literals, decimal arithmetic and the
four-file terminal seal without calling a native helper again.

| Control | Actual result | Interpretation |
| --- | --- | --- |
| O1 actual reviewed source fetch | First of 56 eligible documents was the 2011-08-10 filing; 55 excluded by the one-document limit | Source existence does not establish recent or sufficient selection |
| O2 unchanged original 0671 | Native context retained 19 records, including both complete OCF operands; EvidenceFact count 0 | Actual `value`-only rows disappear at the adapter's `val` gate |
| L1 synthetic legacy `val` | Two facts, one half-year pair, ratio 1.200000 and difference 20.000000 | Existing legacy arithmetic path remains reachable |
| T1 small synthetic typed `value` | Two context records, zero facts | Reproduces the adapter failure without original-document size/selection ambiguity |
| R1 explicitly synthetic dual-key rows | Seven facts; USD pair was half-year 120 / quarter 50, yielding 2.400000; separate EUR pair 900 / 800 yielded 1.125000 | Index-based roles can violate the existing same-concept comparable-period contract; arithmetic itself is correct |
| P1 synthetic document PIT/tie | Both no-query and query-tie selected the older document; future document excluded separately | Limit exclusion and PIT exclusion remain distinct |
| P2 synthetic row PIT | Future-end and future-filed rows excluded; two valid rows remained in context, zero facts | Context PIT filtering works in this control; adapter still loses valid typed rows |

O2's context is partial with 91 omitted concepts. Its two retained OCF literals
are 9,506,313 for 2011-01-01 through 2011-06-30 and 4,342,261 for the same
half-year in 2010. This is direct original/context evidence, not a claim that
all source material was read. R1 deliberately contains both keys to expose a
separate branch; no real document was rewritten and no actual typed-source
wrong-pair execution is claimed. Cross-document overwriting was found in code,
but was not exercised by these seven controls.

## Error family and repair boundary

Previous Mining tool tests used nested `units.val`, one document, and exactly
two records per concept/unit. They bypassed the typed facts-array shape and
made array position coincide with current/prior chronology. The earlier typed
read repair covered the shared context producer, but not this separate Mining
consumer. That omission belongs to our producer-to-consumer verification.
Code inspection also found the legacy selector discards same-end alternatives
before Mining sees them. That producer seam belongs in the same repair; a
downstream field-name change alone cannot restore already omitted periods or
conflicts.

The next repair must carry typed `value` and legacy `val` from the actual
producer shape without altering source literals, derive roles from periods,
retain same-end duration alternatives/conflicts, and construct automatic pairs
only when the existing comparable-period rule and unique operands support
them. Controller summary/current relations and deterministic closure/replay
consumers must stop silently overwriting alternatives. Generic explicit
arithmetic keeps its existing two-finite-operands, same-case contract.

No default currency, QoQ/YoY definition, cross-document revision precedence or
conflict winner is introduced. The original failed probe remains sealed.
Repair tests and any later capability stage have separate outputs; they cannot
rewrite this first result. New direction/magnitude discovery, implementation,
admission, publication, successor use and the full dual loop remain open.

## Namespace provenance decision

A further synthetic control exposes information missing from the current
`EvidenceFact` shape: one legacy document can contain `namespace-a.Metric`
(2024 end, value 120) and `namespace-b.Metric` (2023 end, value 100). Its
projected leaf spans contain neither namespace. Both records are valid facts,
but pairing them as the same measurement is wrong. The current period-based
candidate can still create that pair. Document/hash isolation alone cannot
recover the lost namespace. Label guessing, a default namespace and a hidden
process-global lookup are unsuitable fixes.

The recommended concrete change is an optional `taxonomy: str = ""` field on
`EvidenceFact`, filled from the existing shared context for both supported
source shapes. Namespace participates in automatic pair/unique-basis checks.
New virtual graph views/ledger payloads carry that provenance; no original
document, historical artifact, business completion pointer or frozen reference
is rewritten. Old records without the field remain readable but an unknown
namespace cannot authorize an automatic cross-namespace assumption. Explicit
generic arithmetic retains its existing contract.

The alternative is to add an original-document namespace lookup to every
pair/selection consumer, with a bounded optional context argument and a
fail-closed facts-only path. It preserves the Fact fields but adds a second
provenance channel/interface and recovery obligations. Neither choice changes
the measurement, currency, duration, conflict or source-authority policies.
This shape/interface decision is pending; it is separate from the already
authorized value/period/consumer repair and must not be silently resolved.

## Local candidate verification

The subsequent local candidate repairs the shape-specific value reader, legacy
same-end preservation/PIT filtering, parsed-date ordering and identity,
period-based roles, document-local unambiguous pairing, current automatic
relation refresh, and the Controller/closure/replay unique-basis consumers.
Complete conflicting facts remain available. A sole valid quarter or currency
pair cannot silently establish a default when another current basis remains
unresolved. Explicit generic arithmetic, including USD/shares, remains legal.

The original 0671 now projects 19 facts from its 19 selected context records.
[Independent literal audit](../runs/diagnostics/mining_fact_semantics_repair_20261021_v1/independent/candidate-original19-literal-audit.json)
checks every value, whole span, concept, unit, period, case/document/hash and
availability binding. Source bytes remain unchanged. This is a direct helper
and consumer verification, not a new model request or Mining result.

- Root ran 93 associated tests and nine shared-producer integration tests;
  all passed with network and research LabelStore tripwires untriggered.
  The first integration run retained an old unit expectation that discarded a
  same-end 100/101 conflict. Its failure is preserved; the revised assertion
  requires all three exact period/value records while retaining PIT, offset
  and the original character bound.
- [Independent 21-control suite](../runs/diagnostics/mining_fact_semantics_repair_20261021_v1/independent/candidate-independent-review.json)
  passed in both original-shape and synthetic dual-key isolation modes. Old
  baselines retain 16 and 12 failures, respectively. Baseline module paths were
  a mix of repository and snapshot paths, with all five actual module hashes
  equal to the captured old revision; they were not all loaded from an isolated
  snapshot directory.
- Separate date controls exposed lexicographic ordering and raw-date basis
  identity mistakes in the first candidate. After correction, seven controls
  passed; the captured pre-correction candidate failed three. An intermediate
  supposed old-snapshot green run was contaminated by preloaded Python modules.
  Its output is preserved and excluded; the corrected comparison checks actual
  module files/hashes after clearing those module imports.

These are passing local subsets, not closure of the whole error family.
The legacy namespace false-pair counterexample remains real, with its
[candidate observation](../runs/diagnostics/mining_fact_semantics_repair_20261021_v1/root/namespace-before.json)
retained. H1's `cases_with_comparable_records` still counts records rather than
requiring the shared pair proof; that connection also remains open. No further
native Mining stage, new role, Signal implementation/publication, or successor
experiment is authorized by these local results. The pending namespace choice
must be implemented and verified before claiming this source-to-Mining gate
closed.

## H1 catalog follow-up

The H1 count repair was completed separately from the pending Fact taxonomy
decision. H1 already has the original context's taxonomy/concept/unit grouping,
so its source-metadata count does not need a new Fact field or a second
provenance channel. A private row-index selector now serves both automatic
relations and H1. It proves existence of at least one unambiguous latest-period
and nearest earlier comparable pair within that projected document group.
Multiple durations can contain a valid pair without establishing a default
concept-level measurement. The catalog still retains its original recurring
two-case filter, 12k projection, 24-concept limit, case denominator and ranking
algorithm. Controller modality admission is unchanged.

The outgoing H1 authoring prompt and coverage note no longer claim that every
listed concept already provides a pair, or that absent bounded catalog
membership proves no source exists. The payload/request construction was
tested locally; there was no fresh model response under that prompt.

- 205 associated checks passed with network and research LabelStore guards
  untriggered. The first run retained an obsolete phrase assertion; only that
  unit expectation changed to check the explicit count/uniqueness/omission
  obligations. The first failure remains in the diagnostic record.
- [Independent H1 controls](../runs/diagnostics/h1_comparable_manifest_20261021_v1/independent/candidate-independent-review.json)
  passed 12/12 using the same test bytes that produced three failures on
  revision `113d6a6a`. A separate independent review confirmed nine exact
  relation-output/ID equivalence controls and ten temporary H1 controls.
- [One actual native H1 observation](../runs/diagnostics/h1_comparable_manifest_20261021_v1/root/native/result.json)
  used the unchanged qualified 1,780-document view and the original eight
  label-free development case metadata records. It called the production
  method through a minimal receiver, with no Engine, role, FactGraph, source
  append, LabelStore, GET or old-stage entry. All 1,789 bound files were
  unchanged before and after.
- [Independent actual review](../runs/diagnostics/h1_comparable_manifest_20261021_v1/independent/actual-native-review.json)
  found the same 24 catalog keys, order and counts as the previously saved
  catalog; only the coverage explanation changed. There is **no observed
  coverage increase on this dev8 view**. The counterexamples establish the
  corrected rule; the real-data observation establishes the deterministic
  connection and preservation.

This supersedes only the H1 record-count pending item above. Legacy Fact
namespace ambiguity, model consumption, direction/magnitude discovery and
implementation/admission/successor reuse remain unresolved. The schema choice
has not been inferred from silence and no further Mining capability stage ran.


## Approved taxonomy implementation

The user explicitly selected the optional `EvidenceFact.taxonomy` field. The
implementation and bounded-reading progress are recorded in
[the current acceptance note](approved-reading-and-taxonomy-20261022.md). This
supersedes the pending schema choice above. Unknown legacy leaf namespaces
remain ineligible for automatic pairing; no Mining capability stage has yet
verified fresh model consumption of this additive field.

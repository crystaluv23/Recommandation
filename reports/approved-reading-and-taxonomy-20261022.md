# Approved reading and namespace implementation

The user explicitly approved bounded source reading and optional
`EvidenceFact.taxonomy`, and reaffirmed zero external LLM APIs. These decisions
clear the prior design blocker. The engineering MVP remains open.

The implementation follows the owning specs. Taxonomy now flows through native
typed/legacy projection, dataclass serialization, automatic basis selection and
fact-read results/ledger hashes. The original saved cross-namespace false pair
is rejected without changing fact refs or raw source text. Old typed literals
can establish namespace; old unknown legacy leaves cannot. Explicit generic
arithmetic retains its existing authority. The initial five-test red run also
contained a ledger-constructor harness error; it is not a product failure.
All 122 Mining/LabelStore controls passed with zero network attempts. Fresh
Mining model consumption of this additive field remains unverified.

The production reading path freezes the complete resolver-filtered eligible
pool, pages cards and structured coordinates, and isolates omitted-input
Signals. Actual read originals own evidence, resolution and fingerprints;
the full catalog signature invalidates skips when an unread candidate changes.
Read windows are closed before final extraction/correction; the correction cannot
expand into unread text or silently trim the view. Request reservations honor
remaining case budget and configured per-request cap. Catalog previews count
toward 32k but cannot be cited. Fingerprint-only skips identify old read versions
without manufacturing their old window coverage from unseen complete documents.

Seventeen focused controls passed, including exact native inbox/cache/receipt
reconstruction after each pending request. A final associated batch passed
**354 tests**, network attempts **0**; see
[the log](../runs/diagnostics/source_reading_20261022_v1/related-final.log).
A broader earlier Signal batch passed 355/356, with one migration fixture error.
That same test fails on an isolated copy of the pre-change HEAD source:
[baseline log](../runs/diagnostics/source_reading_20261022_v1/baseline-migration.log).
It contains an issuer-less financial fixture and fails capability audit before
the new reading path. It was not weakened or counted as passing. New test
harness errors (usage/timestamp constructor fields) and the initial incorrect
assumption that an invented projection id defeats unique read-literal mapping
were corrected in tests, without relaxing source validators.

## Fresh native synthetic evidence

The [v2 frozen probe](../runs/diagnostics/source_reading_20261022_v1/native-v2/contract.json)
uses one synthetic Signal and eleven synthetic eligible sources, no labels or
provider I/O. Its production `prepare_inputs` proves the answerable source is
outside the original ten selected documents. Its source-only oracle stays
outside all model requests. Three separate fresh subagents answered exact
initial read, next-read decision and final extraction requests. Raw answers,
receipts, cache, requests, accepted result and read trace remain durable.

[Acceptance](../runs/diagnostics/source_reading_20261022_v1/native-v2/acceptance.json):
first final result **1/1**, model corrections **0**, actual receipts **3**,
logical reservation **31,385**, external LLM API **0**. Internal model token
usage/cost is unknown; zero external cost is not zero internal cost.
The selected original, comparator sentence, positive value, final evidence and
actual read resolution agree with the source-only oracle.
[Reopen](../runs/diagnostics/source_reading_20261022_v1/native-restore.json)
retains all 25 files byte-for-byte and exactly three receipts. Pending boundaries
exercise operation reconstruction; this is not an OS-kill or whole-loop recovery.

The first preparation is retained under `native/` with **zero responses** and a
stop record. Root noticed before dispatch that lexical ranking put its answerable
document first, contradicting the intended rank-eleven premise. The replacement
v2 changes only synthetic distractor text and adds an actual producer preflight.
No earlier completed production stage was reentered, no old denominator changed,
and no historical Registry was republished.

## Remaining acceptance

The current typed/legacy structured reader still indexes its default latest and
nearest comparable periods. An addressed older source window can therefore be
unreadable even though its original rows exist. This is a newly identified F5
gap, not proof of absence. Before claiming F5, extend that addressing through
the shared reader while retaining PIT, full row literals, same-period conflicts,
units and atomic comparable groups; test an older necessary period outside the
default selection. Then freeze fresh actual-source controls and verify Reflect/
consumer meaning. This synthetic protocol pass does not close F5, source trust,
direction/magnitude Mining, admission/reuse or the complete Fast/Slow loop.


## Historical coordinate follow-up, first candidate

The shared reader now has an internal include-history index option; default
callers retain their original latest/comparable selection. Explicit typed and
legacy reads reach older source rows, retain same-period conflicts and nearest
comparable rows, and avoid claiming unread gaps between interleaved records.
Two controls fail against revision 1100b208 (both source-shape older reads return
empty; interleaved reading is falsely blocked), then pass on this candidate.
[356 associated checks](../runs/diagnostics/source_reading_20261022_v1/history-related-final.log)
pass, network attempts zero.

The [first fresh historical probe](../runs/diagnostics/source_reading_20261022_v1/history-native/acceptance.json)
is **0/1**, one fresh role / 13,398 logical reservation / zero external LLM APIs.
Its author selected two distinct non-overlapping 2022 and 2021 raw windows. The
tool expanded the first to include its comparable and then rejected the second
as overlapping. It disclosed no body and accepted no semantic result. The
original response and completed failure stay unchanged. This is a deterministic
interface false rejection: tests had only addressed one window at a time.
A source-preparation-only duplicate-body fixture error and an attempted resume
without a prepared contract are also retained; neither created a request.

Next distinguish explicit duplicate/overlapping requested coordinates from
automatically attached comparable rows within the same exchange. Merge only
those implicit expansions, count each literal once, keep explicit duplicates
and already-read windows rejected, then freeze a new fresh control. No F5 or
MVP closure is claimed.

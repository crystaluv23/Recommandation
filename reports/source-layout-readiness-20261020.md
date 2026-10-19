# Preparation source layout boundary

2026-10-20. Native preparation now classifies already loaded immutable documents
by `RawInfoDocument.source_type`, using the same market and narrative type sets.
It caches parsed documents per company. Source meaning no longer depends on the
grandparent directory name, which omitted the flat `documents/` layout of a
reviewed snapshot. Reviewed-loader bindings, exact unproven-source reviews,
cutoff checks, baseline/date alignment and original target counts remain.

The original [48-case preparation failure](../runs/diagnostics/reviewed_source_snapshot_20261019_v3/full_preflight/preparation_failure.json)
was generated from a view containing only two SEC documents. Its16Anchor
exclusions all say `pit_price_baseline_unavailable`; preparation stopped there
and did not assess the other32cases. That record is unchanged. It cannot prove
16issuers have no local prices.

A bounded read-only inventory found candidate global market documents, matching
adjusted=true provider caches and archive baseline dates for all16cases. Direct
native baseline calculation is available16/16. These are candidates, not newly
admitted sources: the other15issuers still lack independent historical identity
and post-cutoff adjustment-basis qualification. No replacement price download
or full research run was needed for this diagnosis. The16case/time groups are:
Mar31 MP/LTH; May30 ONDS/SFIX; Jul31 FTAI/NEM/WYNN/MS/MU;
Sep30 ENB/PRAX/SNDK/CIEN/BMBL/KGC/ATI, all2025 at00:00UTC.

The [actual qualified BMBL view](../runs/diagnostics/reviewed_market_snapshot_20261019_v4/input_manifest.json)
contains two SEC documents and one market document. Its native baseline is6.494,
doubling threshold12.988 and recent close6.3. The previous directory predicate
selected0market documents from that view. Real preparation now recognizes it
under legacy, neutral relocated and reviewed-flat layouts.

[Root captured five focused tests](../runs/diagnostics/source_layout_readiness_20261020_v1/root-focused-5.log)
pass. They run native prepare, the actual reviewed loader and baseline code,
with temporary approved/LabelStore stubs and one candidate anchor. The default
16target is preserved: positive classification leaves15missing; negative
controls leave16missing. This is not a full16-case or48-case acceptance.
Counterexamples cover wrong type in misleading directories, missing prices,
future availability, exact unproven-source exclusion, wrong baseline dates,
and an explicit two-SEC view refusing another oracle's candidate prices.
Root reviewed the two producer changes and unchanged qualification checks.

One earlier associated27-test invocation accidentally included an old test that
read the real LabelStore and attempted temporary readiness preparation. It was
rejected for insufficient sources; no research cycle, model, scoring or download
ran. This exceeded the requested label-free diagnostic scope and is explicitly
recorded in [the transcribed original result](../runs/diagnostics/source_layout_readiness_20261020_v1/related-27-transcribed.log).
It is not evidence of label-free execution or full-cohort success. Root's final
five-test raw log above uses only temporary label stubs. The preceding six-role
[latest measurement batch](reviewed-measurement-latest-stage-20261020.md) had
already completed with0label reads and is unchanged by these later tests.

The connection defect is locally repaired. Source qualification of the remaining
15issuers, full readiness, full Fast/Slow and engineering MVP remain open.
Next inspect the exact cached request/source proofs for those15, then use the
user-authorized read-only public evidence only where the original record lacks
historical identity or adjustment proof. Do not rerun the measurement controls
or substitute retrospective label prices for blind inputs.

# Bounded catalog working context — implementation verification

Owning spec changed before implementation. Successful native `inspect_catalog`
responses from all four scopes retain whole runtime responses/arguments and
ledger action/response/source-snapshot identities. The shared working page
selects8 responses/32000 UTF-8 JSON bytes, disclosing complete omitted/oversized
locators and required sizes. Repeats replace/reorder observations while charging
their original scope budget. No tool, reading allowance, external API, canonical
business record, source parser or model-authored semantic summary was added.

Evidence population snapshots preserve first-seen deduplicated immutable narrative
document order, case scopes and event order. Ordinary source reads and compute do
not invalidate page cursors. An actual additional-source fetch does; historical
read_windows remain historical and live read progress stays authoritative.
Signal original guards remain intact. Retained backlog items grant disposition
visibility only if their whole original/source hash still matches and the item
is still pending; omitted/oversized/already-staged rows grant none. The existing
current base hash and typed disposition validation remain authoritative.
Indexed memory originals larger than the working-page cap remain complete in
the existing canonical disclosures, with an explicit oversized working locator.

The adjacent compute surface derives actual computed relations solely from the
existing relation/fact graph and ledger, bounded12 whole entries/8000 bytes.
It retains arithmetic value, operand order and exact fact source bindings across
reads/catalogs. Automatic same-concept/co-occurrence relations are excluded.
Legacy relations lack original operand snapshots, so any later fetch
conservatively invalidates the working result. Invalidated rows retain the complete explicitly historical relation
(value/rule/ordered operand refs/case) and reason, preserving recomputation
locators without pairing old values with new fact units. Candidate citation readiness uses
the same pure helper for all computed refs (including omitted entries), rejects
invalidated ones before the sink, and permits ordinary charged recomputation.
Canonical relations, S5 evidence and prior ledger rows remain unchanged.

Final checks:18 new tests and63 existing associated tests pass (81 total);
four task-file hashes are stable, socket tripwire attempts0. Native
MiningAgentRoleModel/StructuredRoleClient capture includes complete catalog and
computed surfaces in exact wire cost, preserves identity projection and stops
before receive; a lower budget rejects before receive. Replay reconstructs the
same view/ledger/S5 units. No fresh production author or candidate was created.

The same five catalog regressions on the archived98147bc1 controller produce
four missing-surface errors and one missing backlog-visibility assertion. These
are evidence of the lost working context, not five new semantic failures.
Initial harness expected8 retained backlog pages, but the existing32KB byte cap
was reached at6; `focused-v1.log` and the exact initial test source remain. Only
that expectation was corrected to the item/byte limits. A preliminary snapshot
included read progress; parent review caught the cursor-refresh ambiguity before
freeze, and spec/prompt/code/tests now exclude it from population bindings.

Evidence: `check-bindings.json`, `associated-final.log`,
`old-98147-five-regressions.log`, reproducible `run_checks.py`. This establishes
offline working-context/typed-readiness connections only. Actual fresh source
planning, candidate generation, semantic admission and exact successor use remain
for the parent-controlled prospective evaluation. No stage/oracle/driver was
modified here, no commit was made, and implementation editing is now stopped.

After the81-test bound run, parent review required preserving the historical
rule/ordered-ref recomputation locator in invalidated compute rows. That final
projection/test-only adjustment was checked with the two affected compute tests and one native wire/cost test; see
`final-locator-bindings.json`. The parent owns the final combined-suite run.

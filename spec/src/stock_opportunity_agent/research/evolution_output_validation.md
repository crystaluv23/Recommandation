# Evolution Output Validation

## Purpose

Parse and validate structured role output, produce machine-readable issues,
and apply only explicitly allowed deterministic recovery transforms.

## Invariants

- Validation never infers write authority from diagnostic prose.
- Scoped correction preserves unrelated valid siblings byte-for-byte.
- A recovery transform must be generic to the declared schema; it must not
  encode provider-, company-, or case-specific exceptions.

Ordinary structured correction obligations use their explicit change paths and
permitted dependency paths even when a Controller enables exact compaction
scope. The compaction-specific scope resolver runs only for actual compaction
obligations; absence of compaction must never disable ordinary sibling
preservation. Scoped drift detection and projection use the latest invalid
output as their baseline: a later correction must not silently revert a repair
that exists only in that latest rejected output. When a Controller enables
exact compaction scope and ordinary issues do not declare their write scope
complete, an applied projection must pass full revalidation. A projected
correction that fails revalidation may extend its copied paths only with paths
named by structured revalidation issues raised against the projected object
itself; diagnostic prose grants no scope. A discovered compaction issue never
grants its container-root path: the extension applies only the exact removal
paths named by that issue's repair metadata, and a compaction issue without
removal metadata grants no extension at all. The model's complete corrected
object never stands in for the projection: remaining drift of any kind —
scalar, nested-leaf, indexed-item, or list membership, including same-length
membership rewrites — fails closed with actionable feedback.

When a safe projection exists but fails revalidation, the next correction
attempt must carry that projected object as its invalid output together with
the projected object's actual new validation diagnostics: safely repaired
fields are preserved, unrelated drift stays discarded, and the follow-up
correction request therefore differs from the previous correction request
instead of replaying it byte-for-byte into a cached identical response.
Retrying the original failed output and original obligations after a
discovered projection is a stall defect. When no safe projection exists, the
original invalid object and its original obligations are retained unchanged
for the retry.

When the correction budget is exhausted, the deterministic
evidence-grounding fallback may restore the exact prior literal named by a
uniquely anchored Basic literal identity obligation (replace-only authority
plus an exact prior literal in its repair context) and may remove rows whose
obligations carry explicit remove authority; restored literal paths are
reported as normalized paths. A literal restoration alone is still
progress: an obligation set with only identity restorations and no
authorized removals is repaired, after safely validating the restoration
index and the target row's type against the failed output. The remove-only
identity codes (novel Basic ref, ambiguous prior literal) evict their named
row only when their own obligation carries remove authority; a
replace-only or add-only obligation of those codes removes nothing. Every
fallback result is accepted only after revalidation through the production
parser. It still declines every obligation without
such a deterministic repair, so ambiguous literal substitution, invented
Basic refs, and any unanchored edit fail closed instead of being silently
accepted.

Field and member granularity is preserved at every path-expansion step. A
leaf path `root[i].field` authorizes only that field of its member; it never
authorizes rewriting sibling fields, replacing the whole member, inserting
new records, or removing the parent row. Whole-member deletion authority is
never inferred from the existence of an indexed leaf path or from whole-object
validity: it requires specific validator metadata — the owning issue's
`authorized_member_removals` repair context naming the exact member paths —
or an obligation that itself names the whole member `root[i]` while its
allowed_repairs permit `remove`. A supplied member-removal allowance mapping
without an entry for a collection root authorizes no removal in that
collection at all: a missing or empty allowance root is fail-closed, never
a default under which every covered slot becomes removable. A leaf `remove`
repair never becomes parent
removal without such an explicit whole-member target. Only an exact member
path `root[i]` authorizes whole-member replacement, and it authorizes
replacing that one member with exactly one returned row: deleting that
member additionally requires the slot's own explicit removal allowance, and
returning several rows where that one member stood — splitting it — is an
addition that requires an explicit bounded add budget. A compaction
obligation's `required_compaction_remove_paths` are exactly such explicit
per-member removal allowances. An unmentioned member must survive.
Surviving members must stay in order — unchanged except for their own
authorized leaf edits, where an authorized node permits its complete subtree
(an authorized same-length list-valued leaf replacement survives beside a
neighboring authorized member removal) — additions stay bounded by an
explicit add budget, never by member-slot count or the prior collection
size, and projection applies the same rule when copying. The raw drift
check, the projection membership fast path, and the content-anchored
reconciler enforce this one per-member operation-authority rule through a
single shared membership check, so a raw corrected object and any projected
correction obey identical operation permissions: every authorized
whole-member slot that lacks its own removal allowance must still be
represented by exactly one returned row, and every row beyond those
replacements needs add authority.
When a correction both repairs its authorized whole-member slots and drifts
the rest of the list (unauthorized removals or reordering), the corrected
list itself is never accepted; projection may instead reconcile
content-anchored against the failed output: each unauthorized failed member
that equals exactly one corrected row anchors it, unmentioned or reordered
members are restored from the failed output in original order, an unmatched
corrected row is taken as a replacement only when it attributes to exactly
one authorized slot whose position between anchors is unambiguous — a run
of returned rows shorter than the authorized slots between anchors is an
ambiguous partial mapping and is rejected, never assigned to the first slot
by assumption — and a
vanished authorized member still requires removal authority. Duplicate
content, an unattributable replacement, or an insertion beyond an explicit
add budget is ambiguous and fails closed with no projection. An append or insertion of new members is
authorized only explicitly: an obligation whose allowed_repairs permits `add`
grants a bounded append budget on the collection its paths name (one new
member per named missing literal, at least one); no leaf path implies that
permission. A compaction obligation's exact removal paths fully enumerate the
container they evict from, so the container-root issue path adds no
member-level authority. Any projected correction is fully revalidated before
acceptance.

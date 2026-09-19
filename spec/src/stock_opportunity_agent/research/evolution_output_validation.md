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

Field and member granularity is preserved at every path-expansion step. A
leaf path `root[i].field` authorizes only that field of its member; it never
authorizes rewriting sibling fields, replacing the whole member, inserting
new records, or removing the parent row. Whole-member deletion authority is
never inferred from the existence of an indexed leaf path or from whole-object
validity: it requires specific validator metadata — the owning issue's
`authorized_member_removals` repair context naming the exact member paths —
or an obligation that itself names the whole member `root[i]` while its
allowed_repairs permit `remove`. A leaf `remove` repair never becomes parent
removal without such an explicit whole-member target. Only an exact member
path `root[i]` authorizes whole-member replacement or a bounded split of that
member. An unmentioned member must survive.
Surviving members must stay in order — unchanged except for their own
authorized leaf edits, where an authorized node permits its complete subtree
(an authorized same-length list-valued leaf replacement survives beside a
neighboring authorized member removal) — additions stay bounded by the
authorized member slots plus the prior collection size, and projection
applies the same rule when copying. An append or insertion of new members is
authorized only explicitly: an obligation whose allowed_repairs permits `add`
grants a bounded append budget on the collection its paths name (one new
member per named missing literal, at least one); no leaf path implies that
permission. A compaction obligation's exact removal paths fully enumerate the
container they evict from, so the container-root issue path adds no
member-level authority. Any projected correction is fully revalidated before
acceptance.

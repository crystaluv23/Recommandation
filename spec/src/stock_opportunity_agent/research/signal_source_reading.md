# Bounded Signal source sessions

This module implements the source-session boundary approved in the
[F5 proposal](../../../../reports/llm-signal-bounded-source-reading-proposal-20261021.md).
It does not choose a measurement, change SignalResult, acquire sources or bypass
the existing evidence/identity/PIT validators.

The executor supplies a frozen eligible resolver pool. Catalog signatures bind
complete records, order, as-of, exact spec and skill; opaque source handles bind
complete individual records. Pages contain at most 20 cards, with 140-character
previews and at most 20 structured group coordinates per card. Additional source
pages or group pages consume a reading exchange. Catalog previews count toward
the 32,000-character ceiling, but cannot authorize final citations. Metadata and
bounded catalogs never prove absence. The local coordinate index requests all
valid historical rows from the shared reader; catalog entries page complete
namespace/concept/unit/period groups in breadth-first period order. Default
reader callers retain their latest/comparable behavior. Invalid/future rows and
index omissions remain partial; indexing alone does not mean model visibility.

One session accepts at most two exchanges, five windows per exchange and ten
distinct sources. An action is exactly reads, source-catalog cursor, fact-group
cursor, or finalize. Coordinates are strict integers in the card's declared raw
or normalized-readable system. Validate the entire read exchange before applying
it. Reject unknown/version-mismatched handles, overlap/repeated source groups and
any character overflow without disclosing a partial fact or sentence.

Structured reads expand each intersected period atomically to all conflicting
duration/value rows and each duration's nearest earlier comparable period in
the same namespace/concept/unit, including periods older than the default view.
Within one exchange, distinct non-overlapping requested windows can acquire the
same implicitly attached comparable row. Merge those complete identical units
before disclosure and character accounting; reject explicitly repeated or
overlapping requested windows and any unit read in an earlier exchange. Automatic
closure must not turn two legitimate current/prior requests into a false duplicate.
The tool never adds a later period to replace the addressed older period. Narrative reads
retain complete sentence units inside the addressed window and report a
continuation when a complete unit could not fit. Raw-offset lineage remains bound
to unchanged originals; existing literal/whole-word/boundary checks still apply.
An oversized group/sentence fails or returns explicit unread/continuation, never
a fabricated semantic conclusion.

The session records actions/results, actual read versions, prepared preview/body
character counts and closed state. Final/correction uses this closed projection;
no later read or automatic edge expansion is permitted. Coverage-only synthetic
views contain only read text/rows and no hidden original metadata; these are
never persisted as Raw Info or used as evidence authority. Original complete
source records alone establish final evidence lineage.

On a fingerprint-only no-op, original read versions can be identified but old
window coverage cannot be reconstructed from those fingerprints. The returned
resolution explicitly leaves coverage unconfirmed instead of deriving periods
or observations from unread full documents; the earlier result remains the
caller-owned retained result. Native exact request/cache replay, rather than a
fingerprint-only no-op, reconstructs complete session windows and coverage.

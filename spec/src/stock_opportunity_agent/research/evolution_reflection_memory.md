# Sourced Reflection Memory

## Purpose

Provide pure, bounded model views and reference resolution over immutable,
already anonymous retrospective reflection artifacts. The module never opens
files, calls models, or grants access to Raw Info or blind execution.

## Contract

- Original case, Plan and round reflections remain archived in full. Optional
  structured items contain one fact, hypothesis or action, a model-authored
  brief and detail, applicability conditions, limitations, supporting and
  counter references, and an explicit case/Plan scope. Runtime binds content
  hashes and item identifiers; a model cannot author those identities.
- References resolve only through the supplied in-memory catalog. Source
  identifiers bind their immutable content and structural location and ignore
  the rebased round number, so import and restart preserve identity. Repeated
  source references are not independent observations.
- Reflection roles receive a bounded catalog, prioritizing canonical per-case
  facts and original case/Plan units over redundant item-scope rows. The full
  local resolver remains available; omitted-count metadata never expands into
  an unbounded list of identifiers.
- A source-backed item is `sources_checked`, never automatically `verified`.
  Runtime-owned outcome facts may be verified; model confidence and citation
  presence are not truth. Explicit outcome claims must match canonical outcome
  records, and technical exclusions cannot support research attribution.
- Higher layers may select unchanged lower items or add source-backed items;
  a new item's declared scope must be covered by its source closure. Cited
  counterexamples remain attached. No hierarchy level is intrinsically true.
- Old artifacts load without rewriting. Their exact original strings become
  verbatim index entries marked `legacy_unreviewed`, with no invented LLM brief or retrospective
  conversion into verified facts.
- Brief views select complete entries within a UTF-8 byte budget and retain
  included/deferred references and counts. A byte-bounded read-by-reference
  returns exact approved original units, never arbitrary files or a silently
  truncated excerpt. Source existence and selected coverage do not establish
  semantic support or completeness; manifests report these separately.
- Every new case reflection retains a runtime-owned `source_identity`, computed
  by its role from the immutable anonymous context, prediction and feedback,
  plus a safe `source_snapshot` containing only that identity and deterministic
  feedback. Source hashes bind identity as well as facts: identical outcomes
  in distinct cases never collapse. Legacy identities bind the original full
  case unit and containing Plan scope. Identity rebasing does not change refs.
- Success/failure categories require typed binary or magnitude outcome claims
  covering their declared cases. These must agree with machine feedback;
  technical exclusions and non-applicable outcomes cannot support such claims.
  These checks constrain explicit factual assertions, not all semantic truth
  in authored prose. Confidence is never a correctness substitute.
- A paginated directory exposes bounded complete briefs for omitted entries;
  its cursor/counts remain visible when the complete deferred-ref list does not
  fit. A `level` filter (`case`, `plan`, `round`) lets the consumer discover
  case evidence without first paging through every higher-level summary.
  The initial view interleaves levels after explicitly selected entries.
  Brief, directory and source-read limits count the entire serialized UTF-8
  envelope, including metadata. Oversized original units fail instead of being
  truncated; oversized legacy briefs are identified explicitly by reference.
- Retrospective reads are allowed only for proposer, Plan/round reflection and
  authorized Slow memory consumers. Blind execution, prediction and unknown
  roles cannot access this index. Callers supply only role-approved, anonymous
  projections and retain the existing outgoing leakage scan.
- The authored-item boundary checks JSON shapes before membership tests or
  reference resolution. It raises typed local paths and explicit dependencies;
  `create_items` only prefixes those paths with the item coordinate. Diagnostic
  text never determines correction authority. Invalid counter references name
  only `counter_refs`, while supporting-source changes may require coupled scope
  and outcome-claim repair. Canonical outcome/category and scope/source conflicts
  name their actual repair dependencies. A malformed unclassified item falls
  back to its whole-item structural scope, never a guessed source field.

## Dependencies

Only canonical hashing and shared ValidationError. Core records may persist
items and build views; role adapters own prompts, authorized source construction,
model output validation, and outgoing identity masking.

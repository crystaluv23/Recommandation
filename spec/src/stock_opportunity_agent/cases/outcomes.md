# Cases Outcomes

## Status
Started

## Purpose

Own versioned retrospective outcome definitions, such as what counts as a
"surge winner", neutral control candidate, failure, or unlabeled case after a
forward window has matured.

This submodule exists because outcome definitions affect cold start, monthly
review, future case increments, and experiment comparisons. They must be
testable and replaceable without changing cold-start signal learning.

## External Interface

The submodule should expose:

- `OutcomeDefinition`: versioned thresholds, horizon, and minimum observation
  requirements.
- `OutcomeObservation`: retrospective price outcome measured after an as-of
  date.
- `CaseOutcomeLabel`: winner, control, failure, or unlabeled.
- helpers to measure price outcomes from data-layer price bars and label returns
  under a chosen definition.

Initial implementation uses a conservative close-to-close 180-day default:
winner if return is at least 80%, control if return is between -10% and +20%,
failure if return is at most -20%, and unlabeled otherwise or when too few
trading days are available.

For the initial production cold-start case selection, candidate winners should be
drawn from the most recent one-year historical window. This selection window is
separate from the forward outcome horizon used to label each candidate.

## Responsibilities

- Keep outcome labels outside point-in-time packets and blind research inputs.
- Make definition versions explicit in historical cases and run artifacts.
- Support future comparison of alternate definitions without changing case
  learning.
- Distinguish retrospective labels from live scanner signals.
- Leave richer definitions, such as max-forward-return, drawdown-adjusted surge,
  factor-conditioned labels, and sector-specific thresholds, to later confirmed
  implementations.

## Dependencies

- Consumes data-layer price bars for retrospective outcome measurement.
- Feeds `cases` learning, `review`, and future meta-learning experiments.
- Must not feed live scanner decisions directly because labels use future data.

## Invariants

- Outcome windows are explicitly after `as_of_date`.
- Outcome labels are retrospective review artifacts, never as-of research
  evidence.
- Changing thresholds, horizons, or labeling semantics requires a new definition
  id or version.

## Global Label Store (single door)

All retrospective ground truth consumed by any test, harness, evaluation, or
experiment comes from one canonical label store under
`runs/cold_start/data/outcome-label-store-v1/` (a `manifest.json` plus
`labels.jsonl`). The store key is `(company_id, as_of_date)`: a label without
an explicit prediction boundary does not exist. Records persist the raw
smoothed observation (baseline five-day mean, forward five-day-mean peak, their
dates, horizon end) plus the derived `realized_max_multiple`, `is_surge`, and
magnitude class, recomputed by the versioned six-month smoothed-multiple
calculator from the frozen full-market adjusted-price archive. The manifest
binds the archive identity and hash, the calculator identity, the label
contract, and the record count; loading verifies all of them.

Consumers derive `GroundTruth` through the `LabelStore` loader and never
hand-enter outcome constants — a hand-written realized multiple outside the
store and its tests is a repository-lint failure. A missing
`(company_id, as_of_date)` key fails closed as an explicit, reported exclusion
instead of defaulting or silently skipping. The store is an evaluation-path
artifact: prediction-time and blind-analysis paths must not import or read it.
Rebuilding against a new price vintage or a changed calculator writes a new
store version; runs record the store version they scored against, and
published historical metrics are not retroactively rewritten except through an
explicitly labeled recomputation. The six-month smoothed-multiple calculator
itself (`six_month_smoothed_multiple`) lives in this submodule so the
versioned definition and its only executable copy stay together; the evolution
dataset layer re-exports it.

## Testing

Tests should cover definition validation, return labeling boundaries, insufficient
future data, and later comparison of alternative definitions. Label-store tests
must additionally cover strict schema loading, manifest/record reconciliation,
duplicate-key rejection, fail-closed unknown keys, and derivation equivalence
with the shared calculator on synthetic bars.

### Loader admission is enforced at the evaluation door

LabelStore.load keeps its public interface and is fail-closed: manifest scalar
fields and LabelRecord fields retain their declared JSON types (no bool-as-number,
string-to-float/bool coercion or nonfinite values). Require the fixed calculator
identity and exact current SURGE_LABEL_CONTRACT, a readable regular archive file,
and its actual SHA256. Parse/hash the same archive stream before returning a
store. For every stored record, use its selected symbol history and the single
six_month_smoothed_multiple implementation to recompute all raw observations,
dates/horizon and derived fields; exact disagreement rejects the load. Selected
history rows require canonical ISO dates and finite positive numeric adjusted
closes, with optional symbol metadata matching their enclosing symbol; bad rows
must not silently disappear through calculator filtering. Duplicate dates or
ambiguous JSON keys reject. Unknown issuer keys continue to fail explicitly.

Both legacy full-market archives and derived archives use the existing
bars_by_symbol interface; no new archive schema, threshold, store version,
placeholder/verify=False exception, correction of historical bytes or alternative
truth doorway is introduced. Stream one symbol at a time with the existing JSON
reader moved into the data layer, avoiding a 903MB whole-file object graph and
cases→research imports. Recompute all6554 real records once to assess actual
compatibility and load cost before considering any process-local optimization.

This proves consistency with the frozen archive and calculator, not provider
price authenticity, issuer mapping beyond the stored key/symbol, adjustment
truth or forecast benefit. Any real record mismatch remains a qualification
failure; never rewrite the original store to make validation pass. Labels and
this loader remain evaluation-only and never enter prediction-time imports or
frozen blind requests.

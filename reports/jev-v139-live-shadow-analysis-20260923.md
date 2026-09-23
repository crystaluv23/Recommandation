# Jev V139 frozen historical shadow analysis

Date: 2026-09-23

> **Correction, 2026-09-23:** The direction-quality conclusion below is
> superseded by
> `reports/jev-v139-prompt-boundary-and-fn-audit-20260923.md`. The original Jev
> state forwarded an upstream `analysis_prompt` whose instructions conflicted
> with the historical LLM's fixed screening system contract. A direction-only
> probe preserving that state remained conservative (F1 0.500), while the
> corrected fixed-contract probe matched the historical LLM on all 21 binary
> choices (F1 0.800). The original run remains valid transport, routing, and
> magnitude diagnostic evidence; it is not a valid intrinsic Jev-versus-LLM
> direction comparison.

## Verdict

Jev is not accepted as a replacement for either the final opportunity classifier
or Signal selection. Its direction probability has promising ranking information,
so it is worth retaining as an additional experimental feedback signal for
reflection, disagreement review, and later calibration. Raw Jev confidence and
the current magnitude decision do not have demonstrated incremental value.

This is an in-sample historical shadow over one evolved Plan. It establishes
behavior and candidate uses; it does not establish out-of-sample generalization.

## Frozen experiment boundary

- Source: V139 `plan_r0001_c01` and its already persisted historical artifacts.
- Cases: 24 total, with 21 comparable final Predictor contexts and 3 technical
  exclusions whose final context was empty.
- Signal routing: 80 frozen rounds, containing 992 individual eligible-card
  choices.
- External execution: only Jev was called. Historical LLM predictions, contexts,
  Signal results, labels, and Plan state were not regenerated.
- Label boundary: direction/routing inputs and historical labels were stored in
  separately hashed bundles. Scoring opened labels only after all Jev responses
  were durable.
- Direction/routing manifest:
  `5bd82c478c86d63b482926da34d0481c55924030133932bb6ae645fcf8b7525a`.
- Conditional-magnitude manifest:
  `fdccc0f5d3ed40c3d2a81c4a7294c892d8fcdb5dea0f0c4e53d6d30b306f58af`.
- Resolved model/provider: `typesafe/jev-1.13-20260917` / TypeSafe.

The first combined direction-and-magnitude request design was found invalid:
five positive directions independently chose `not_applicable` for magnitude.
The production experimental adapter and shadow harness now ask direction first,
then ask only the three positive magnitude classes when direction is `likely` or
`possible`. The five positive cases were re-run through this conditional step.

## Execution

| Phase | Logical requests | Physical attempts | Known cost | Tokens |
|---|---:|---:|---:|---:|
| Clean direction + routing run | 101 | 101 | $0.037251270 | 980,811 |
| Conditional magnitude follow-up | 5 | 5 | $0.001600326 | 38,358 |
| Scored total | 106 | 106 | **$0.038851596** | **1,019,169** |

All 106 scored requests completed without retry. Mean latency was 1.38 seconds
for final direction and 1.40 seconds for routing; p90 was 2.10 and 2.04 seconds.

Two diagnostic attempts preceded the clean run. V1 exposed provider-rounded
probability sums, after which the adapter retained the raw response and normalized
only totals in `[0.95, 1.05]`. V2 stopped after an SSL EOF, after which bounded
per-request retries and conservative uncertain-send charging were frozen. V1 and
V2 are excluded from quality metrics.

## Final direction result

| Model/path | Accuracy | Precision | Recall | F1 | TP / FP / TN / FN |
|---|---:|---:|---:|---:|---:|
| Historical LLM | 0.762 | 0.769 | 0.833 | **0.800** | 10 / 3 / 6 / 2 |
| Jev raw choice | 0.667 | **1.000** | 0.417 | 0.588 | 5 / 0 / 9 / 7 |

Jev chose `possible` five times, `unlikely` ten times,
`insufficient_information` six times, and `likely` zero times. Every Jev-positive
case was already positive under the historical LLM, so Jev discovered no additional
candidate. Applied as a veto, it removed all three historical LLM false positives
but also removed five true positives.

Paired correctness was 11 both correct, 2 both wrong, 3 Jev-only correct, and 5
historical-LLM-only correct. The exact McNemar p-value was 0.727, and the paired
bootstrap 95% interval for Jev minus LLM F1 was `[-0.536, 0.069]`. The sample does
not support a replacement claim.

## Probability and confidence value

The positive probability ranked outcomes better than the raw four-class choice:

- ROC AUC: **0.838**, stratified bootstrap 95% interval `[0.630, 1.000]`.
- ROC AUC within the 13 historical LLM-positive cases: **0.900**.
- A label-tuned threshold of 0.29 would produce F1 0.857, precision 1.0, and
  recall 0.75 on these same cases. This is a post-hoc in-sample observation and
  is not an accepted threshold.

The probabilities were poorly calibrated as absolute event probabilities:

- Jev Brier score: **0.282**.
- Constant base-rate Brier score: **0.245**.
- Jev log loss: **2.120**.
- Mean probability assigned to the realized binary label: 0.586.

Confidence was not monotonic with correctness. High confidence contained 3/3
correct cases, medium confidence 2/5, and low confidence 9/13. The high-confidence
group consisted of confident negative decisions and is too small to establish a
general reliability rule.

Therefore the positive probability is the useful Jev output in this run, but as
a relative ranking or disagreement signal. Neither raw probability nor confidence
should enter fitness or be interpreted as calibrated market probability yet.

## Conditional magnitude result

All five Jev-positive cases were assigned `2-3x`, with confidence from 0.90 to
0.98. Their realized classes were one `2-3x`, three `3-10x`, and one `10x+`.

- Conditional accuracy among Jev-positive cases: **1/5 = 20%**.
- Accuracy across all 12 positive-truth cases, including direction misses:
  **1/12 = 8.3%**.
- Historical LLM magnitude accuracy on the same 12 cases: **5/12 = 41.7%**.
- Mean probability assigned to the true magnitude among the five conditional
  calls: 0.208.
- Multiclass Brier score among those five calls: 1.534.

The high reported confidence is contradicted by four larger-magnitude misses.
Current Jev magnitude output should remain diagnostic only.

## Signal selection result

The routing portfolio below was rescored on 2026-09-23 after correcting the
cap-rank score from the winning destination's probability to total inclusion
probability `1 - P(no_match)`. No Jev request was repeated.

| Measure | Result |
|---|---:|
| Exact ordered agreement with historical LLM | 1.25% |
| Exact set agreement | 6.25% |
| Mean set Jaccard | 0.420 |
| Micro recall of historical selected refs | 0.635 |
| Mean historical selection size | 3.113 |
| Mean Jev selection size after cap | 3.900 |
| Rounds reaching cap of four | 77 / 80 |
| Raw non-`no_match` card decisions | 878 / 992 = 88.5% |

Retention of previously selected Signal results was 69.6% for positive, 59.1%
for negative, 62.3% for neutral, and 59.3% for unavailable results. Jev selected
almost every eligible card and relied on the runtime cap to trim the result. This
is weak discrimination, not evidence of better routing.

Agreement is only a proxy because the Jev-only alternatives were not executed.
The shadow cannot determine whether different selected Signals would improve the
final prediction. Jev should not replace the selector. A later test could use its
per-card probabilities as a secondary rank score, with a predeclared sparsity
rule and executed counterfactual arms.

## Incremental-value decision

| Proposed role | Decision | Evidence |
|---|---|---|
| Sole final classifier | Reject | F1 0.588 vs 0.800; seven false negatives |
| Hard veto on LLM positives | Reject | Removes 3 false positives and 5 true positives |
| Extra direction probability for reflection/ranking | Continue experimentally | AUC 0.838 overall and 0.900 inside LLM positives, with wide uncertainty |
| Raw confidence as a feedback weight | Reject for now | Small and non-monotonic confidence buckets |
| Magnitude classifier | Reject for now | 1/5 conditional accuracy despite 0.90-0.98 confidence |
| Sole Signal selector | Reject | 88.5% raw applicability and 77/80 cap saturation |
| Secondary Signal rank score | Untested hypothesis | Requires executed alternatives and a frozen sparsity rule |

The next quality gate should use a genuinely held-out period or issuer cohort,
freeze any probability threshold before label reveal, report calibration as well
as rank discrimination, and execute the alternative Signal sets if routing value
is being claimed.

# Jev Signal-routing context-parity test

Date: 2026-09-23

## Conclusion

Giving Jev the historical LLM selector's complete initial user context did not
make its selected Signal portfolios converge to the LLM portfolios. It did make
Jev materially more selective and its card-level selection probabilities much
less overconfident.

The authoritative strict probe covered 80 historical routing rounds and 992
eligible-card decisions. Jev selected 263 cards after the existing total and
LLM-Signal caps, versus 249 for the historical LLM. Despite the similar volume,
only 131 of the 249 historical selections were retained. Micro precision,
recall, and F1 against the historical LLM were 49.8%, 52.6%, and 51.2%.

This rules out a direct selector replacement under the current per-card question
topology. It does not show that Jev's alternative portfolios are worse for final
research outcomes: the alternative Signals were not executed in this probe.

## Frozen boundary and execution

- Source shadow manifest:
  `5bd82c478c86d63b482926da34d0481c55924030133932bb6ae645fcf8b7525a`.
- Strict context-parity manifest:
  `2067bd234b01a713fa2e0ff77ffb312bbf7f86ec2be6cc8f2de490b15280e45d`.
- For all 80 rounds, the Jev `state` was literally object-equal to the accepted
  initial `signal_retrieval_cards` user payload, including
  `validation_feedback: null`.
- The single 3,927-character LLM system contract was frozen under SHA-256
  `20040d426eea8c6240c3a57b5684e188787f75775a3982e55859b0ac0fe6c214`.
  Jev has no chat system-role interface, so the selection-relevant rules were
  translated into every card question rather than sent as a byte-identical
  system message. These included smallest batch, non-redundancy, prior results,
  total and LLM caps, exact matches, hard applicability, and answer-need rules.
- Execution called only OpenRouter Jev. It did not call the historical LLM,
  execute Signals, rerun research roles, or read outcome labels.
- All 80 requests completed on the first physical attempt through provider
  `TypeSafe`, resolved model `typesafe/jev-1.13-20260917`.
- The strict run used 1,161,183 tokens and cost $0.044927736. An earlier
  non-authoritative diagnostic run cost $0.039571224 before the literal-null and
  full-rule checks were tightened. The initial sandbox-blocked attempt received
  no provider response and incurred no recorded cost.

## Portfolio comparison

All precision and recall values in this section treat historical LLM selection
as the reference behavior. They measure parity, not real-world correctness.

| Measure | Historical LLM | Old broad Jev | Strict context-parity Jev |
|---|---:|---:|---:|
| Selected cards | 249 | 312 | 263 |
| Mean cards per round | 3.113 | 3.900 | 3.288 |
| Rounds at cap four | — | 77 / 80 | 56 / 80 |
| Empty rounds | — | 1 / 80 | 7 / 80 |
| Exact set agreement | — | 6.25% | 2.50% |
| Mean set Jaccard | — | 0.420 | 0.357 |
| Micro precision | — | 0.506 | 0.498 |
| Micro recall | — | 0.635 | 0.526 |
| Micro F1 | — | 0.563 | 0.512 |

The stricter instructions cut raw non-`no_match` decisions from 878/992 (88.5%)
to 443/992 (44.7%). This corrected the obvious saturation problem and moved the
mean portfolio size close to the LLM's. It also removed many historical LLM
selections: 85 of the 118 post-cap misses were explicit Jev `no_match` choices;
the other 33 were displaced by the total or LLM-Signal cap.

The strict and broad Jev sets differed in 63 of 80 rounds. Therefore the supplied
selection contract materially affects Jev routing, but matching selection count
does not imply matching the joint portfolio.

## Probability and confidence diagnostics

At the individual-card level, strict Jev made 164 true-positive, 279
false-positive, 464 true-negative, and 85 false-negative include/exclude choices
relative to the LLM. Its selection score `1 - P(no_match)` had ROC AUC 0.686.
The Brier score improved from 0.504 in the old broad probe to 0.297, and log loss
improved from 3.977 to 0.902. Mean predicted selection probability fell from
0.820 to 0.572; the LLM reference prevalence was 0.251. The probability remains
too high in aggregate, but it now contains useful ranking information.

Jev `confidence` is concentration or decisiveness of its own answer distribution,
not a calibrated probability that the answer matches the LLM or the eventual
outcome. In this probe:

| Raw decision group | Count | Mean confidence |
|---|---:|---:|
| LLM selected, Jev selected | 164 | 0.689 |
| LLM rejected, Jev selected | 279 | 0.650 |
| LLM rejected, Jev `no_match` | 464 | 0.572 |
| LLM selected, Jev `no_match` | 85 | 0.487 |

Confidence was useful mainly for strong rejection. Among Jev `no_match`
decisions, agreement with the LLM was 80.6% at confidence below 0.60, 89.0% at
0.60-0.85, and 97.3% at 0.85 or above. Among Jev selections, parity precision
was 33.9%, 32.2%, and 46.5% in the same buckets. After applying the portfolio
caps, true-positive and false-positive selections had nearly identical mean
confidence, 0.704 versus 0.700, and identical mean selection probability, 0.846.

Confidence should therefore remain an extra reflection signal. It can flag a
high-confidence veto or a concentrated disagreement, but this panel does not
support using it as a fitness weight or treating it as correctness probability.

## Adapter defect found during scoring

The first scorer ranked excess candidates by the probability of the winning
routing label. That penalized a card whose selection probability was spread
across several needs. The correct score is total inclusion probability
`1 - P(no_match)`.

The scorer and runtime helper now use total inclusion probability, with an
offline regression test. No additional Jev call was needed. This correction
raised old broad Jev's LLM-relative F1 from 0.528 to 0.563 and strict Jev's from
0.477 to 0.512. The table above contains only corrected values.

## Why exact context did not produce LLM-like portfolios

The remaining gap is structural rather than a missing user-context field.

1. The historical LLM emits one joint structured portfolio. It can decide that
   one card makes another redundant while satisfying the cap in the same output.
2. Jev answers one closed routing choice per card. The shared state and repeated
   instructions expose all cards, but the adapter still combines independent
   card answers with a deterministic post-hoc cap.
3. The LLM output contract represents primary, confirmation, contradiction,
   scope, and residual need explicitly. Jev's current choices reduce those
   relationships to one need, `context_only`, or `no_match`.
4. A similar selection count can therefore contain a different mix. The strict
   probe over-selected some broadly reusable cards and rejected 85 cards the LLM
   had retained.

## Recommended use

Jev can participate in Signal selection, but the current result supports a
hybrid or sequential design rather than immediate ownership of the final set.

- Preserve `P(no_match)`, the full routing distribution, and confidence as
  additional feedback to the reflection LLM.
- Use high-confidence `no_match` as a review or veto signal, while logging LLM
  disagreements for evolution.
- For a true Jev selector, run a sequential slot experiment: choose the next
  card from all remaining cards, append the chosen card and its role to state,
  then ask again until the stop option or cap. That lets Jev observe actual prior
  selections and judge redundancy jointly over time.
- Measure outcome value only after executing frozen LLM and Jev Signal sets on
  the same cases. Portfolio agreement alone cannot determine which selector is
  better.

The production selector and fitness remain unchanged.

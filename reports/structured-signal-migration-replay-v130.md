# Structured Signal migration replay

- Source run: `runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v130`
- Frozen trajectories: 38
- Replayed Signal occurrences: 91
- Execution boundary: exact persisted document ids, content hashes, and prediction timestamps; labels were read only after execution for audit grouping.
- Registry mutation: none.

| Signal | Uses | State agreement | Availability old -> new | Mean confidence old -> new |
|---|---:|---:|---:|---:|
| `cash_to_current_liabilities_ratio` | 22 | 21/22 | 20 -> 20 | 0.818 -> 0.909 |
| `cash_burn_rate_elevated` | 34 | 31/34 | 34 -> 34 | 0.847 -> 1.000 |
| `liquidity_runway_months` | 35 | 28/35 | 35 -> 35 | 0.771 -> 1.000 |

- Transitions for `cash_to_current_liabilities_ratio`: `negative->negative`: 11, `negative->positive`: 1, `positive->positive`: 8, `unavailable->unavailable`: 2.
- Transitions for `cash_burn_rate_elevated`: `negative->negative`: 21, `negative->neutral`: 1, `neutral->negative`: 2, `neutral->neutral`: 1, `positive->positive`: 9.
- Transitions for `liquidity_runway_months`: `negative->negative`: 22, `neutral->negative`: 3, `neutral->neutral`: 3, `positive->negative`: 4, `positive->positive`: 3.

## Interpretation

- The cash/current-liabilities mismatch is a threshold-boundary correction: the deterministic ratio is 1.00856, which satisfies the declared `>= 1.0` positive rule.
- Cash-burn differences come from explicit numeric semantics: zero burn is negative evidence, while a positive but below-threshold burn is neutral.
- Most runway differences occur when operating cash flow is non-negative. The deterministic v2 treats that as negative evidence of a low-runway condition instead of converting cash generation into burn; one further neutral-to-negative transition is a computed 13.2918-month runway above the declared 12-month boundary.
- Deterministic confidence `1.0` means the declared formula was completely evaluated from validated inputs. It is execution confidence, not confidence that the Signal predicts a surge.

The label-group counts are post-execution diagnostics. They did not enter the deterministic functions or their input selection. This replay measures execution replacement on historical inputs; it does not rerun the final prediction LLM, so changed Signal states are downstream-impact candidates rather than causal prediction changes.

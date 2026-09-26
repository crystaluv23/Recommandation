# Structured Signal migration replay

- Source run: `runs/cold_start/evolution/information-evolution-dual-self-evolution-20260922-v139`
- Frozen trajectories: 48
- Replayed Signal occurrences: 100
- Execution boundary: exact persisted document ids, content hashes, and prediction timestamps; labels were read only after execution for audit grouping.
- Registry mutation: none.

| Signal | Uses | State agreement | Availability old -> new | Mean confidence old -> new |
|---|---:|---:|---:|---:|
| `cash_to_current_liabilities_ratio` | 27 | 25/27 | 24 -> 25 | 0.796 -> 0.926 |
| `cash_burn_rate_elevated` | 34 | 30/34 | 31 -> 34 | 0.790 -> 1.000 |
| `liquidity_runway_months` | 39 | 28/39 | 38 -> 39 | 0.759 -> 1.000 |

- Transitions for `cash_to_current_liabilities_ratio`: `negative->negative`: 13, `neutral->negative`: 1, `positive->positive`: 10, `unavailable->positive`: 1, `unavailable->unavailable`: 2.
- Transitions for `cash_burn_rate_elevated`: `negative->negative`: 20, `neutral->negative`: 1, `neutral->neutral`: 1, `positive->positive`: 9, `unavailable->negative`: 2, `unavailable->positive`: 1.
- Transitions for `liquidity_runway_months`: `negative->negative`: 20, `neutral->negative`: 5, `neutral->neutral`: 4, `positive->negative`: 5, `positive->positive`: 4, `unavailable->negative`: 1.

## Interpretation

- Cash/current-liabilities differences are resolved by matched typed facts and the declared ratio thresholds; complete inputs can turn an LLM abstention or neutral state into a measured state.
- Cash-burn differences come from explicit numeric semantics: zero burn is negative evidence, while a positive but below-threshold burn is neutral; complete matched facts can also recover an old LLM abstention.
- Runway differences primarily occur when operating cash flow is non-negative. The deterministic v2 treats that as negative evidence of a low-runway condition instead of converting cash generation into burn; finite runways use the declared six- and twelve-month boundaries.
- Deterministic confidence `1.0` means the declared formula was completely evaluated from validated inputs. It is execution confidence, not confidence that the Signal predicts a surge.

The label-group counts are post-execution diagnostics. They did not enter the deterministic functions or their input selection. This replay measures execution replacement on historical inputs; it does not rerun the final prediction LLM, so changed Signal states are downstream-impact candidates rather than causal prediction changes.

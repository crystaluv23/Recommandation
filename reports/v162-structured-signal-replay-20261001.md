# Structured Signal migration replay

- Source run: `runs/cold_start/minimal_rounds_v162_integrated`
- Frozen trajectories: 48
- Replayed Signal occurrences: 52
- Execution boundary: exact persisted document ids, content hashes, and prediction timestamps; labels were read only after execution for audit grouping.
- Registry mutation: none.

| Signal | Uses | State agreement | Availability old -> new | Mean confidence old -> new |
|---|---:|---:|---:|---:|
| `cash_to_current_liabilities_ratio` | 5 | 4/5 | 3 -> 4 | 0.540 -> 0.800 |
| `cash_burn_rate_elevated` | 15 | 11/15 | 12 -> 15 | 0.693 -> 1.000 |
| `liquidity_runway_months` | 32 | 19/32 | 26 -> 32 | 0.623 -> 1.000 |

- Transitions for `cash_to_current_liabilities_ratio`: `negative->negative`: 2, `positive->positive`: 1, `unavailable->negative`: 1, `unavailable->unavailable`: 1.
- Transitions for `cash_burn_rate_elevated`: `negative->negative`: 10, `negative->positive`: 1, `positive->positive`: 1, `unavailable->negative`: 1, `unavailable->positive`: 2.
- Transitions for `liquidity_runway_months`: `negative->negative`: 15, `neutral->negative`: 2, `neutral->neutral`: 3, `neutral->positive`: 2, `positive->negative`: 3, `positive->positive`: 1, `unavailable->negative`: 4, `unavailable->positive`: 2.

## Interpretation

- Cash/current-liabilities differences are resolved by matched typed facts and the declared ratio thresholds; complete inputs can turn an LLM abstention or neutral state into a measured state.
- Cash-burn differences come from explicit numeric semantics: zero burn is negative evidence, while a positive but below-threshold burn is neutral; complete matched facts can also recover an old LLM abstention.
- Runway differences primarily occur when operating cash flow is non-negative. The deterministic v2 treats that as negative evidence of a low-runway condition instead of converting cash generation into burn; finite runways use the declared six- and twelve-month boundaries.
- Deterministic confidence `1.0` means the declared formula was completely evaluated from validated inputs. It is execution confidence, not confidence that the Signal predicts a surge.

The label-group counts are post-execution diagnostics. They did not enter the deterministic functions or their input selection. This replay measures execution replacement on historical inputs; it does not rerun the final prediction LLM, so changed Signal states are downstream-impact candidates rather than causal prediction changes.

# V139 Signal modality classification

## Boundary

- Source run: `information-evolution-dual-self-evolution-20260922-v139`
- Source Registry: version `7`, hash `8df0bb48b93349044ff2442b3f589d05a22cb437cadf0c495257deba52e6077c`
- Successor Registry: version `8`, hash `719bd0520c673005083e4f265ec8cfab13467897c748fa5d37e285cedb234785`
- Plan hash: `e80fb5e9683db688355a23136d7591973b0d33689c1e517199e4ca46110f505f`
- Historical mutation: none. The successor is materialized at
  `runs/cold_start/evolution/signal-registry-successors/v139-modality-v1/signals`.

The plan covers all 18 current stable refs exactly once. Registry version `8`
contains 12 structured Signals and 6 narrative Signals. Every current spec has
an explicit modality and the full capability audit passes with 18 enabled and
zero disabled refs.

## Classification

| Source ref | Successor ref | Modality | Executor | Change |
|---|---|---|---|---|
| `cash_burn_rate_elevated:v1` | `cash_burn_rate_elevated:v2` | structured | deterministic | Correct numeric formula previously stored as LLM |
| `cash_reserves:v1` | `cash_reserves:v2` | structured | deterministic | Backfill identity |
| `cash_to_current_liabilities_ratio:v1` | `cash_to_current_liabilities_ratio:v2` | structured | deterministic | Correct numeric formula previously stored as LLM |
| `gross_margin_change:v2` | `gross_margin_change:v3` | structured | deterministic | Backfill identity |
| `liquidity_runway_months:v1` | `liquidity_runway_months:v2` | structured | deterministic | Correct numeric formula previously stored as LLM |
| `max_drawdown_1y:v2` | `max_drawdown_1y:v3` | structured | deterministic | Backfill identity |
| `negative_word_count:v1` | `negative_word_count:v2` | structured | deterministic | Backfill identity |
| `net_share_retirement_yoy:v1` | `net_share_retirement_yoy:v2` | structured | deterministic | Backfill identity |
| `operating_cash_flow_margin:v1` | `operating_cash_flow_margin:v2` | structured | deterministic | Backfill identity |
| `price_momentum_126d:v1` | `price_momentum_126d:v2` | structured | deterministic | Backfill identity |
| `revenue_acceleration:v1` | `revenue_acceleration:v2` | structured | deterministic | Backfill identity |
| `revenue_growth_yoy:v1` | `revenue_growth_yoy:v2` | structured | deterministic | Backfill identity |
| `commercialization_status:v1` | `commercialization_status:v2` | narrative | LLM | Backfill identity |
| `customer_concentration:v1` | `customer_concentration:v2` | narrative | LLM | Backfill identity |
| `financing_listing_action:v2` | `financing_listing_action:v3` | narrative | LLM | Backfill identity |
| `guidance_acceleration:v1` | `guidance_acceleration:v2` | narrative | LLM | Backfill identity |
| `order_confirmation_disclosed:v1` | `order_confirmation_disclosed:v2` | narrative | LLM | Backfill identity |
| `order_quality:v1` | `order_quality:v2` | narrative | LLM | Backfill identity |

`negative_word_count` is structured even though its input is text: configured
term counting fully determines its state. `order_confirmation_disclosed` and
`customer_concentration` remain narrative even though they may use amounts or
percentages: deciding whether an event is binding, material, attributable, or
diversified still requires semantic interpretation.

## Replay and validation

The three executor corrections were replayed on V139's frozen inputs before the
successor was accepted. Across 48 trajectories and 100 historical uses:

| Signal | Uses | State agreement | Availability old to new |
|---|---:|---:|---:|
| `cash_to_current_liabilities_ratio` | 27 | 25/27 | 24 to 25 |
| `cash_burn_rate_elevated` | 34 | 30/34 | 31 to 34 |
| `liquidity_runway_months` | 39 | 28/39 | 38 to 39 |

The disagreements are semantic corrections from typed formulas: matched ratio
thresholds, zero versus below-threshold burn, recovery of complete numeric input
that the LLM had abstained on, and non-negative operating cash flow treated as
negative evidence of low runway. Labels were read only after execution for
diagnostics. The detailed rows are in
[`structured-signal-migration-replay-v139.md`](structured-signal-migration-replay-v139.md).

The successor also runs source-backed deterministic fixtures for every numeric
state boundary, retains the existing LLM skills and fixtures for narrative
Signals, and passes the complete Registry capability audit.

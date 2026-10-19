# Runtime Compute Tools

## Contract

Closed, bounded metrics compute price-shape, return-between and distance-to-anchor
cards from point-in-time adjusted closes. Numeric values and literal endpoint
references are runtime-owned control data, never model-authored evidence.
The existing computed-metric-card-v1 schema and formulas remain unchanged.
Readable summaries retain supplied literal first/last dates beside the values;
trading-session counts must not be relabeled as calendar-month horizons.
Controller retains typed cards for validation while exposing this readable view.
Final Predictor and compact Posthoc retain the same original typed cards.

Daily observation eligibility uses `row_date < UTC_day(as_of)`. Equivalent
aware instants retain identical values, literal refs and trading windows; the
original `as_of` spelling is preserved on the card. Adjacent UTC days may
legitimately select different rows. Trading-count formulas and fiscal periods
are unchanged.

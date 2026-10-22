# Categorical state versus numeric sign

The completed fresh consumer has a bounded F9 factual-consistency failure. Its
Predictor says that a positive categorical state denotes a positive months
measurement. The supplied scalar is positive, but this does not define the
categorical state. Keep the original answer and the one-case failure; do not
correct/reenter that completed stage.

The exact v3 spec freezes positive_runway_max_months=6 and
negative_runway_min_months=12. The deterministic producer's documented and
implemented branches classify finite runway <=6 as positive, >=12 as negative,
and the open interval as neutral. Nonnegative operating cash flow is a separate
negative/unbounded branch. These labels describe the measured condition; they
are not stock-direction forecasts. No measurement definition is being changed.

The actual Reflect and Predictor wires preserve the full numeric measurement,
period, operands, categorical_state and numeric_sign independently, with an
explicit instruction to distinguish those last two. They do not carry the
exact predicate/threshold mapping. The final response nevertheless invents a
categorical interpretation from the number's sign. This is both an actual model
noncompliance with the distinction and a producer-to-consumer information gap;
the missing mapping does not excuse the claim or imply a need to require the
Predictor to recite thresholds.

Earlier tests checked that the two distinct fields and the caution existed.
They did not test fresh consumer semantics or prove that a consumer received
the exact classification condition. A positive numeric value can have any of
positive/neutral/negative categorical labels depending on the frozen predicate.
Schema/receipt/cache success cannot detect a prose redefinition of that label.

Next repair must address the general classification family: bind any supplied
state explanation to the exact version and authoritative producer contract,
carry it through model views/Reflect/final context/Predictor/persistence, and
leave unknown meanings opaque rather than guessing from sign or stock direction.
Use same-sign/different-state, risk-positive, negative-number/positive-state,
nonnegative-cash-flow unbounded and missing-input unavailable variants, and a missing-contract
counterexample. Do not handwrite a new measurement, infer generic semantics
from parameter spelling, force a prediction direction, or weaken whole-word,
PIT or typed repair permissions. Run a new declared bounded acceptance only
after its own pre-answer inputs/oracle/call budget are frozen; no full successor.

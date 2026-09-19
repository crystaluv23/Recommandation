# Interim independent semantic probes
Current patch fails genuine runtime lookup rejection: `_runtime_evaluation_input_requested` returns False for all of:
- What is the value of the baseline price?
- Please obtain the baseline date and price.
- Can we look up the baseline price?

It correctly returns True for `Using the supplied baseline, retrieve the current adjusted close price.` and `What is the exact baseline date and price for the six-month outcome?`, and False for an issuer-guidance question relative to supplied baseline.

Root concern: `_anchor_occurrence_requested` treats any unrecognized governor/content token as evidence of a different topic, thus unknown wording becomes blanket permission. `of`, `obtain`, `up` are concrete ordinary failures; merely adding these words leaves same fail-open mechanism. Prefer conservative recognition of anchor-as-reference constructs with request clauses independently checked; unknown intent should retain prior rejection unless a clear reference-use exception is established. Avoid building an ever-growing natural language parser. Preserve all existing negatives and actual V118 valid positive, mixed/multiple-clause queries.

This is an interim review while writer active, not final result. Round11 command restrictions arose because Codex omitted exact allowed commands from initial brief (now appended); source and tests unverified until real execution.

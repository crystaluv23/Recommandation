# Independent review: two remaining concrete failures
Current code rejects all five round11 reviewer negatives, passes actual tests886/lint. However `_runtime_evaluation_input_requested` incorrectly returns False for:
1. `Please provide me with the baseline date and price.`
2. `Using the supplied baseline price, what is the baseline price?`

It correctly returns True for `Using the supplied baseline price, what is the current adjusted close price?` and False for `What did issuer guidance disclose by 2025-03-31 relative to the supplied baseline price?`.

Mechanism1: standalone with in reference-preposition set is not sufficient evidence of reference use; it introduces requested object in provide/supply-with construction. Require actual comparison/reference phrase, e.g. compared with, not any with. Check same generic issue for other ambiguous reference prepositions without adding unlimited verb lists.
Mechanism2: proximity regex can span multiple anchors; word_pattern.search only nominates first occurrence, so a reference mention can hide later direct lookup of same anchor. Inspect all occurrences/overlapping relations and clause boundaries; do not stop at first nominated word. Preserve all positives and mixed clauses and no guard-bypass on repeated same anchor.

Need actual paired regressions, full tests/lint, raw V118 replay. Current semantic patch not accepted yet.

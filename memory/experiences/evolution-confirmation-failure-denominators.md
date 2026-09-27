# Evolution Confirmation Failure Denominators

visit_times: 6

## Trigger

Read this before computing or changing self-evolution confirmation metrics when
some frozen cases are missing, technically failed, abstained, or invalid.

## Lesson

Keeping a failure in a separate count is insufficient if the primary quality
metric is then recomputed only over successful rows. That can preserve a perfect
Binary F1 after the system fails on known positive cases and can make a fragile
candidate look better as failures increase.

For a frozen labeled cohort:

- retain every received failure row and every missing key;
- count a received technical failure on a known positive case as a false
  negative in Binary F1;
- report a technical failure on a known negative case separately and never call
  it a true negative;
- keep an explicit failure-rate gate because positive-class F1 does not penalize
  negative-case abstention; and
- make missing frozen rows `incomplete` rather than silently shrinking the
  cohort or substituting new cases.

The same denominator discipline applies to version promotion: a candidate that
reduces wrong decisions only by abstaining more can be relatively better than
the stable version while still having no correct decisive evidence. Apply the
absolute directional-quality floor before relative update improvement so a
uniformly wrong candidate cannot enter the stable Registry.

The acceptable failure rate and quality degradation remain protocol decisions.
Tests may use explicit fixture thresholds to exercise the mechanism, but those
numbers are not production defaults or evidence of real-provider reliability.

## Evidence

The T6 distribution test injected 0%, 10%, distributed 20%, and issuer-clustered
20% failures. Before the correction, two failed positive cases were excluded
from the confusion matrix and the candidate retained Binary F1 1.0. After the
correction, they are false negatives, while failures on negative cases remain
visible through failure and coverage metrics without becoming correct outcomes.

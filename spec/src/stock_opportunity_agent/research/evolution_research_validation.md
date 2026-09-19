# Evolution Research Validation

## Purpose

Validate point-in-time research state, evidence references, Signal results,
reflection transitions, and Predictor inputs after generic JSON parsing.

## Invariants

- Evidence must resolve to local immutable source spans.
- Outcome and target-identity leakage checks remain fail closed.
- State transitions preserve stable ids and cumulative research history.
- Temporal intent checks normalize underscore-separated words before matching
  cutoff clauses. Machine-style and prose spellings have the same meaning;
  this does not change persisted questions, source dates, or evidence validation.
- A partial-answer residual must retain the temporal scope of the need it
  narrows. When a persisted routing residual dropped the parent need's cutoff,
  the exact required residual representation restores the inherited as-of
  clause onto the residual instead of retaining the already answered parent
  need. Transition contracts, selection intents, need cutoff restoration, and
  transition validation derive that representation through one shared rule so
  the exact string H_reflect is told to write is always acceptable to both the
  transition and temporal guards.
- A legacy partial-answer residual that no bounded restatement can represent
  under the actual runtime prediction boundary (for example realized facts
  after the cutoff) is invalid routing state, not a removable obligation. The
  need-transition contract builder fails closed for it before any prompt
  exists, and transition validation never authorizes deleting the unresolved
  need: removal must be restored exactly, and no cutoff is fabricated for
  realized future facts.
- A need correction never carries a blanket dependency on unrelated state. A
  visible-answer or need-transition issue names only its own need path; it
  grants no authority over `current_beliefs` or any other collection. Belief
  edits during a correction must be authorized independently — by an actual
  linked-assertion dependency (same exact claim text) or an actual compaction
  obligation with exact removal scope — so a valid unrelated belief survives
  a need correction byte-for-byte.

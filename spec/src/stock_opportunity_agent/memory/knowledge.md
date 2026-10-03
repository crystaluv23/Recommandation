# Knowledge use summaries

Own the shared deterministic vocabulary for Experience and Signal brief cards.
This module depends only on core validation and artifact hashing, not evolution
engines, model providers or the Signal Registry.

## Brief contract

Each card exposes `usage_context` with `when_to_use`, `failure_conditions`, and
`related_refs`, plus a runtime-derived `performance` summary. Conditions describe
economic/research applicability and conditions weakening or reversing the
interpretation, not merely missing extraction inputs. Unknown boundaries remain
explicitly unknown. The prose is sourced, observational research knowledge;
neither the index nor usage statistics verifies its causal explanation.

Experience uses its existing scope conditions and limitations, with optional
exact-version `related_signal_refs`. Signal uses an optional `usage_context`
inside its versioned parameters; related refs point to Experience items. Shared
validation bounds prose and refs; summaries preserve immutable originals.

## Learning identity

Only explicit adoption/valid execution receives use credit. Visibility, storage,
related-index membership and model confidence are not adoption. Runtime owns
outcome evaluation. Repeated Plan evaluations of the same issuer/time count as
one independent case, with repeated predictions retained as observations.
Technical failures remain visible and cannot receive successful-research credit.
Unknown/no observations produce null rates rather than invented zero performance.

Profiles are derivatives of committed, source-bound records. Exact replay and
restore are idempotent; uncommitted artifacts cannot enlarge learning authority.
Read-only history export and card construction reconstruct missing derivatives
in memory without writing into their source workspace. Only explicit publication
after a local commit repairs derivative files and publishes the profile snapshot.
Old artifacts lacking adoption metadata have unknown use, not inferred success
or an invented unused control. Current-case outcomes never enter blind research.

The common observed-use metric is `correct_rate`: average binary prediction
correctness after explicit adoption/valid Signal execution. Compute a mean per
issuer/prediction-time case first, then average cases equally. Distinct repeated
predictions remain observations, not independent cases. Positive/negative-class
correct rates and case-weighted TP/FP/TN/FN stay visible to expose class imbalance.
Technical exclusions and unavailable Signal measurements receive separate counts
and no research success credit; they do not change formal Plan score denominators.
Conflicting states/coverage for one exact Signal version and physical case/input
remain disputed observations and cannot receive successful-use credit.
This is selected-use association, never causal attribution or admission authority.
Experience credit follows explicit Plan adoption across that Plan's evaluated
cases; it does not assert that every case-specific action was executed. Signal
credit follows valid measurement execution, not evidence of marginal contribution.

`KnowledgeUseStore` stores one rebuildable, source-record-bound observation file
per committed Plan. Reading verifies local state/checkpoint/record hashes, plus
explicit hash-bound history imports; extra files and future round numbers grant
no authority. An atomic profile snapshot is an audit derivative, not a new
commit pointer. Profiles are built over the complete authorized history rather
than only the bounded Experience FIFO. Source identities remain local; model
cards contain aggregate numbers only.
Slow-only construction restores these profiles too. Its search fingerprint binds
the profile snapshot so a resumed search cannot silently change feedback inputs.

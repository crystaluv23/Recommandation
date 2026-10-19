# Executed Answer Scope Stage Diagnostic

## Purpose and boundary

Run at most two saved Bumble Reflect inputs from completed v182 through the
current production `LLMResearchController.reflect` and `StructuredRoleClient`.
This is a separately authorized stage diagnostic, not a Fast/Slow successor,
prediction, cohort evaluation or resumed goal. It does not read labels for the
model, change v182, query/mutate the oracle store, fetch sources or invoke a Predictor.
Reading the audit-bound source files to verify their hashes does not admit their PIT.
The existing unresolved source-version and transcript policies remain unresolved.

## Preparation and execution

`preview --root NEW_DIRECTORY` reads the original report bindings, persisted
trajectories, committed Plans, completed attempt ledger, original requests and
response caches. It binds their exact file hashes and selects the two original
prior states, selections and Signal batches. Request control context is restored
from the saved actual request, without treating anonymous tokens as canonical
source identity. No temporary `/tmp` audit file is an authoritative input.

Preview freezes a stage-only contract, input bundle, source/code file hashes,
registered model identity and conservative accounting rates. It calls the real
controller/client with external execution disabled and an explicitly empty
environment, persisting exact initial requests until `ExternalRequestPending`.
It does not invoke an environment loader, inspect credential presence or access
the network. A preview directory must be new and outside every existing run.

`execute --root DIRECTORY --acknowledge-manifest HASH` first verifies the frozen
manifest, input bundle, original files and current code hashes. Only then may it
use an existing environment loader and enable the registered production client.
The acknowledgement identifies the reviewed diagnostic; it is not a new approval
flow or permission to resume an old goal. Changed code requires a new preview;
the old preview is retained. An execution marker prevents repeated execution,
including after failure or completion; there is no automatic resume/retry.

The script uses a stage-specific immutable contract exposing the hash and limits
required by the production transport. It must not fabricate a complete cohort
`EvolutionRunContract`. The ordinary production ledger owns physical-attempt and
cost admission, request persistence, raw responses, native corrections and exact
response caching. Its hard ceilings are eight physical attempts and $0.25 total.
Each sample starts with its original first Reflect context. If its new decision is
continue, the actual terminal-closure Reflect uses empty selections, the same full
batch, and the original terminal request's must_finalize/termination_trigger.
Each invocation permits one native correction (ordinary or patch-mechanics, sharing
one allowance), so at most four semantic invocations and eight physical attempts.
Preview also builds closure estimates from the canonical original initial state;
these are estimates only, never substituted for the newly produced runtime state.
No document channel, browsing, computation exchange, proposal,
new Signal extraction or provider retry is added. These are ceilings, not usage
targets, and may not be automatically increased. Cost estimates use the existing
registered conservative rates, not a current provider quote or exact invoice.

## Acceptance and persisted consumers

Save each new ResearchState, AgentStep metadata, usage and request hashes separately
for initial and conditional closure stages, then reload these saved bytes. Require the new `need_dispositions`
metadata to bind the exact prior-state hash and selected need occurrences.
Assemble a clearly labelled `stageassembly` using the production state-delta,
final-context, compact-posthoc and critic-trajectory helpers. Keep both deltas in
the same original round order; each metadata hash binds its own prior state.
The critic is constructed by replacing the original trajectory's state/deltas/
context; its old prediction is explicitly historical, not a new model result.
Save and reread those consumer payloads;
check that the target unanswered Q3 need remains and its disposition survives.
This is actual local consumer construction, not a real prediction or posthoc
model execution. The old wrong state remains only comparative evidence.

Passing requires both original target needs not be incorrectly resolved, all
untargeted prior need occurrence counts remain represented, metadata matches the saved state, and
the production consumer projections preserve the disposition. Valid citations or
the model's declared disposition do not independently establish economic truth;
the original Q2-only versus Q3-request evidence supplies the semantic check.
Any rejected sample or missing consumer metadata leaves stage acceptance failed.
All failed attempts remain in the ledger and diagnostic denominator. A failed
sample does not authorize repairs to live input/code or another execution.

Computed cards are checked against the original visible readable cards before use.
The production setter is used; persisted dictionary sorting may reorder semicolon
clauses, so exact title and clause multiplicity must match before restoring the
original readable ordering. Any card, value, or clause mismatch fails preparation.
The original tool catalog is hash-bound but absent from this diagnostic; this
does not validate the full original tool-enabled workflow or every branch.

## Tests

Use isolated directories and explicit synthetic original artifacts to test
immutable preparation, tamper refusal, execute-once behavior, restricted stage
calls, and persisted consumer checks. Preview tests use production request
construction and prove no environment-loader/network invocation. Do not call a
model from tests or replace the decisive controller/transport boundary with a
scripted successful research answer.

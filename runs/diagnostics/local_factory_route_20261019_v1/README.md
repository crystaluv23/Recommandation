# Local production factory route: original failure

This independent diagnostic called the actual `build_run_contract`, contract
parser, cycle preflight, `_parallel_decision_roles`, and `JevBlindPredictor.predict`.
The production control source is unchanged from commit
`80e1c798890db46e255ee7b82c1d34ee906923e3`; per-file hashes are in `result.json`.
It did not run or freeze a production dataset, admit source data, or create a
model answer. A temporary synthetic clean Git identity allowed the real builder
to be exercised while unrelated implementation work was in progress. Its SHA
is explicitly synthetic and cannot authorize a real cycle.

Reproduce using the project-compatible Python and `PYTHONPATH=src`:
`python3 runs/diagnostics/local_factory_route_20261019_v1/probe.py`.
Do not rerun into this original result after fixing production code; copy the
probe to a fresh diagnostic root for validation.

The initial probe fixture omitted frozen v8 limits and was rejected before
entering the target combination; its fixture was corrected to the existing
frozen constants before the retained run. No production validation was patched.

Observed original behavior:

- Both-local models plus `parallel_jev_decisions=true` are accepted by the
  actual builder and contract parser. The builder adds an OpenRouter Jev model
  even when no API key is available.
- A runtime object with that flag passes cycle preflight.
- With `allow_external=false`, the actual local caller nevertheless reaches
  an intercepted OpenRouter constructor. Without a key it instead raises a
  key-missing error after selecting the external path.
- With an explicitly fake diagnostic key, the actual Jev predictor reaches
  `UrllibTransport.post_json` for `candidate_judgment`. The transport is denied
  before transmission; zero HTTP transmissions and zero socket connection
  attempts occurred. The real key/environment was never read.
- The flag-false path retains `LLMSignalRetrievalAgent` and `LLMBlindPredictor`.
  Its native `StructuredRoleClient` writes one unanswered local inbox, raises
  `LocalRoleRequestPending`, creates no receipt, and records zero external
  attempts. No alternative LLM response, Jev distribution, or logprobs were made.

The cycle's coordinator and parallel worker both call the same vulnerable
helper. All composed prose/Signal-batch/Slow roles inspected in the production
factory receive `judge_caller`, `evolution_caller`, or `worker_caller`, each a
`StructuredRoleClient`; the explicit Jev helper is the direct provider bypass
found in this composition. This is a bounded factory audit, not proof that every
legacy research module in the repository has no direct model client.

Minimal fix: reject this unsupported combination before remote metadata/client
construction at builder, contract admission, cycle preflight, and shared helper.
Keep the local flag-false path and independently authorized remote-only paths;
do not invent native-agent Jev distributions or provider token scores. Existing
frozen files remain immutable; invalid combinations fail on admission/execution.

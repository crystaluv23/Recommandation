# Information Evolution MVP Implementation Baseline

## Frozen starting point

- Starting HEAD: `a9480ca`.
- Authoritative T7 workspace: `self-evolution-t7-20260908-v1`.
- Committed pointers: Fast round `0`, Slow cycle `0`; stable Registry version `1`.
- T7 model ledger: 250 attempts, 248 completed, one retryable failure, one
  in-progress reservation, and `$0.37523724` recorded actual cost.
- Candidate checkpoints remain partial at 17/24, 0/24, and 11/24. They are
  recovery/audit evidence, not completed fitness or learning.
- The pre-existing dirty runtime/spec/test/audit changes belong to the T7
  evidence-recovery work. The two untracked historical `reports/` trees are
  unrelated and remain untouched.

## Minimum acceptance matrix

| Property | Evidence |
| --- | --- |
| Complete ordinary case | Existing Plan/runtime integration tests |
| One invalid evidence row plus valid siblings | Typed ResearchState fallback tests and both T7 response replays |
| Correction success and exhaustion | Structured-role execution tests |
| Valid `no_match` | Routing role tests |
| Temporary provider error | Reliability/control tests |
| Interrupt and exact resume | Control, Plan engine, and reliability tests |
| Signal promotion and later consumption | Existing Signal engine/adaptor integration tests; real lifecycle still pending |
| No-gain result | Existing four-arm benefit evaluator tests; real confirmation still pending |

Unknown program errors remain fail-closed with their traceback, request hash,
context identity, and last committed pointer. Locked Test content is not read.

## B: structured evidence recovery

The high-frequency ResearchState failures now use stable
`basic_literal_not_grounded`, `claim_quantity_not_supported`, and
`assertion_without_support` issues. Paths, allowed repairs, dependent assertion
paths, source candidates, and numeric details are typed fields. Fallback dispatch
uses only those fields; changing message language or punctuation cannot change
the action. Shape-invalid rows stop deeper evidence checks. Unique literal
mapping remains deterministic, while ambiguous mappings are never guessed.

After bounded model correction, the call-free fallback removes only named bad
evidence rows and assertions that lose their final identical claim support. It
re-runs the complete parser after every state-changing step, rejects repeated
states, and refuses to remove all evidence.

## C: prompt and provider findings

Persisted T7 request counts are not first-pass rates: request hashes, actual
attempts, invalid-output audit artifacts, and cache reuse are different units.
The exact request inventory contains 31 H_init initial and 31 H_init correction
requests, plus 52 routing initial and 28 routing correction requests. H_init
initial/correction cached responses consumed 229,019/296,025 input tokens and
cost about `$0.07557`/`$0.09412`; routing consumed 108,934/80,780 input tokens
and about `$0.03492`/`$0.02519`. Initial validity remains unknown where no
per-request outcome label exists.

The fixed H_init and routing prompts were deduplicated without changing their
schemas or PIT, literal-support, no-match, applicability, and need-ownership
rules. Offline rendered system-prompt sizes changed from 9,649 to 8,757 UTF-8
bytes for H_init and from 4,671 to 3,424 bytes for routing. This proves only
lower fixed context, not better model quality or lower end-to-end cost.

DeepSeek's current Responses API documentation lists both JSON-object mode and
native JSON Schema output for `deepseek-v4-flash`:
<https://api-docs.deepseek.com/api/create-response/>. The current runtime keeps
JSON mode plus strict local typed validation for this checkpoint. Native schema
would change every affected wire contract and requires its own frozen provider
comparison; it is not silently enabled in an existing v7 contract.

Existing semantic-transition tests cover same-topic/different-period questions,
partial answers, financing mentions without terms, subject-only mentions, and
exact duplicates. No new false-positive evidence justified weakening those
hard gates in this checkpoint.

## D: persistence and recovery decision

The focused Plan/control/CLI/reliability suite confirms exact completed-case
reuse, immutable failed attempts, fixed-cohort scoring, pointer-last commits,
bounded provider/content recovery, and idempotent resume. The T7 live blocker
was an undersized attempt ceiling plus now-repaired role validation, not missing
attempt identity. Therefore no D3 retry schema or candidate persistence change
is introduced.

## E/F: external boundary

The old T7 contract is immutable and code-bound to `a9480ca`; it cannot execute
the repaired runtime. A new workspace must freeze after this checkpoint with:

- one candidate per Fast round;
- one Fast round before Slow, followed by a second cycle whose Fast work can
  demonstrate use of any promoted Signal;
- `deepseek-v4-flash` for proposer and judge;
- the approved development manifest and global Raw Info oracle;
- the same explicit four data providers, seven capabilities, eighteen source
  types, and 96/192 cycle/run data-request bounds;
- at most 2,500 model attempts and `$20` model cost;
- at most two cycles, stopping earlier on deterministic rejection, budget/data
  pause, unknown error, or absence of a valid candidate.

Freezing is local and sends no request. External model/data execution is still
unauthorized until the exact post-freeze contract hash and command are approved.
The four-arm benefit protocol remains unchanged. Its 80-case/60-issuer,
two-replicate, 0.05 minimum F1 gain, non-negative issuer-cluster interval lower
bound, 0.02 maximum coverage loss, 0.05 maximum technical-failure rate, 0.90
Signal accuracy, and 25% cost-regression values remain proposed research
parameters rather than active defaults. Until a real promotion exists, the
confirmation result is `incomplete`, not `no_gain` or `gain_confirmed`.

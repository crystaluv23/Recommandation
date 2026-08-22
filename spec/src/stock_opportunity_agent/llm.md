# LLM Capability and Generic Agent Harness

## Status

Started

## Purpose

Keep reusable model/provider adapters and the generic tool-calling runtime at a
top-level capability boundary. Research roles may share the harness. Signal
Mining and Signal Update use narrow structured role adapters because local code,
not a free-form tool loop, owns sampling, label disclosure, staging, and gates.

## Generic Agent Contract

`GenericAgent.run(prompt, tools, workspace, output_schema, max_steps)` executes
a bounded loop:

```text
model response
-> one named domain tool call or structured final output
-> tool observation
-> next model response
```

The model receives tool cards, an immutable serializable workspace view, and
prior observations. The harness records a trajectory and returns validated
structured output plus usage.

Tools are explicit `DomainTool` values. They expose a name, description, and
prompt-safe callable signature; an unknown tool or malformed turn fails closed.
When a granted tool call omits or misnames arguments, the harness records a
structured `invalid_arguments` observation with the expected signature and lets
the model repair it within the existing step bound. It does not invent missing
values. Explicit domain `ValidationError` exceptions are likewise returned as a
bounded `tool_validation` observation so the model can correct values such as a
timezone-free cutoff; all other exceptions raised inside a correctly bound
domain tool still fail closed. The harness never grants arbitrary shell or
filesystem primitives such as `ls`, `cat`, or `rm`.

Final-output schema `ValidationError` exceptions follow the same bounded repair
path: the invalid output and concise validation message are recorded as a
`validate_final_output` observation, while the schema remains unchanged. Other
schema exceptions fail closed.

## Usage and Limits

Every model turn reports LLM calls, token count, and cost when known. `max_steps`
is mandatory and positive. Task-specific runtimes add their own call, token,
cost, and research-round limits.

## Structured Role Transport Contract

Structured single-role calls serialize their user payload once as canonical
UTF-8 JSON (`sort_keys`, compact separators, Unicode preserved) and reuse that
exact string in both the durable role request and the provider message. For
registered production providers, preview builds the complete secret-free HTTP
payload through the same provider method used by execution. The request
artifact stores the exact canonical body text, byte length, and SHA-256; before
network execution the runtime rebuilds it and fails closed on any byte drift.
The HTTP transport sends the same canonical bytes. Request hashing, cost
estimation, audit replay, and network transmission therefore share one byte
identity rather than merely equivalent JSON objects.

## Invariants

- Provider secrets never enter prompts, workspaces, observations, or artifacts.
- Persisted production wire bodies contain no authorization headers or secrets.
- A judge role is no-web and receives no validation label or future outcome.
- A web-enabled proposer or mining agent never receives locked-test records.
- Final structured output is passed through the supplied schema validator.
- The harness itself cannot promote a Plan or Signal; domain orchestration owns
  validation and promotion.

## Signal Update Role

The Update role receives one exact stable Signal, its bounded learned profile,
and locally selected label-visible induction packets. It makes one semantic
decision: `no_change`, `defer`, or `update`. `update` must include the complete
`vNext` spec, skill when required, and executable fixtures; the other decisions
cannot carry a candidate. One bounded correction may repair malformed JSON,
but the role cannot select a target, retrieve arbitrary cases, inspect the
issuer-disjoint holdout, stage a candidate, run tests, or promote it. If local
target or induction requirements are not met, the role is not called. The
orchestrator may invoke this single-target role independently for at most three
locally ranked targets in one Slow cycle; failures and usage are isolated per
target and there is no multi-target prompt.

## Testing

Cover multi-tool trajectories, structured output validation, unknown-tool
rejection, bounded invalid-argument repair, malformed-turn rejection, bounded
output-schema repair, and maximum-step exhaustion.

# LLM Capability and Generic Agent Harness

## Status

Started

## Purpose

Keep reusable model/provider adapters and the generic tool-calling runtime at a
top-level capability boundary. Research, Signal mining, and Signal updating may
share the harness without creating task-specific agent classes.

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

## Invariants

- Provider secrets never enter prompts, workspaces, observations, or artifacts.
- A judge role is no-web and receives no validation label or future outcome.
- A web-enabled proposer or mining agent never receives locked-test records.
- Final structured output is passed through the supplied schema validator.
- The harness itself cannot promote a Plan or Signal; domain orchestration owns
  validation and promotion.

## Testing

Cover multi-tool trajectories, structured output validation, unknown-tool
rejection, bounded invalid-argument repair, malformed-turn rejection, bounded
output-schema repair, and maximum-step exhaustion.

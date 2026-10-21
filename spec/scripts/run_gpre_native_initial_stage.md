# GPRE native initial research diagnostic

## Scope

The fixed profile lives at `runs/diagnostics/gpre_native_initial_20261021_v1/stage`.
It asks whether the qualified 1780-document reviewed view can support a genuine
single-case bootstrap and H_init at 2025-05-30 UTC. It uses the explicit
`default_information_plan()` manual research Plan, not a source/capture plan,
and calls `run_reviewed_orientation_stage._run_initial` unchanged. Native core
computes the evaluation context, market anchor, computed cards and BasicInfo.
Company name and ticker aliases come from the bound SEC cover and market
metadata; identity evidence is retained outside role input.

## Boundaries

Prepare freezes source/result/view bytes, the original latest-v12 18-definition
snapshot, current execution code/spec and the manual Plan. Reconstructing the
definition snapshot must not invoke fresh freeze or capability audit. The
independent source oracle is separately bound as an opaque file and never
included in author payloads. This is not a cohort run or a successor contract.

Resume uses a real native StructuredRoleClient and LocalRoleExchange with at
most two independent author requests and one native structured correction.
Each request reserves canonical messages UTF-8 bytes plus maximum output,
at most 131072 logical units; the whole case is at most 256000, without
borrowing or budget reset. Replayed immutable requests retain the same logical
reservation. Only initialize and its native correction stages are allowed.
Native RuntimeLimits requires at least three LLM calls for the full execution
scaffold; its legal minimum of three does not authorize a third author here.
The local exchange and request observer enforce the stricter two-request limit,
including the existing patch-mechanics correction, and the tail is forbidden.
After accepted H_init and native usage/state persistence, InitialBoundary stops
before routing, Signal execution, Reflect, Predictor, prediction or labels.
Network, external API, acquisition, raw append, Signal execution/preparation,
Registry freeze/promotion and label access are forbidden. Failure is terminal.
Completion cannot be resumed to create further role requests.

## Preparation evidence

Before formal prepare or dispatch, a temporary destination runs the complete
actual metadata/identity/reviewed store/default Plan/Registry/core/client chain
until its real pending inbox and outbox parent exist. There is no authored
answer, accepted state or fake need. The preflight retains native BasicInfo,
gaps, anchors, anonymous request, reservation and all binding checks. It proves
the connection only; later fresh H_init and independent semantic review remain
separate. Temporary roots are explicit test overrides, not alternate production
destinations or author budgets. Every failed attempt remains intact.

## CLI

`--prepare --expectations PATH` freezes the fixed stage without dispatch.
`--resume` advances only this frozen stage to pending or accepted H_init.
`--submit HASH --agent-id ID` binds a separately authorized fresh raw answer.
The driver never authors or edits an answer. Formal invocation requires root
review and authorization; synthetic/temp preflight is not formal prepare.
The fixed directory name is not an anonymous role handoff: the authorized
dispatcher copies the native inbox byte-for-byte to a neutral temporary path,
binds its hash, and returns the independently authored raw bytes unchanged to
the native outbox before submit. No issuer-bearing paths or private source
oracle are given to that fresh author. This changes no transport or request.

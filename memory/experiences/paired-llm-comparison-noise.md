# Paired Blind-LLM Comparison Noise

visit_times: 4

## Trigger

Read this before comparing baseline and candidate information plans with a
blind LLM, especially when interpreting confidence deltas from one call per
packet.

## Lesson

An identical packet can receive a slightly different confidence score in
separate provider calls even when the model and prompt are unchanged. A paired
information experiment must reuse the same cached response for an unchanged
packet hash. Otherwise model sampling noise can be mistaken for acquisition or
organization lift.

Confusion-matrix changes and threshold crossings are more meaningful than tiny
confidence movements, but they can also be unstable near the decision
threshold. Record the model, temperature, and other sampling settings, and use
repeated calls only when the extra cost is justified by the decision.

## Context

In the July 24, 2026 v36/v38 frozen six-case comparison, SRM received no SEC
Company Facts and its raw packet hash was identical in both runs. Separate
OpenRouter calls returned the same `insufficient_information` judgment but
confidence 0.40 and 0.38. The candidate's aggregate confusion matrix was
unchanged, so the small confidence movement was correctly treated as noise.

## How to Apply

1. Freeze cases, source documents, prompt, model, and decision threshold.
2. Key the response cache by the exact packet hash and relevant model settings.
3. Reuse a cached response when the candidate packet hash is unchanged.
4. Report `TP`, `FP`, `TN`, and `FN` before confidence deltas.
5. Do not claim lift from a small single-call confidence change without a
   classification change or repeated-run evidence.

## Limits

Response reuse isolates unchanged inputs but does not remove noise for packets
that actually changed. Repeated sampling or a deterministic provider setting
may still be needed when a decision depends on a small near-threshold delta.

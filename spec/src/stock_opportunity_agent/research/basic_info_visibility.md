# Basic Info visibility summary

Pure ephemeral presentation helpers retain source status, current normalized
projection counts/ids, up to eight existing omission markers, and separate
three-valued source/projection/effective omission flags. Known raw resolver
coverage may supply the source flag; markers establish an effective omission
without guessing its stage. An explicitly saved effective omission, partial/
omitted status or positive omission count also retains that known omission;
its missing layer flags remain unknown. No count is promoted to source-document fullness.

Final, posthoc (both packet forms) and critic use the same source-index
projection; saved unknowns are not turned into false. This helper neither
reads additional sources nor grants evidence authority, and it does not
mutate archived rows. Role masking still applies to every string.

For a saved trajectory or packet containing both an old final source index and
the original Basic Info bundle, merge known upstream flags and omission markers
by exact request_id before summarizing. Final projection counts/flags retain
their original layer; never copy resolver counts into them or join different
requests. Known omissions are retained conservatively; missing upstream
information remains unknown. Recovery may retain the bounded union of both
marker lists (up to sixteen); original producer lists remain at most eight.

The final critic wire uses a lossless, payload-local representation to avoid
repeating long visibility field names over many cases. Each source-index row
contains a `profile_ref` and its complete `projection_ids` (when originally
present). Top-level `basic_info_visibility_profiles` maps that ref to the exact
remaining descriptor: request identity/types/status/counts, all three-valued
flags and all markers. Reconstructing the descriptor plus original ids must
produce the complete helper row exactly, including absent fields and null vs
false. Different markers, request ids or unknown/false states cannot merge.
Profiles are scoped to this single request payload; they are neither a cache nor
a Registry, source evidence or valid reflection citation. They are masked with
the rest of the role input. The critic instruction explains how to join the
profile with each row. Final/Predictor/posthoc and the complete trajectory helper
remain unchanged; only the final critic wire representation is packed.

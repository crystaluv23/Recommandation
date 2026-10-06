# Jev Historical Shadow Harness

## Purpose

Freeze, execute and score the existing Jev historical-shadow experiment from
immutable saved Plan trajectories and transmitted routing requests. Preparation
is local; execution retains the existing authorization, budget, hash and label
separation checks. It does not alter production scoring or source artifacts.

## Frozen routing identity

Match a saved routing request to the exact information needs, prediction cutoff
and prior-result identities, versions, values, confidence and coverage. Available
result summaries remain exact. For unavailable results, evolving safe-summary
wording is presentation rather than request identity: ignore only that summary
when comparing the prior results. A recorded execution status must match; a
legacy missing status remains unknown and is not backfilled in the saved packet.
Reject differing result sets, state, versions, coverage, recorded status and
ambiguous matches. Return the original saved request unchanged after matching.

## Verification

Exercise old and current summaries, unknown legacy status, mismatching canonical
fields and recorded status. Preparing the historical fixture must preserve its
original routing request count and input contents without external calls.

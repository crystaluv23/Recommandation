# Canonical label admission before bounded feedback

The existing single-door contract is now enforced by `LabelStore.load`: archive
identity/hash, fixed calculator and SURGE contract, strict JSON types and every
record's original and derived observations must agree before any truth is exposed.
No label definition, store version, historical record or shared calculator changed.

## Failure and repair

The old loader checked presence, count and internally consistent record shape.
It accepted a changed source hash, calculator/contract and even an internally
consistent label derived from different prices. Its tests used `/dev/null` with
a zero hash, so roundtrip success never tested the promised source verification.
The [original independent evidence](../runs/diagnostics/label_store_loader_boundary_20261020_v1/independent-review.json)
retains 18 false admissions among 24 fixed cases, with original loader/calculator.

The repaired loader reads the bound archive once through the shared streaming
reader. Hashing uses the same UTF8 stream with original CRLF bytes; parsing must
reach EOF, rejecting trailing content, trailing commas, duplicate fields/symbols
and invalid JSON whitespace. Selected histories require valid distinct dates and
finite positive numeric adjusted closes, without boolean/string coercion. Every
record is recomputed by the unchanged sole calculator, including means, member
dates and horizon. Bad source shape or disagreement raises typed ValidationError.
Unknown case keys remain explicit exclusions. There is no verification bypass.

The reader moved to `data` so `cases` does not depend on `research`. The original
dataset private name remains an alias and retains default whitespace behavior;
strict label decoding is opt-in. There is no added dependency or cache.

## Evidence and scope

[Independent current review](../runs/diagnostics/label_store_loader_boundary_20261020_v1/independent-current/independent-review.json)
finds all 18 old false admissions rejected, the legal positive accepted and five
old negative controls preserved. Another 29 variants cover streaming/shape/EOF,
plus exact CRLF/UTF8 hashes at five chunk sizes. Multi-symbol and same-symbol
multi-boundary records pass. Local label/dataset tests: 26 passed; full regression
passed: 1806 tests in 180.865 seconds. Final lint is recorded below.

The actual canonical manifest has 6554 records. After the prefix's durable sink,
[actual s01 source qualification](../runs/diagnostics/label_source_qualification_20261019_v1/actual-s01.json)
independently binds manifest, labels, frozen archive, calculator and contract.
The sole calculator reproduces the record; its baseline 6.494 and five dates and
six-calendar-month horizon match the saved prediction definition. The first full
strict load reconciled all 6554 records in 9.463 seconds, peak RSS about 61 MB,
without modifying source files. The final current-source validation is recorded
separately: current-source full load passed in 9.383 seconds, peak RSS about
66 MB, with concrete code/store/sink SHA bindings and unchanged before/after maps
in [the final result](../runs/diagnostics/label_source_qualification_20261019_v1/strict-load-final.json).
Repeated source verification needs no new cache.

This closes only deterministic admission consistency with the bound archive.
It does not authenticate provider prices, adjustment basis or CIK-symbol mapping;
those source qualifications remain distinct. No Posthoc role, score, trajectory,
Slow import, new prediction or research benefit is claimed. External LLM calls,
new read-only data requests and feedback dispatches are all zero in this batch.
The next stage needs its own frozen Posthoc expectation and budget; the completed
prefix and its exhausted collection budget remain unchanged.

Validation finished: 1806/1806 tests passed (180.865s). Pre-push lint at
2026-10-19T16:54:58Z passed, and the saved feedback was personally read.
Original archive/store and completed blind-prefix files were not modified.

Final staged whitespace check removed one empty EOF line from the new reader.
The 16:55:42Z pre-push lint passed and was personally read.
[Documentation binding](../runs/diagnostics/label_store_loader_boundary_20261020_v1/final-documentation-bindings.json)
reconstructs the exact reviewed hashes before public docstrings and the exact
full-store execution hash before that EOF change; behavior ASTs agree. Original
review and actual execution records retain their original hashes.

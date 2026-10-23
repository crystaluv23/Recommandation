# Independent query-origin review

Result: eight offline test groups pass; 4337 exact comparisons against the
functions extracted independently from Git revision `f0f81fb1` preserve the
old excerpt and clipped flag. Old complete evolution_core.py SHA-256 is
`86af38cbea304799b2974b631c11dcba07266f9033bd331fa155246394a54617`.
No product defect was found in this bounded review.

The generated cases exercise Unicode and JSON escapes, decoded duplicate keys,
fixed projection order against reverse raw field order, nested decoys, nonstring
values, metadata-only text, HTML/hidden duplication, a 30000-character hidden
gap, invalid JSON fallback, and raw windows around 4000-character boundaries.
Every JSON-origin fragment in generated Mapping cases is independently decoded
from its actual raw slice and compared with its claimed projection substring.
The old and new fetch outputs preserve documents, facts, canonical narrative
events, request, query coverage, excluded documents, and unread accounting.

Controller checks establish bounded whole-hint pages, multi-case binding,
cross-action availability, repeated-fetch deduplication, distinct-query retention,
ordinary heavy/browse accounting, rejection of unread narrative citations,
acceptance after the corresponding real local read, stale source snapshot flags,
and separate event-read permission for two cases sharing one source. Hints are
not ledger evidence refs or materialization reads. Future-available and foreign
owner sources produce no navigation.

The first attempt had one harness error: constructing a RawInfoDocument with a
changed hash but unchanged content was correctly rejected by its invariant.
The first script, log, and summary are preserved. The fixture was changed to a
valid different content/hash snapshot; attempt two passed. Attempt three added
per-fragment JSON decoding and the shared-case read-permission counterexample;
all eight groups passed. No product code was changed by this reviewer.

Evidence: `review.py`, `attempt-3.log`, `summary-attempt-3.json`.
Network tripwire attempts: zero. No API, LabelStore, stage execution, original
artifact modification, or production role request occurred. These are local
mechanical checks, not fresh model behavior or research effectiveness evidence.

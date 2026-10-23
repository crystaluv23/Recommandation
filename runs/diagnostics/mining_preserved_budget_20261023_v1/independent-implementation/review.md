# Independent implementation counterreview

Reviewer: `/root/budget_counterreview`, 2026-10-23. Read-only product review of
`5fcf473b` historical-budget / native recovery changes; no production author,
external API, network, formal v4 oracle or stage was created by this review.

## Result

No new blocking implementation defect found in the reviewed budget/prefix and
completed-seed reconstruction family. This closes the previously missing
independent implementation counterreview prerequisite, **not** fresh Mining
behavior, candidate semantics, publication, consumer capability or MVP closure.

The reviewed driver enforces global and Mining limits independently at the
actual serialized request-ready boundary. The native Mining model starts from
the verified v3 historical prefix once, then accrues only ordered local cached
answers. The shared model is reused between seeds. Restoring a completed seed
requires the separately saved exact-byte checkpoint binding, a snapshot whose
members match local receipts, and counters equal to historical consumption plus
that snapshot; later receipts are not substituted for the earlier prefix.
Initial usage remains new-evaluation usage rather than fictitious historical
host usage. Both advance and submit verify the frozen contract and old controls.

## Evidence

`stage-tests.log`: all 27 current stage tests passed in 42.345 seconds using the
bundled Python. They include the actual native dual-seed completion/replay path,
missing checkpoint receipt, jointly changed counters/snapshot, deleted earlier
checkpoint with future answers present, exact budget edges, malformed submitted
content, native first-request/input-only capture, and old-root mutation refusal.
This is an independent rerun of existing tests, not 27 newly designed controls.

`counterreview.py` / `counterreview.json`: 17 additional independently constructed
checks passed. They verify all three real predecessor controls; reject symlink
aliases of the three old roots; reject bool/negative/reset usage, missing
answered identities and scope reassignment; preserve all three committed old
oracle byte strings; and use the real v3 prefix in temporary native transport
controls for both global and Mining exact-fit, one-unit excess and zero call
remainder. Exact fit reaches a native inbox, intentionally invalid submitted
JSON consumes its complete wire reservation, and rechecking the same wire does
not double-charge. Candidate scope does not separately inherit Mining debt.

Real predecessor consumption remains 12/2,001,316, 11/1,837,419 and
10/2,055,941. Real v3 prefix yields 70/10,526,971 Mining and
718/56,664,315 global remaining under the unchanged original ceilings.
The 312 sealed v3 file hashes and product/spec/test source hashes were equal
before and after the controls. Formal v4 oracle/stage were absent at review end.

The first independently authored synthetic transport fixture omitted required
Mining stage-input fields, so validation correctly stopped before request-ready.
That harness failure is retained in `counterreview-first-harness-error.log`;
the corrected fixture obtains the native empty controller model view. No product
change was needed, and the first failure is not counted as a product defect.

## Limits and next gate

The checkpoint binding is an immutable workflow receipt, not a cryptographic
signature against an adversary rewriting all authority files. That is the same
trusted-local-artifact boundary used by the frozen manifest and terminal seal.
Tests validate fail-closed state/cost reconstruction, not operating-system crash
recovery or host token/currency measurement.

It is reasonable to prepare a prospective v4 oracle by retaining the original
source-semantic obligations and denominators while rebinding only the repaired
code/spec/predecessor metadata. Verify unchanged protected obligations before
freezing. Fresh production authors must then receive only their exact native
inbox under the original remaining budgets. No old v3 reentry, answer import,
budget reset or prewritten action follows from this review.

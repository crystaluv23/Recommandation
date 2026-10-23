# Independent ordering-regression recheck

Revision two passes all ten offline groups: the original eight groups plus two
new ordering counterexamples. The 4337 old-function excerpt/clipped comparisons
still match. No network attempts, API calls, LabelStore access, stage execution,
or product modifications occurred in this review.

The added whole-fetch test uses three case refs, two source documents, and all
six permutations of the requested case order. Complete `coverage` and
`omitted_coverage` dictionaries are identical across permutations. Navigation
has canonical case-ref order while preserving selected-document order and each
document's title-before-body projection order, even when the raw body precedes
the raw title.

The added working-page test uses reverse raw JSON fields and three fetches:
query A, query B, and repeated query A. It checks newest-fetch ordering between
queries, deduplication with the newest action id, and intact title-before-body
ordering within each fetch. This is the distinction the original eight groups
did not assert: page limits and fragment validity alone did not verify ordering
inside a single fetched result. The parent found the whole-fetch coverage
regression with its associated test; the earlier independent report is retained
as bounded evidence, not rewritten to claim it had caught that regression.

Evidence: `review-revision-2.py`, `revision-2.log`, `summary-revision-2.json`,
and `reviewed-source-hashes-revision-2.json`. Prior scripts, logs, summaries,
review report, and reviewed source hashes remain unchanged.

This verifies mechanical ordering and preservation only; fresh model behavior
and research usefulness remain untested.

# Repeated-read frontier: information increment and stop evidence

Reviewer `/root/budget_counterreview`, 2026-10-23. This is a minimal read-only
diagnostic of actual h025→h026→h027 inputs and old accepted source windows. It
does not submit h027, run a research tool, modify the frozen code/stage/oracle,
or evaluate the separate A worktree.

The evidence supports a **parent decision to stop the current repeated-window
search strategy for low information increment**, retaining native pending and
the uncompleted capability result. It does not establish a code defect, an
infinite loop, inability to synthesize a candidate, or absence of a pattern.

## What actually changed

| Action | Exact previously read unit | Result in next actual model input |
| --- | --- | --- |
| h025, executed | h008: case-001, same source/hash, offset 267,000 / length 4,000 | Restores that whole readable unit; read count 1→2. It pushes case-003 offset 1,148,801 / 4,000 from the 12-unit body page into explicit omitted entries. |
| h026, executed | h010: case-003, same source/hash, offset 1,148,801 / length 4,000 | Restores that whole readable unit; read count 1→2. It pushes case-003 continuation offset 1,152,908 / 4,000 into explicit omitted entries. |
| h027, raw only | Selects h011's same case-003 source/hash, offset 1,152,908 / length 4,000 | Not submitted or executed. Its rationale explicitly cites current body-page omission. No result or future page is inferred. |

Both executed rereads have exact original raw-span SHA-256, original source
content hash/object/coordinates and identical visible returned text to their
first reads. Each restored unit is the sole added visible body-page member, and
each displaced unit is the next independently authored read selection. The
page remains 12 of 16 unique read units, with four explicit omitted locators;
read-progress retains all 16. Source retention and omission are truthful. This
is an observed finite chain of two page transitions, not a claim that every
future reread must displace indispensable content.

Across the two executed rereads, the complete accepted source-window map stays
byte-for-byte equal: **16 unique units from nine documents**. Known facts,
relations and events, evidence digest, backlog rows/hash and exact catalog
observations remain unchanged. The digest still has 2,093 facts, 947 relations
and 14 events. No new independent source, new source fact, candidate or need
disposition is produced. The measurable gain is restoration of currently
visible old source text and a repeat-read receipt, rather than additional
research evidence. That restoration can still be useful for later reasoning;
the current evidence does not determine whether h027 would enable synthesis.

The two rereads cost **237,574 + 241,252 = 478,826 logical reservations**.
Current accepted accounting is historical **10 / 2,055,941** plus new
**26 / 5,367,457**, combined **36 / 7,423,398**. The original Mining limit is
80 / 12,582,912, so 44 calls / 5,159,514 remain before any h027 submission.
h027's prospective 240,149-unit request fits the original single and aggregate
ceilings. Therefore **budget exhaustion is false** at this frontier. Costs are
logical reservations, not measured host tokens or money.

## Interpretation and decision boundary

Normal charged rereads are permitted by the frozen interface. The page declares
its omissions and supplies coordinates, and the runtime returns correct source
text. These observations do not demonstrate an implementation violation. The
bounded current-view design and the actually selected read sequence together
explain the observed replacement of one useful old window by another. The
review does not infer an author's memory, intentions, or what an alternative
permitted action would have produced.

The latest two actual actions add no independent evidence or candidate progress
and the pending third action proposes another exact old-window reread. This
provides concrete information-increment evidence for the AGENTS/work-contract
option to stop this strategy rather than keep spending until a result appears.
It is a discretionary bounded-search decision, not proof that continuing could
never succeed. A finite recovery of several omitted windows might eventually
allow a new synthesis; that counterfactual remains unknown. No immediate rerun,
new code-version target or larger cap is justified by this diagnostic itself.

## State that must remain honest

The exact native state is still `pending_independent_role` at request
`a7c5f884f8ca9c6f9b605b30c94242808fe095f6ad42e958b1edd3a373eb4de7`.
The h027 raw file exists, but its receipt and native response cache do not.
No completion/failure seal or `mining-output.json` exists; business round/cycle
pointers remain 0/0. Preserve these facts and the original candidate
denominator 1/uncompleted and four unattempted consumers. A parent stop receipt
must not be represented as `no_pattern`, completed Mining, exhausted budget,
technical acceptance, a new model failure or MVP convergence. Do not submit or
import the prepared h027 answer under a stopped-control record.

`reread-frontier-check.py`, `reread-frontier-evidence.json` and the successful
log provide exact static bindings, original/repeated read equivalence and both
observed body-page set differences. Current runtime and original oracle hashes
are unchanged. The first audit run incorrectly demanded direct equality of
model-facing catalog JSON despite request-local identity aliases reindexing
when body units reorder. Its failure is retained in
`reread-frontier-first-harness-error.log`. Stable observation refs, response
hashes, source-snapshot hashes/status and metadata are equal; correcting this
review-harness comparison required no product or source change.

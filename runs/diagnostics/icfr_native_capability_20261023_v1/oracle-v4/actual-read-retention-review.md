# Actual h004–h007 read-retention review

Reviewer `/root/budget_counterreview`, 2026-10-23. Read-only original-source and
actual-wire review through **h007 input only**. No first loss or blocking
propagation error was found on these two executed read paths. No source,
product, stage, frozen oracle, receipt or author answer was changed; no author
received review information or suggestions. h007's answer is outside this review.

The first six raw answers retain their native cache/receipt/actor connections.
For the two actual read actions, the requested offsets and lengths were executed
exactly, with no whole-unit relocation or length change:

| Read action | Actual source/case | Raw offset / length | Visible text |
| --- | --- | --- | ---: |
| h004 `10a60089…` | accession `000114036125018373`, case-002 | 3,970,161 / 4,000 | 2,123 characters |
| h005 `dd6cc39b…` | accession `000121390024092156`, case-001 | 26,191 / 696 | 458 characters |

Each original source's exact raw slice matches the returned `verbatim_hash`,
ledger-owned read and later retained unit. Independent removal of HTML tags and
whitespace folding reproduces the complete returned visible text for both
windows. The first ends inside an unfinished HTML opening tag, which contains
no visible prose and is excluded; no source sentence is removed by that cleanup.
These are complete **requested windows**, not claims to have read full documents
or whole ICFR sections. `next_readable_start` and coordinates remain visible.
Transport-local anonymization may change alias numbers between requests, but
original canonical document refs, ledger hash, source content hash and case scope
prove that case-002 and case-001 were read in the intended order without an
object swap.

After h006's new `material weakness` query, h007 retains both earlier complete
readable windows, offsets, lengths, raw/content hashes, source types,
publication/availability times, case scopes and next-read coordinates. The
read-evidence page includes both units, declares no omitted/oversized entries
and is exhaustive for the two actually read units. The fields and visible text
are equal to those in h006 input despite the last-action result now being a
fetch. Source publication and availability remain within the corresponding
original case cutoffs.

The complete 18 exact baseline Signal capability cards remain in the seven-card
normal page and two retained inspected pages. Native fetch action 6 retains the
literal authored refined query and creates 31 new discovery navigation records.
The earlier 34 records remain ledger-owned, for 65 total. All 65 original raw
coordinates and span hashes were checked against the approved bound documents.
h007 displays eight newest-query records, explicitly reports 57 omitted and
keeps discovery-only/not-read/not-citable status. This verifies truthful bounded
navigation and preservation, not that those query hits establish ICFR findings.

Independent source reading supports h006's rationale. The case-001 window is a
cover-page question asking whether an auditor attestation report under section
404(b) was filed; it does **not** supply management's ICFR conclusion or even a
completed yes/no response within this bounded text. The case-002 window reports
effective **disclosure controls and procedures** at the covered quarter end and
no ICFR change during the three months ended March 31, 2025 that materially
affected, or was reasonably likely materially to affect, those controls. That
does not establish annual ICFR effectiveness, absence of material weaknesses,
remediation, or status at the later prediction cutoff. The author's wording
keeps this distinction and treats the refined search as navigation rather than
absence, completed comparison or predictive benefit. No semantic overclaim was
observed in that particular rationale.

`actual-read-retention-review.json` binds the precise reviewed inboxes, raw
answers, caches, receipts, six-action native observation and original sources;
`review_read_retention.py` reproduces the checks. Current frozen product/source
bindings and three original oracle hashes also verify unchanged. Later author
actions are outside the fixed review. This is narrow actual read/retention
evidence, **not** full F5, candidate-semantic, admission, consumer or MVP closure.

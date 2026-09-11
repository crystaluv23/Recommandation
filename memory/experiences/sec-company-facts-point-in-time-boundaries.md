# SEC Company Facts Point-in-Time Boundaries

visit_times: 4

## Trigger

Read this before acquiring, filtering, or materializing historical SEC Company
Facts for point-in-time cases.

## Lesson

The Company Facts endpoint is a current aggregate response, not one historical
document. Validate the response-level registrant CIK, then group eligible rows
by accession and assign availability from that row's filing date. Do not require
the accession prefix to equal the registrant CIK: valid filings can carry an
accession whose first ten digits belong to a different SEC submitter.

Do not backdate response-level fields such as the current entity name. Preserve
only accession-linked facts, record that extraction was retrospective, and keep
the corresponding primary filing as the audit authority.

## Context

While adding the expanded-case Company Facts stage on 2026-08-09, an initial
guard compared each accession prefix with the response CIK. Prestige Wealth's
official 20-F is filed under CIK `0001765850` but has accession
`0001213900-24-014546`, proving that the guard would silently discard legitimate
foreign-issuer facts. The corrected implementation validates response CIK and
accession syntax independently.

Company Facts rows expose a filing date but not the acceptance timestamp used by
the submissions feed. The backfill therefore makes facts available at the next
UTC midnight and flags every derived document for primary-filing audit.

## How to Apply

1. Freeze one exact per-CIK request plan from a label-free case scope.
2. Restrict forms, standard taxonomies, period ends, and latest availability.
3. Validate the response CIK, but treat accession as an independent filing id.
4. Group by accession and deduplicate identical fact rows deterministically.
5. Set next-day availability when only a filing date exists.
6. Exclude current response identity fields from historical content.
7. Store raw responses in cache and append content-versioned Raw Info documents.
8. Audit important facts against the primary filing before research use.

## Limits

Next-day UTC is conservative, not a substitute for an exact SEC acceptance
timestamp. Company Facts also does not supply complete narrative disclosures,
news, transcripts, or historical point-in-time company profiles.

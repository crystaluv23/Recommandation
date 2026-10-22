# Source disclosure navigation

The data disclosure interface indexes immutable, point-in-time-selected Raw Info;
it does not acquire sources or infer research conclusions. Existing catalog,
fetch and raw provenance behavior remains owned by the original raw coordinates.

`readable_section_index(readable)` is a pure shared index of SEC Part/Item
heading-pattern matches in the exact supplied readable string. Each row retains
the source-order section id, bounded literal heading, its character offset and
heading length, and the span to the next match (or text end). Table-of-contents
entries and cross-references can match; this is navigation, not authoritative
section classification, completeness, or evidence of absence.

The raw document-card adapter maps those same heading coordinates through its
own readable-to-raw origins. A consumer with a different normalized view must
index that exact view instead of copying raw offsets into normalized reads.
The index has no query ranking, source filtering, summarization or citation
authority. Consumers own bounded paging, explicit omissions and disclosure
budget accounting. Only subsequent original-source reads authorize citations.

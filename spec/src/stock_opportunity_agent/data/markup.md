# Source markup visibility

## Purpose

Data owns deterministic nonvisible HTML ranges shared by selection, disclosure
and source projection. The helper returns original half-open raw intervals;
original documents, hashes, dates and quoted evidence never change.

## Contract

`nonvisible_html_ranges(raw_text)` skips head, script, style, template,
Inline XBRL header/hidden and elements explicitly hidden by HTML attributes or
inline display:none / visibility:hidden. Nested blocks form one outer range;
unclosed hidden blocks end at EOF. Ordinary visible elements and accessibility
attributes alone do not remove content. External stylesheet inference and
semantic financial extraction are outside this helper.

Hidden text must be excluded before readable-context windows consume budget,
not merely after selecting raw offsets inside a large hidden header. Both data
window selection and research projection use these same intervals. All readable
characters remain mapped to literal original offsets. No issuer/date exceptions.
Existing exact raw reads remain addressable and are not silently relocated.

`visible_html_ranges` returns the complement of nonvisible blocks and markup
tags in original coordinates. Source disclosure may intersect these intervals
with an exact requested raw window, including windows starting inside a tag or
hidden block. It must report empty readable content and the next readable raw
coordinate, without moving the requested window. A readable projection is not
a new verbatim source or a replacement for the raw document hash.

## Validation

Exercise nested, incomplete, mixed-case and inline styles; preserve ordinary
visible content and exact projection lineage. Replay a real filing whose hidden
header previously consumed every selected window. Offline visibility proves
coverage/lineage, not semantic completeness or research gain.

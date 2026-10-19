# Filing orientation primitives

Exact SEC form qualification is shared by request matching and structured
coverage. Only generic filing sources or exact typed SEC forms can qualify;
metadata cannot upgrade news/market/facts/commentary into a filing. A nonempty
form field is authoritative and must agree with an exact typed source. Titles
are not form proof. Exact requests do not silently match amendments, substrings
or title references; generic filing evidence remains readable.

The shared source-versus-form predicate also serves SEC proof qualification.
Generic `filing`, `sec_filing` and `filing_body` aliases retain their original
source type and may carry any nonempty proved SEC form, including S-1 and
amendments. Exact typed `10-k`, `10-q`, `8-k`, `20-f`, `40-f` and `6-k`
sources qualify only when their case-insensitive whole form equals the proved
form. Other types, news and substring matches reject. This does not expand
the operating-form set: generic nonoperating forms remain generic evidence.

The versioned operating orientation orders the latest available annual
(10-K/20-F/40-F) then latest interim (10-Q), each chosen by availability rather
than query hit count. Thus count two can include background and recent update;
count one prefers annual when present, while interim alone remains sufficient
for the OR periodic-source requirement. Remaining candidates keep their normal
rank. Apply this same pure order locally and before provider body limits, then
use the ordinary append/requery contract. Other generic requests keep their
existing rank. Available refers to the actually eligible local/acquired pool,
not an unqueried provider universe; selected forms never prove all business
facts were visible or the research need was answered.

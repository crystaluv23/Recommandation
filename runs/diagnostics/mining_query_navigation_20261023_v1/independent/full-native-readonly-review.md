# Read-only review of the full-source offline probe

The probe's scope statement is appropriate: it reconstructs ten recorded answers
in a temporary workspace, then executes an explicitly scripted hypothetical query
and read. It supplies no eleventh author answer and does not claim fresh model
compliance. The code stops prospective captures at request_ready and forbids
receive; the original completed stage is never the execution destination. The
12 MiB / 80-call limits match the sealed diagnostic contract and its normal
Engine override. No hidden budget increase or reopening was found.

Independently verified from saved files: the original ten inboxes, outboxes and
receipts match their receipt hashes; their reservations sum to 2055941. Captured
message JSON plus the 4000-output reserve is exactly 232555 after the hypothetical
query and 234197 after the hypothetical read. Both payloads retain spent
2055941/calls 10, single limit 262144, total limit 12582912 and call limit 80.
Their input-contract payload hash and UTF-8 byte count also match. The four raw
navigation slices match source documents and their disclosed raw hashes.

All 312 completion hash bindings pass, and the stage currently contains 316
files; the probe separately asserts its own 316-file before/after equality.
263 source bindings and all 182 tested source/spec file hashes match. The original
completion remains terminal_resource_or_control_stop, with ten existing inboxes
and ten receipts. The probe's first tuple-versus-list comparison failure remains
in its original log. This reviewer did not rerun the probe, enter a stage, call
providers or network, access LabelStore, or change original artifacts.

Cost interpretation must remain precise: these are two prospective captures for
different hypothetical tool states, both using the same old spent prefix. They
were not dispatched and are not two newly consumed model requests. The numbers
measure logical bytes-plus-output reservation; host-model tokens and currency
cost are unmeasured. The ordinary local tool actions add one heavy and one browse
charge. Source interpretation and fresh model behavior are still unverified.

This review itself initially made two harness assumptions that were corrected:
it compared the transport input envelope with the diagnostic contract, then used
UTF-8 cost serialization for the ASCII-escaped artifact hash. The saved first and
second audit failure logs preserve both; the final audit verifies each distinct
contract/encoding. They were review harness errors, not product/probe failures.

Evidence: full-native-readonly-review.json, full-native-audit.py and
full-native-audit-third.log. Original review evidence is retained.

# Bounded read-only market proof collection

Collect only the 30 GET requests frozen in the original
`market_source_qualification_20261020_v1/inventory.json` (SHA256
`cd20f162f7d7bd04d0340732bd0b19262b9aad6e03f06594d72fc909a35f2183`).
Verify every distinct nested path/hash binding (38, distinct from the inventory
producer's binding-array count), request identity and exact endpoint/query
whitelists before any socket or credential load. The original inventory and
its bound admission profile remain unchanged.

`scripts/collect_reviewed_market_proofs.py --inventory FILE --output DIRECTORY
--max-new-requests N` exclusively freezes its script/inventory bindings, original
requests, 30 cumulative attempt ceiling and rolling 5-per-60-second throttle in
`plan.json` before collection. One output lock protects plan, attempt ledger,
raw bodies and result receipts. Resume uses the same directory and exact plan;
it never recreates the output, resets attempts or replaces a raw body. The first
invocation may intentionally stop after two requests; later invocations can
collect the remaining 28 under the same ceiling. No failed or interrupted
attempt can be retried without a separately authorized change of contract.

At actual collection only, the existing environment loader supplies
`MASSIVE_API_KEY` for an Authorization Bearer header. Credentials never appear
in URLs, errors, receipts or output. Redirects are refused. Each sequential
attempt is durable before its GET, with a 30-second timeout and no retry.
Persist exact response bytes exclusively, followed by the existing BMBL receipt
fields (`name`, endpoint/query, retrieval instant, HTTP/provider status,
pagination marker, raw filename/hash). A response containing the credential is
not persisted or silently redacted. Auth/HTTP/provider/pagination/timeout or
credential-leak failure stops that invocation and leaves its failed/pending
attempt visible. Previously completed receipts and raw hashes must verify
before resume skips them. A crash after raw persistence cannot authorize a retry.

This collector only retains evidence. It does not normalize data, admit sources,
rewrite original clocks, load labels, prepare research runs or invoke LLMs.
Subsequent qualification still uses the existing reviewed-market proof reader.
Tests inject a fake opener, clock and credential loader; they never load real
credentials or make network requests.

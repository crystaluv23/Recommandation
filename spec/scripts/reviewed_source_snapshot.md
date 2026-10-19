# Reviewed source snapshot diagnostic

The local diagnostic materializes the four-record review into an independent
snapshot and freezes its explicit reviewed type/root/manifest hash in an input
manifest. Runtime restore uses the same production loader as coordinator and
worker stores. It forbids socket creation and does not execute model roles.

Checks retain 2 admitted SEC / 1 excluded polluted news / 1 unknown transcript:
exact document load/search/documents, pre-availability versus exact instant,
resolver lookup/requery and unknown DataGap, idempotent admitted replay,
rejected append/acquisition, reviewed snapshot/refresh/restart, changed proof,
missing/renamed manifest, widened root/scope and added file rejection. Original
oracle records are not changed. This is a narrow trusted-input boundary check,
not 48-case readiness or proof of Signal semantics/prediction quality.

Retained transport payloads named `*.response.raw` and `*.response-prefix.raw`
are immutable byte evidence. Git marks these suffixes binary (`-text -diff
-merge`): checkout conversion, text merging or formatting must not change their
hashes. Source-authored tabs/whitespace are not repository-authored text lint
failures. Code, documentation and JSON receipt/review records remain ordinary
linted text. A retained prefix is explicitly incomplete HTTP-body evidence,
never a full-submission hash or proof that unretained documents were read.

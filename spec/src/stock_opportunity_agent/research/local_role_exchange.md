# Independent local role exchange

This module implements the local execution boundary in
[evolution_transport](evolution_transport.md). `LocalRoleExchange.receive`
creates an immutable hash-addressed inbox after the transport has validated,
masked and budgeted the exact request. It pauses via `EvolutionControlFlow`
until an independently authored raw response and coordinator-written receipt
exist. `submit` binds actual agent identity, request, inbox bytes and raw output
bytes without changing the answer. Resume verifies all bindings before parsing.
The exchange creates its outbox directory before publishing pending work, so
the isolated role can exclusively create its raw file without filesystem setup.
Creating an empty directory does not reserve another request or author a response.
The call ceiling is persisted and cannot be increased on resume. Inbox only
contains exact model messages and output limits; no acceptance oracle is sent.

The exchange never imports a provider client or performs network I/O. Original
messages, raw responses and receipts are audit evidence, not semantic approval.
Independent agents may use only the inbox and runtime-supplied tools, with no
inherited chat or access to expected answers. Internal cost/tokens remain unknown.

## Shared admission and recovered responses

Dispatch admission is one shared-root transaction across threads, client
instances and processes: hold an OS advisory lock while checking immutable
contract, existing inbox identity and total count, then atomically publishing
the admitted inbox. A replay consumes no new slot. Pending work counts toward
the ceiling; a failed response never frees a slot. The admission lock is not
held while an independent agent executes.

Before returning any local exact-cache hit, revalidate inbox, request identity,
receipt and original raw bytes, reparse the raw answer and compare with cached
JSON and normalization. Missing/tampered originals or cache drift fail closed
without dispatch, overwrite or another role attempt. A cache hit cannot bypass
checks applied to the first response. Backend identity is explicit; actual
agent model version is unknown unless provided by authoritative tool metadata.

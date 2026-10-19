# Independent local role exchange

This module implements the local execution boundary in
[evolution_transport](evolution_transport.md). `LocalRoleExchange.receive`
creates an immutable hash-addressed inbox after the transport has validated,
masked and budgeted the exact request. It pauses via `EvolutionControlFlow`
until an independently authored raw response and coordinator-written receipt
exist. `submit` binds actual agent identity, request, inbox bytes and raw output
bytes without changing the answer. Resume verifies all bindings before parsing.
The call ceiling is persisted and cannot be increased on resume. Inbox only
contains exact model messages and output limits; no acceptance oracle is sent.

The exchange never imports a provider client or performs network I/O. Original
messages, raw responses and receipts are audit evidence, not semantic approval.
Independent agents may use only the inbox and runtime-supplied tools, with no
inherited chat or access to expected answers. Internal cost/tokens remain unknown.

# Python Runtime for Tests

visit_times: 59

## Trigger

When running Python tests, project scripts, formal cold-start pipelines, or lint-adjacent validation commands in this repository.

## Lesson

Use the project-compatible Python runtime, not macOS system `python3` and not the missing `python` shim. The repository requires Python 3.11+, and the system `python3` may be Python 3.9, which fails before tests run because existing code imports `types.UnionType`.

## Context

During cold-start implementation on 2026-05-03, `python` was not available and `python3 -m unittest discover -s tests` used Apple Python 3.9. That produced import errors from `src/stock_opportunity_agent/models.py` before any test body executed. The bundled Codex runtime at `/Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3` ran the same test suite successfully.

The issue is not a code regression in the current task when the failure mentions `ImportError: cannot import name 'UnionType' from 'types'` under Python 3.9. It is a runtime mismatch.

## How to Apply

Before running tests or project scripts, prefer:

```sh
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests
```

For project scripts, use the same runtime with `PYTHONPATH=src`, for example:

```sh
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_cold_start_formal.py --context-mode off --web-inflection-mode off --max-listings 1
```

If the bundled runtime path is unavailable, call `load_workspace_dependencies` or `install_workspace_dependencies` before falling back. Do not report system-Python import failures as product failures until the command has been retried with a Python 3.11+ runtime.

## Limits

This does not excuse real test failures under Python 3.11+. If tests fail under the bundled runtime, treat them as current-task failures unless the traceback proves otherwise.

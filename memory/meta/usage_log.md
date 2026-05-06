# Usage Log

- 2026-05-02: Trigger "adding provider, adapter, registry, or external-service integration"; read `memory/experiences/provider-boundary-placement.md` before expanding data-source capabilities so provider selection stays at the data capability boundary.
- 2026-05-03: Trigger "running Python tests and seed pipelines"; read `memory/experiences/python-runtime-for-tests.md` before extending cold-start execution so verification uses the Python 3.11+ runtime.
- 2026-05-03: Trigger "running Python tests and seed pipelines"; read `memory/experiences/python-runtime-for-tests.md` before adding inflection discovery so verification uses the bundled Python 3.11+ runtime.
- 2026-05-03: Trigger "running Python tests and seed pipelines"; read `memory/experiences/python-runtime-for-tests.md` before adding cold-start progress reporting so verification uses the bundled Python 3.11+ runtime.
- 2026-05-03: Trigger "running Python tests, scripts, seed pipelines, or validation commands"; read `memory/experiences/python-runtime-for-tests.md` before running the OpenRouter-backed cold-start seed pipeline so verification uses the bundled Python 3.11+ runtime.
# 2026-05-03

- Trigger: running the OpenRouter cold-start script and repository validation.
  Experience: `memory/experiences/python-runtime-for-tests.md`.
  Why: Reused the bundled Python 3.11+ runtime for project scripts and tests to avoid the known system-Python mismatch.
- 2026-05-06: Trigger "running the formal cold-start script and repository validation"; read `memory/experiences/python-runtime-for-tests.md` before executing the production cold-start workflow so scripts use the bundled Python 3.11+ runtime.

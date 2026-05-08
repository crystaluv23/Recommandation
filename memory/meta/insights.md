# Project Insights

- Test and script verification should use the bundled Python 3.11+ runtime with `PYTHONPATH=src`; macOS system `python3` can be Python 3.9 and fail on existing 3.11+ syntax/imports before tests execute.
- Formal cold-start work should begin by restating the execution contract and auditing the exact runner inputs/prompt JSON; existing scaffolding can hide missing packet data, identity leaks, and seed/formal entry-point drift.

Rewrite this file during future memory reviews when repeated experiences reveal stable project-specific advice.

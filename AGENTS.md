# Stock Opportunity Agent — Session Entry

Read this file first. Then read [progress/status.md](progress/status.md).
These are the bounded current entry points; historical logs are not current state.

## Product and authority

Build a long-running US stock opportunity research agent for the next 3–6 months.
Output watchlists, evidence-backed theses and review artifacts. Trading, brokerage,
leverage and position sizing require explicit user approval and top-down design.

Design authority: [vision](spec/vision.md) → [architecture](spec/architecture.md)
→ owning module specs under `spec/src/`. User instructions and existing authorized
scope persist. Read the owning spec before implementation; if a change conflicts
with an ancestor, name the conflict and obtain the corresponding decision first.
Write/update specs before code. Do not silently change research definitions,
canonical schemas, scoring, promotion policy, PIT guarantees or module interfaces.

## Work toward acceptance, not activity

For multi-step work, state the concrete problem, verifiable success criteria,
current evidence, and stopping condition before starting. At the end identify
which acceptance item advanced and at what evidence level. Tests, commits,
reports, calls, version numbers and exit0 are not themselves research progress.

Keep input credibility, correct execution, correct/consumed feedback, new capability
and reuse, and independent benefit separate. A local fix can close a local defect;
it cannot close a live-behavior or benefit requirement. Never infer economic truth
from valid citations, hashes, schema validation or a correct single prediction.

**Mandatory reflection:** read [the agent-workflow contract](spec/agent-workflow.md)
and the matching [experience index](memory/GUIDE.md) when a supposedly fixed failure
recurs, two consecutive rounds of the same strategy advance no acceptance item,
input/contract/repair authority becomes inconsistent, claim levels drift, or before
a complete paid successor/complexity expansion. During sustained work, check for
information gain about every 30 minutes; do not generate timed paperwork.

The reflection must explain why prior checks failed, inspect the entire applicable
producer/prompt/validator/typed-repair/fallback/consumer/persistence/next-cycle chain,
name the assistant's missed assumptions, and choose a changed action with a bounded
falsifiable check. Repeating “more prompts/tests/another run” is insufficient.
If the strategy stays the same, justify it with new evidence and a distinguishing
variable. Do not rename the problem or reset history to escape this rule.

Track long-running convergence in [progress/convergence.json](progress/convergence.json),
updated at substantive round/review/decision boundaries only. Before a full live
successor refresh service/run/user state, freeze inputs/code and run:

```sh
python3 scripts/check_project.py --before-successor
```

This is an administrative gate, not research validation or authorization. Check
failed prerequisites rather than edit them to obtain PASS. Approved independent
diagnostics may continue; never report them as complete-cohort acceptance.

## Runtime and evidence boundaries

- Preserve PIT, historical body versions, object/period/unit applicability, labels,
  fixed failure denominators, identity masking and Locked Test. Do not weaken Signals
  coverage, literal/whole-word/boundary validation or typed repair authority.
- Compare actual production prompts, inputs, raw responses, native corrections,
  persisted records and exact-version downstream consumption. Check the original
  defect, representative variations and counterexamples; do not mock the decisive
  production boundary. Scripted old-answer replay does not prove model compliance.
- Completed runs stay completed. Use authoritative round/cycle pointers and fresh
  service status, never old PIDs or staged artifacts. Keep code/input snapshots
  immutable and one executor serial. Recovery follows the original contract.
- Goal usage/budget limits stop that goal. Do not replace, resume or relabel it to
  evade the limit. `null` is not active. Only an actual service return to active
  under user authorization permits continuation. Separately authorized work remains
  scoped to that work; it does not resume old experiments.
- No factor/class quotas or mechanically invented research conclusions to create
  progress. Honest no-pattern is valid; limited search is not proof of absence.
- Preserve credentials outside artifacts and output. Sending/publishing/other
  external actions require the corresponding existing or explicit authorization.

## Implementation and knowledge discipline

Use minimum necessary code, explicit one-way interfaces, established style,
public docstrings and declared dependencies (`pyproject.toml` for Python).
Change only task files. Test deterministic behavior in `tests/`; judge LLM research
quality with real evidence and evaluation artifacts. Scale verification to risk.

Consult memory on a matching trigger; read only relevant entries. **No read counters,
consultation logs or bookkeeping-only commits.** Record adoption or a counterexample
only when it changes a decision. Existing `visit_times` and usage logs are history.
Repeatedly ineffective lessons must be narrowed, converted into checks or retired.
The workflow contract takes precedence over obsolete experience instructions.

Keep status short and current. Preserve detailed history in reports/changelog or
an explicitly historical archive. Don't copy stale ACTIVE/PID claims into current
status. Rules that only generate work must themselves be simplified or removed.

## End of a substantive change

Sync specs, update current status and append one meaningful changelog entry.
Record non-obvious reusable lessons/reviews only when needed. Run suitable tests
and `scripts/lint_repo.sh`; read `.lint-feedback/pre-push-last.log` after every
manual pre-push lint or push. `core.hooksPath` is `.githooks`.

Inspect `git status`, stage only this task's files and create a concise checkpoint
before the final reply whenever project files changed. Keep unrelated user edits
out. Report verification failures and limits honestly. A meta-check PASS does not
prove these rules changed future behavior; verify that at the next real trigger.

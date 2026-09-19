# Round 22 report

- round_id: fast-slow-20260919/round-22
- status: partial (starting; investigation next)
- baseline: 068ec23 (922 tests + lint accepted), round-21 partial changes preserved in working tree

## Plan

1. Read preserved round-21 changes in `evolution_research_validation.py` /
   `evolution_plan_roles.py` / tests / specs.
2. Repair probe 1: `_bounded_residual_need` must validate the parent itself
   (parent must pass the future-source guard) before granting inherited
   expectation semantics; invalid parents lend nothing.
3. Repair probe 2: remove the `date.min` surrogate from the symbolic routing
   check; use the real prediction date when available, otherwise restrict the
   check to what is provable from parent/residual bounds; ordinary historical
   residuals must remain accepted.
4. Revise round-21 tests encoding the wrong `date.min` behavior; add both
   independent counterexamples plus invalid symbolic/explicit parents, valid
   historical residual, bounded guidance residual, realized-future and
   unrelated residuals.
5. replay.py from original V123 attempts 7/8 payload (JSON-decoded), honest
   replay-vs-synthetic distinction.
6. focused / full / lint, specs + progress + changelog, then stop for review.

## Findings / results

(to be updated after investigation, implementation, testing)

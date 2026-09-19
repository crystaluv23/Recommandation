# Delegation skill repair (2026-09-19)

User requested removing hard deadlines, API progress, persisted reviewable plans, and visible handoff/progress/result summaries while Fast/Slow work continues.

Installed skill: /Users/l/.codex/skills/plan-and-delegate/SKILL.md (outside this repository's git tracking).

Implemented: no default total/idle termination; positive time limits only for explicit user budgets. Default app-server API create/subscribe/send/read/events with exact scoped hooks and isolated HOME. Incremental safe event metadata, root session ID, status snapshots every 30 seconds; raw content excluded from summaries. API task completion uses runtime session/event turn.completed/turn.failed, never idle snapshots or prompt_completed acknowledgements. Observation errors do not stop active work. Legacy prompt mode retains dedicated log feedback fallback. Each round's brief and reports persisted; user receives linked summaries before dispatch, at meaningful stages and after independent review. No default nested delegation. Progress-aware rounds within authorization; credential path default recorded, no key contents copied.

Validation: 9 offline tests passed, including preview/no mutation, completion, explicit idle/total budgets, partial/duplicate/private events, API subscribe-before-send, idle and prompt acknowledgement cannot end work, observation error cannot end work. quick_validate.py passed (PyYAML installed solely into /private/tmp/plan-delegate-skill-validation-20260919).

Real API evidence: /private/tmp/zcode-api-live-20260919-skill/report.md contains API_CHECK_OK. status file confirms runtime turn.completed, 3 model completion events, 2 tool completion events, 311 notifications, 13.1 seconds. No project files touched by this integration test. Two earlier API pilots incorrectly treated idle then prompt_completed as task completion; they ended early and produced no business changes, are not successes. Both now have regression coverage. Actual round 04 execution-03 now receives real streamed API events.

Round 03 old timeout supervisor was removed alone at user request, leaving original ZCode process alive until genuine completion. Round 03 yielded 856 tests + lint pass, but independent drift counterexample failed acceptance. Round 04 addresses that separate project issue.

Limits: event activity is not semantic progress; reports/diffs/tests still govern acceptance. Resume is not validated. App-server API cannot take over another active prompt process. Installed skill is not a git repository; the project checkpoint covers this audit record, hashes identify installed skill contents.

Installed file hashes:
- SKILL.md: 6254d34b10757d027eb892c5803a84a16e9af3a73a3070a1932e56a4808ee77c
- references/zcode.md: 42d66d20370a4b25dda1f1a8d50ed05f9485d455d1aab7ec14295f8d386a2409
- scripts/run_zcode.py: e7bc00a3050516ae1e8e4f3c1c55a220098524f7032eee4ec7daecbdfe109652
- scripts/progress_events.py: 9a47055d7afa31ffabfaa5ef9084a8174875a1b7f0d05858c25efa05162f1f71
- scripts/zcode_api.py: 68e1aaa369a325088dad869ff1527bf6a17f0f3098c19921c5c954a99128e24a
- scripts/test_run_zcode.py: 5c739d5b53968d3e0be9fd909d4418964ae4483ca4db69f3a094fadebbebe699

Revalidation: 9 offline tests passed again after duplicate/stale API-event handling update. Round05 genuinely completed with turn.completed after 1417.8 seconds, 71 model completions and 79 tool completions. No hard deadline applied. Round06 dispatched via API with both time limits 0; exec handle 10160, PID3984, session sess_dda29ec3-81b3-49bf-87dd-89568186bb86.

2026-09-20 event-order repair: actual turn completion after prompt submission is accepted even if session/send acknowledgement arrives later; that late acknowledgement cannot overwrite terminal status. 10 offline tests passed, including this ordering regression. Running round08 retains its already-loaded adapter; no active process was stopped or replaced.

Final skill-format revalidation after event-order repair: quick_validate.py returned Skill is valid. Round09 uses the updated adapter; no default execution/idle deadline.

## Round11 handoff correction
Codex omitted exact permitted commands from round11 brief; agent attempted variants denied by scope hook and reported all shell unavailable. Launcher now automatically includes exact allow-command strings in dispatched prompt, preventing this omission. Existing scope policy unchanged;10offline tests passed. No restart of active round11.

Latest launcher SHA256: efeecc17a9bfb53c77c32e1dfdb1f4522298c51174c651d870ff6600e7d1da18. Skill validator passed after exact-command handoff patch.

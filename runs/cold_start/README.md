# Cold Start Run Workspace

This directory is the clean workspace for formal cold-start runs.

Default formal run layout:

```text
runs/cold_start/
  formal/
    <run_id>/
      01_universe/
        eligible_listings.json
      02_prices/
        price_histories.json
      03_selection/
        historical_candidate_selection.json
      04_documents/
        documents_and_catalysts.json
      05_packets/
        historical_cases.json
      06_research/
        inflection_analyses.json
        blind_case_analyses.json
        pre_surge_signal_logic.json
        signal_definitions.json
        case_signal_observations.json
        theme_maps.json
        surge_research_playbooks.json
        manifest.json
  ralph/
    <run_id>/
      preflight_blind_llm_requests.json
      preflight_leakage_report.json
      preflight_manifest.json
      research_information_plan.json
      information_requirements.json
      evidence_coverage_ledger.json
      atomic_evidence_by_case.json
      raw_vs_organized_evaluation.json
      ralph_experiment_summary.json
      holdout_blind_scheme_evaluation.json
  evolution/
    evolution_dashboard.html
    evolution_dashboard_data.js
    evolution_dashboard_index.json
    <run_id>/
      config.json
      evaluation_contract.json
      state.json
      events.jsonl
      memory.json
      evolution_summary.json
      evolution_history.json
      evolution_dashboard_data.js
      evolution_dashboard.html
      top_k.json
      scheme_experiments.json
      experiment_report.json
      schemes/
      frozen_signals/
      signal_extractions/
      predictions/
      evaluations/
      prompts/
      cache/
      experiments/
```

`01_universe` through `05_packets` are pre-OpenRouter checkpoints. If LLM
research is slow or interrupted, the next run should reuse these stage outputs
rather than repeating the full universe scan. The formal runner can load an
existing universe checkpoint with `--universe-path` and an existing price
checkpoint with `--price-history-path`, while still reapplying the current
eligibility and selection logic.

`04_documents/documents_and_catalysts.json` also records web-context queries,
company/theme/research-summary documents, catalysts, per-case context coverage,
and coverage-gate exclusions. `05_packets/historical_cases.json` remains the
complete packet audit; when `--coverage-gate-mode enforce` is used, insufficient
packets are excluded from blind LLM learning but still remain in this packet
checkpoint. Use `--web-context-mode off` only when intentionally testing the
non-web context path.

`ralph/<run_id>/` stores the broad information-plan experiment and optional
preflight exports. Preflight outputs are local audit artifacts for reviewing
the anonymous no-web blind packets before an approved external LLM call. The
redundant legacy packet-scheme CLI and its separate response-import artifact
family have been removed; the broad information-plan path is the only
standalone Ralph experiment.

The Ralph information-plan runner now emits proposal artifacts for
`research_information_plan.json`, `information_requirements.json`,
`evidence_coverage_ledger.json`, `atomic_evidence_by_case.json`,
`point_in_time_source_documents.json`, `document_content_audit.json`,
`raw_source_blind_packets.json`, raw-versus-organized blind comparison,
information-family add-back/ablation, and layered failure attribution. The
point-in-time source artifact preserves the complete retrospective bodies and
can be passed back through `--documents-path` for deterministic replay. In
`--preflight-only` mode it writes packet and readiness artifacts without an
external LLM call. The repository has no human-curated gold packet; automatic
or source-audited packets must not be labeled gold.

Raw-source and organized-packet experiments must reuse the same point-in-time
source bundle, model, output contract, and documented context-budget policy.
Label-aware discovery and acquisition stay before packet masking. Blind
evaluation remains anonymous and web-disabled, and a holdout used to propose a
change becomes retrospective feedback data rather than independent validation
for that change.

Preflight must stop before blind calls when the selected holdout has no
source-backed facts, when source bodies are truncated or unusable, or when the
expanded source-alias leakage scan fails. The July 12 v5 preflight stopped on
incomplete source bodies. The July 13 v19 bounded development preflight is the
current frozen replay: 23 audited sources, 16 usable full bodies, seven
summary-only bodies, strict leakage passed, and three source-backed target
families. Its raw arm samples document chunks round-robin so one long filing
cannot consume the full context budget. Local heuristic v22 is only a pipeline
diagnostic: organized positive gap is 0.19 but FP is 1.00 because both cases are
`possible`. Do not use it as an effectiveness estimate. Sending the frozen
anonymous packets to an external provider still requires explicit informed
authorization; otherwise keep the local preflight for review and do not run the
provider-backed path.

`evolution/<run_id>/` stores the resumable A/B/C genome search. The frozen exam
uses the maximum five-day-smoothed adjusted-close multiple over six calendar
months: A below 2x, B from 2x to below 3x, and C at or above 3x. B/C are binary
positive and binary F1 is the only Top-K selection score. Model probability
fields are rejected. Initialize and run the two-generation mock config:

```sh
PYTHONPATH=src python3 scripts/evolve_information_schemes.py init \
  --config configs/evolution/mock_experiment.json
PYTHONPATH=src python3 scripts/evolve_information_schemes.py run \
  --config configs/evolution/mock_experiment.json
```

Resume or inspect the same run:

```sh
PYTHONPATH=src python3 scripts/evolve_information_schemes.py resume \
  --config configs/evolution/mock_experiment.json
PYTHONPATH=src python3 scripts/evolve_information_schemes.py status \
  --config configs/evolution/mock_experiment.json
PYTHONPATH=src python3 scripts/evolve_information_schemes.py dashboard \
  --config configs/evolution/mock_experiment.json
```

Each stock's signal extraction and A/B/C prediction is written immediately.
`resume` reuses it only when the frozen contract, fold, scheme recipe, signals,
label-free input, extraction, and evaluator settings match. Mock `final-test`
runs once on separate sealed synthetic companies; real `final-test` remains
fail-closed until a compatible one-shot A/B/C dataset and source archive are
configured. Ordinary `run` and `resume` never load those labels.

Every completed round also upserts its run-local `evolution_history.json` and
refreshes both the portable per-run page and the fixed repository-level entry:

```text
runs/cold_start/evolution/evolution_dashboard.html
```

Open that same HTML for every run and round; it needs no server or network
access. Its run selector reads the generated local index and defaults to the
most recently completed run. The chart uses round on the x-axis and binary F1
on the y-axis. Candidate points and their per-round median show the stochastic
sequence, while the retained archive-best line is shown separately because
Top-K makes it non-decreasing by construction. The `dashboard` command rebuilds
the unified page from direct child run records, and `status` refreshes it before
printing state. A legacy run can recover only its last fully representable
round; the page labels that limitation instead of inventing missing history.

The executable plotting and run-selection logic lives in the HTML. Because a
browser opening `file://` cannot enumerate directories or fetch arbitrary JSON,
the loop atomically refreshes the adjacent `evolution_dashboard_data.js` from
the canonical local JSON histories after every round. Reopening the one HTML or
clicking reload therefore reads the latest generated local index.

Run on saved Ralph cases only with a compatible adjusted-close history. Legacy
winner/control or terminal-return labels are rejected rather than silently
treated as the new maximum-multiple contract:

```sh
PYTHONPATH=src python3 scripts/evolve_information_schemes.py run \
  --mode heuristic \
  --price-histories-path <run>/02_prices/price_histories.json \
  --resume \
  --output-dir runs/cold_start/evolution/codex-v1-real-heuristic
```

After reviewing the exact persisted `packet_preflight/` payloads, an explicitly
authorized first external run should remain one candidate, one concurrent
request, and one bounded generation:

```sh
PYTHONPATH=src python3 scripts/evolve_information_schemes.py run \
  --mode llm \
  --openrouter-model openai/gpt-5.5 \
  --openrouter-provider openai \
  --children-per-generation 1 \
  --max-candidates 1 \
  --max-concurrency 1 \
  --max-api-cost 10 \
  --input-cost-per-million-tokens 5 \
  --output-cost-per-million-tokens 30 \
  --blind-cache-dir runs/cold_start/evolution/shared-blind-cache \
  --price-histories-path <run>/02_prices/price_histories.json \
  --resume \
  --output-dir runs/cold_start/evolution/codex-v1-llm
```

Provider availability and pricing are time-varying and must be refreshed before
a real run. The command requires `OPENROUTER_API_KEY`; no credential is written
to artifacts. Synthetic and heuristic runs are pipeline diagnostics only. A
real effectiveness claim still requires an explicitly declared untouched-
company final test after proposal changes stop.

The generated run directories are ignored by git. Keep durable lessons in
`memory/`, durable design in `spec/`, and only commit code or documentation
changes.

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
      ralph_experiment_summary.json
      holdout_blind_scheme_evaluation.json
      imported_response_manifest.json
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

`ralph/<run_id>/` stores standalone Ralph Loop refinement/holdout experiments
and optional preflight exports. Preflight outputs are local audit artifacts for
reviewing the anonymous no-web blind packets before an approved external LLM
call. If responses are generated outside this runtime, the runner can import
them by request id and write imported-response evaluation artifacts in the same
run directory.

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
authorization; otherwise keep the local preflight for response export/import.

The generated run directories are ignored by git. Keep durable lessons in
`memory/`, durable design in `spec/`, and only commit code or documentation
changes.

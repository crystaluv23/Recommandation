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
call.

The generated run directories are ignored by git. Keep durable lessons in
`memory/`, durable design in `spec/`, and only commit code or documentation
changes.

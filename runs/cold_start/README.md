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
        manifest.json
```

`01_universe` through `05_packets` are pre-OpenRouter checkpoints. If LLM
research is slow or interrupted, the next run should reuse these stage outputs
rather than repeating the full universe scan.

The generated run directories are ignored by git. Keep durable lessons in
`memory/`, durable design in `spec/`, and only commit code or documentation
changes.

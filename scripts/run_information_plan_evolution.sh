#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
CLI="$PROJECT_ROOT/scripts/evolve_information_schemes.py"
BUNDLED_PYTHON="/Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"

usage() {
  printf '%s\n' \
    "Usage:" \
    "  bash scripts/run_information_plan_evolution.sh new [options]" \
    "  bash scripts/run_information_plan_evolution.sh resume [options]" \
    "" \
    "Common required options:" \
    "  --workspace PATH           evolution workspace" \
    "  --raw-info-root PATH       global append-only Raw Info oracle" \
    "  --approved-dataset PATH    reviewed, human-approved dataset manifest" \
    "" \
    "new also requires:" \
    "  --run-id ID" \
    "  --judge-model ALIAS" \
    "  --evolution-model ALIAS" \
    "" \
    "new tuning options:" \
    "  --plan-rounds N            Fast rounds per Signal cycle (default: 2)" \
    "  --candidates-per-round N   independent Plans per round (default: 3)" \
    "  --parent-selection-seed N  deterministic exploration seed (default: 42)" \
    "  --max-external-attempts N  frozen LLM attempt ceiling (default: 2500)" \
    "  --max-total-cost USD       frozen cumulative cost ceiling (default: 100)" \
    "  --data-external            enable a bounded data policy in the contract" \
    "  --data-provider NAME       allowed provider; repeat as needed" \
    "  --data-capability NAME     allowed capability; repeat as needed" \
    "  --data-source-type NAME    allowed source type; repeat as needed" \
    "  --max-data-requests-per-cycle N" \
    "  --max-data-requests-per-run N" \
    "" \
    "resume tuning options:" \
    "  --max-cycles N             cycles this invocation; 0 means until Ctrl+C" \
    "                              (default: 1)" \
    "  --external                 permit LLM calls under the frozen contract" \
    "  --data-external            permit calls allowed by the frozen data policy" \
    "  --acknowledge-contract-hash SHA256" \
    "                              required with --external and must match" \
    "" \
    "Safety:" \
    "  new never performs external calls. It freezes a v4 contract and stops" \
    "  at the first exact-request approval boundary. Use resume with the printed" \
    "  contract hash to authorize execution. Locked Test stays sealed and Signal" \
    "  machine-validated Signal candidates auto-promote atomically at each cycle boundary."
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 2
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

MODE="${1:-}"
if [ "$MODE" != "new" ] && [ "$MODE" != "resume" ]; then
  usage >&2
  exit 2
fi
shift

WORKSPACE=""
RAW_INFO_ROOT=""
APPROVED_DATASET=""
RUN_ID=""
JUDGE_MODEL=""
EVOLUTION_MODEL=""
PLAN_ROUNDS=2
CANDIDATES_PER_ROUND=3
PARENT_SELECTION_SEED=42
MAX_EXTERNAL_ATTEMPTS=2500
MAX_TOTAL_COST=100
MAX_CYCLES=1
ALLOW_EXTERNAL=0
ALLOW_DATA_EXTERNAL=0
DATA_PROVIDERS=()
DATA_CAPABILITIES=()
DATA_SOURCE_TYPES=()
MAX_DATA_REQUESTS_PER_CYCLE=0
MAX_DATA_REQUESTS_PER_RUN=0
ACKNOWLEDGED_CONTRACT_HASH=""
NEW_ONLY_OPTION_SEEN=0
RESUME_ONLY_OPTION_SEEN=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace|--raw-info-root|--approved-dataset|--run-id|--judge-model|--evolution-model|--plan-rounds|--candidates-per-round|--parent-selection-seed|--max-external-attempts|--max-total-cost|--max-data-requests-per-cycle|--max-data-requests-per-run|--max-cycles|--acknowledge-contract-hash)
      [ "$#" -ge 2 ] || fail "$1 requires a value"
      case "$1" in
        --workspace) WORKSPACE="$2" ;;
        --raw-info-root) RAW_INFO_ROOT="$2" ;;
        --approved-dataset) APPROVED_DATASET="$2" ;;
        --run-id) RUN_ID="$2"; NEW_ONLY_OPTION_SEEN=1 ;;
        --judge-model) JUDGE_MODEL="$2"; NEW_ONLY_OPTION_SEEN=1 ;;
        --evolution-model) EVOLUTION_MODEL="$2"; NEW_ONLY_OPTION_SEEN=1 ;;
        --plan-rounds) PLAN_ROUNDS="$2"; NEW_ONLY_OPTION_SEEN=1 ;;
        --candidates-per-round) CANDIDATES_PER_ROUND="$2"; NEW_ONLY_OPTION_SEEN=1 ;;
        --parent-selection-seed) PARENT_SELECTION_SEED="$2"; NEW_ONLY_OPTION_SEEN=1 ;;
        --max-external-attempts) MAX_EXTERNAL_ATTEMPTS="$2"; NEW_ONLY_OPTION_SEEN=1 ;;
        --max-total-cost) MAX_TOTAL_COST="$2"; NEW_ONLY_OPTION_SEEN=1 ;;
        --max-data-requests-per-cycle) MAX_DATA_REQUESTS_PER_CYCLE="$2"; NEW_ONLY_OPTION_SEEN=1 ;;
        --max-data-requests-per-run) MAX_DATA_REQUESTS_PER_RUN="$2"; NEW_ONLY_OPTION_SEEN=1 ;;
        --max-cycles) MAX_CYCLES="$2"; RESUME_ONLY_OPTION_SEEN=1 ;;
        --acknowledge-contract-hash) ACKNOWLEDGED_CONTRACT_HASH="$2"; RESUME_ONLY_OPTION_SEEN=1 ;;
      esac
      shift 2
      ;;
    --data-provider|--data-capability|--data-source-type)
      [ "$#" -ge 2 ] || fail "$1 requires a value"
      case "$1" in
        --data-provider) DATA_PROVIDERS+=("$2") ;;
        --data-capability) DATA_CAPABILITIES+=("$2") ;;
        --data-source-type) DATA_SOURCE_TYPES+=("$2") ;;
      esac
      NEW_ONLY_OPTION_SEEN=1
      shift 2
      ;;
    --external)
      ALLOW_EXTERNAL=1
      RESUME_ONLY_OPTION_SEEN=1
      shift
      ;;
    --data-external)
      ALLOW_DATA_EXTERNAL=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
done

[ -n "$WORKSPACE" ] || fail "--workspace is required"
[ -n "$RAW_INFO_ROOT" ] || fail "--raw-info-root is required"
[ -n "$APPROVED_DATASET" ] || fail "--approved-dataset is required"
[ -f "$APPROVED_DATASET" ] || fail "approved dataset is missing: $APPROVED_DATASET"

if [ -n "${EVOLUTION_PYTHON:-}" ]; then
  PYTHON_BIN="$EVOLUTION_PYTHON"
elif [ -x "$BUNDLED_PYTHON" ]; then
  PYTHON_BIN="$BUNDLED_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  fail "Python 3.11+ is required"
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  fail "Python 3.11+ is required; set EVOLUTION_PYTHON to a compatible executable"
fi

run_cli() {
  PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON_BIN" "$CLI" "$@"
}

CONTRACT_PATH="$WORKSPACE/run_contract.json"

if [ "$MODE" = "new" ]; then
  [ -n "$RUN_ID" ] || fail "new requires --run-id"
  [ -n "$JUDGE_MODEL" ] || fail "new requires --judge-model"
  [ -n "$EVOLUTION_MODEL" ] || fail "new requires --evolution-model"
  [ "$RESUME_ONLY_OPTION_SEEN" -eq 0 ] || fail "new is always zero-network; resume-only options are not accepted"
  [ ! -e "$WORKSPACE" ] || fail "new requires an unused workspace"
  [[ "$PLAN_ROUNDS" =~ ^[1-9][0-9]*$ ]] || fail "--plan-rounds must be a positive integer"
  [[ "$CANDIDATES_PER_ROUND" =~ ^[1-9][0-9]*$ ]] || fail "--candidates-per-round must be a positive integer"
  [[ "$PARENT_SELECTION_SEED" =~ ^-?[0-9]+$ ]] || fail "--parent-selection-seed must be an integer"
  [[ "$MAX_EXTERNAL_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || fail "--max-external-attempts must be a positive integer"
  "$PYTHON_BIN" -c \
    'import math,sys; value=float(sys.argv[1]); raise SystemExit(0 if math.isfinite(value) and value > 0 else 1)' \
    "$MAX_TOTAL_COST" || fail "--max-total-cost must be positive"
  if [ "$ALLOW_DATA_EXTERNAL" -eq 1 ]; then
    [ "${#DATA_PROVIDERS[@]}" -gt 0 ] || fail "--data-external requires --data-provider"
    [ "${#DATA_CAPABILITIES[@]}" -gt 0 ] || fail "--data-external requires --data-capability"
    [ "${#DATA_SOURCE_TYPES[@]}" -gt 0 ] || fail "--data-external requires --data-source-type"
    [[ "$MAX_DATA_REQUESTS_PER_CYCLE" =~ ^[1-9][0-9]*$ ]] || fail "--data-external requires a positive --max-data-requests-per-cycle"
    [[ "$MAX_DATA_REQUESTS_PER_RUN" =~ ^[1-9][0-9]*$ ]] || fail "--data-external requires a positive --max-data-requests-per-run"
  elif [ "${#DATA_PROVIDERS[@]}" -gt 0 ] || [ "${#DATA_CAPABILITIES[@]}" -gt 0 ] || [ "${#DATA_SOURCE_TYPES[@]}" -gt 0 ] || [ "$MAX_DATA_REQUESTS_PER_CYCLE" != "0" ] || [ "$MAX_DATA_REQUESTS_PER_RUN" != "0" ]; then
    fail "data policy options require --data-external"
  fi

  run_cli init \
    --workspace "$WORKSPACE" \
    --raw-info-root "$RAW_INFO_ROOT"
  FREEZE_ARGS=(
    freeze-run
    --workspace "$WORKSPACE"
    --raw-info-root "$RAW_INFO_ROOT"
    --approved-dataset "$APPROVED_DATASET"
    --run-id "$RUN_ID"
    --judge-model "$JUDGE_MODEL"
    --evolution-model "$EVOLUTION_MODEL"
    --plan-rounds "$PLAN_ROUNDS"
    --candidates-per-round "$CANDIDATES_PER_ROUND"
    --parent-selection-seed "$PARENT_SELECTION_SEED"
    --max-external-attempts "$MAX_EXTERNAL_ATTEMPTS"
    --max-total-cost "$MAX_TOTAL_COST"
  )
  if [ "$ALLOW_DATA_EXTERNAL" -eq 1 ]; then
    FREEZE_ARGS+=(
      --data-external
      --max-data-requests-per-cycle "$MAX_DATA_REQUESTS_PER_CYCLE"
      --max-data-requests-per-run "$MAX_DATA_REQUESTS_PER_RUN"
    )
    for item in "${DATA_PROVIDERS[@]}"; do FREEZE_ARGS+=(--data-provider "$item"); done
    for item in "${DATA_CAPABILITIES[@]}"; do FREEZE_ARGS+=(--data-capability "$item"); done
    for item in "${DATA_SOURCE_TYPES[@]}"; do FREEZE_ARGS+=(--data-source-type "$item"); done
  fi
  run_cli "${FREEZE_ARGS[@]}"

  CONTRACT_HASH="$(
    "$PYTHON_BIN" -c \
      'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["contract_hash"])' \
      "$CONTRACT_PATH"
  )"
  printf 'Frozen contract hash: %s\n' "$CONTRACT_HASH"
  run_cli run-cycle \
    --workspace "$WORKSPACE" \
    --raw-info-root "$RAW_INFO_ROOT" \
    --approved-dataset "$APPROVED_DATASET"
  exit 0
fi

[ "$NEW_ONLY_OPTION_SEEN" -eq 0 ] || fail "resume uses frozen settings; new-only options cannot change them"
[ -f "$CONTRACT_PATH" ] || fail "resume requires an existing frozen contract"
[[ "$MAX_CYCLES" =~ ^[0-9]+$ ]] || fail "--max-cycles must be a non-negative integer"
[ "$ALLOW_EXTERNAL" -eq 1 ] || [ -z "$ACKNOWLEDGED_CONTRACT_HASH" ] || fail "--acknowledge-contract-hash requires --external"
CONTRACT_INFO="$(
  "$PYTHON_BIN" -c \
    'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print(data["contract"]["schema_version"] + " " + data["contract_hash"])' \
    "$CONTRACT_PATH"
)"
CONTRACT_SCHEMA="${CONTRACT_INFO%% *}"
CONTRACT_HASH="${CONTRACT_INFO#* }"
[ "$CONTRACT_SCHEMA" = "evolution-run-contract-v4" ] || fail "legacy contracts are read-only"

RUN_ARGS=(
  run-loop
  --workspace "$WORKSPACE"
  --raw-info-root "$RAW_INFO_ROOT"
  --approved-dataset "$APPROVED_DATASET"
  --max-cycles "$MAX_CYCLES"
)
if [ "$ALLOW_EXTERNAL" -eq 1 ]; then
  [ -n "$ACKNOWLEDGED_CONTRACT_HASH" ] || fail "--external requires --acknowledge-contract-hash"
  [ "$ACKNOWLEDGED_CONTRACT_HASH" = "$CONTRACT_HASH" ] || fail "acknowledged hash does not match the frozen contract"
  RUN_ARGS+=(--external --acknowledge-contract-hash "$ACKNOWLEDGED_CONTRACT_HASH")
fi
if [ "$ALLOW_DATA_EXTERNAL" -eq 1 ]; then
  RUN_ARGS+=(--data-external)
fi

printf 'Resuming contract hash: %s\n' "$CONTRACT_HASH"
run_cli "${RUN_ARGS[@]}"

#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
CLI="$PROJECT_ROOT/scripts/evolve_information_schemes.py"
BUNDLED_PYTHON="/Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
WORKSPACE="$PROJECT_ROOT/runs/cold_start/evolution/deepseek-v4-flash-overnight-v1"
PROPOSAL="$WORKSPACE/dataset_proposal/dataset_manifest.proposal.json"
APPROVED_DATASET="$WORKSPACE/dataset_proposal/dataset_manifest.approved.json"
RUN_ID="deepseek-v4-flash-overnight-v1"
MODEL_ALIAS="deepseek-v4-flash"
PLAN_ROUNDS=2
CANDIDATES_PER_ROUND=2
MAX_EXTERNAL_ATTEMPTS=10000
MAX_TOTAL_COST=30
OVERNIGHT_HOURS="${EVOLUTION_OVERNIGHT_HOURS:-10}"

usage() {
  printf '%s\n' \
    "Usage: bash scripts/run_deepseek_evolution.sh" \
    "" \
    "Prepare and run the current information-plan evolution loop with" \
    "DeepSeek V4 Flash for one unattended, wall-clock-bounded session." \
    "" \
    "Defaults:" \
    "  duration:                 10 hours" \
    "  plan rounds per cycle:    2" \
    "  candidates per round:     2" \
    "  external attempt ceiling: 10000" \
    "  total cost ceiling:        USD 30" \
    "" \
    "Set EVOLUTION_OVERNIGHT_HOURS to a positive integer to change only" \
    "the wall-clock duration, for example:" \
    "  EVOLUTION_OVERNIGHT_HOURS=12 bash scripts/run_deepseek_evolution.sh" \
    "" \
    "The script asks for the API key if needed and requires one confirmation" \
    "before dataset approval or any external call. It never opens Locked Test" \
    "or promotes staged Signal candidates."
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi
if [ "$#" -ne 0 ]; then
  usage >&2
  exit 2
fi

if ! [[ "$OVERNIGHT_HOURS" =~ ^[1-9][0-9]*$ ]]; then
  fail "EVOLUTION_OVERNIGHT_HOURS must be a positive integer"
fi

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

if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  if [ ! -t 0 ]; then
    fail "DEEPSEEK_API_KEY is unset and no interactive terminal is available"
  fi
  IFS= read -r -s -p "请输入 DEEPSEEK_API_KEY（不会显示或写入文件）: " DEEPSEEK_API_KEY
  printf '\n'
fi
if [ -z "$DEEPSEEK_API_KEY" ]; then
  fail "DEEPSEEK_API_KEY cannot be empty"
fi
export DEEPSEEK_API_KEY

REVIEWER="${EVOLUTION_REVIEWER:-$(git -C "$PROJECT_ROOT" config --get user.name 2>/dev/null || true)}"
if [ -z "$REVIEWER" ]; then
  IFS= read -r -p "请输入数据集批准人名称: " REVIEWER
fi
if [ -z "$REVIEWER" ]; then
  fail "a non-empty reviewer name is required"
fi

printf '%s\n' \
  "" \
  "[1/4] 本地预检与数据准备（零外部调用）" \
  "workspace: $WORKSPACE"

run_cli preflight-local \
  --workspace "$WORKSPACE" \
  --judge-model "$MODEL_ALIAS" \
  --evolution-model "$MODEL_ALIAS"

run_cli migrate-raw-info --workspace "$WORKSPACE"

PREPARE_RESULT="$(run_cli prepare-dataset --workspace "$WORKSPACE")"
printf '%s\n' "$PREPARE_RESULT"
[ -f "$PROPOSAL" ] || fail "dataset proposal was not created: $PROPOSAL"

PROPOSAL_HASH="$(
  "$PYTHON_BIN" -c \
    'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' \
    "$PROPOSAL"
)"

printf '%s\n' \
  "" \
  "即将启动一次无干扰 DeepSeek 夜间运行：" \
  "  数据：当前脚本默认历史开发集（不是待审核的 expanded v7）" \
  "  proposal: $PROPOSAL" \
  "  proposal hash: $PROPOSAL_HASH" \
  "  model: $MODEL_ALIAS（方案生成与盲评）" \
  "  duration: $OVERNIGHT_HOURS hours" \
  "  plan rounds/cycle: $PLAN_ROUNDS" \
  "  candidates/round: $CANDIDATES_PER_ROUND" \
  "  attempt ceiling: $MAX_EXTERNAL_ATTEMPTS" \
  "  cumulative cost ceiling: USD $MAX_TOTAL_COST" \
  "  reviewer: $REVIEWER" \
  "  Locked Test: sealed" \
  "  Signal candidates: staged only, never auto-promoted" \
  "" \
  "确认后，脚本将不再询问并可能持续产生 API 费用。"

if [ ! -t 0 ]; then
  fail "an interactive terminal is required for the execution confirmation"
fi
IFS= read -r -p "输入 RUN-DEEPSEEK-OVERNIGHT 继续: " CONFIRMATION
if [ "$CONFIRMATION" != "RUN-DEEPSEEK-OVERNIGHT" ]; then
  printf '%s\n' "未确认；没有批准数据集，也没有发起外部调用。"
  exit 0
fi

printf '%s\n' "" "[2/4] 批准精确数据集并冻结运行合同"
if [ ! -f "$APPROVED_DATASET" ]; then
  run_cli approve-dataset \
    --proposal "$PROPOSAL" \
    --proposal-hash "$PROPOSAL_HASH" \
    --approved-by "$REVIEWER"
else
  printf '%s\n' "复用现有已批准数据集: $APPROVED_DATASET"
fi

run_cli freeze-run \
  --workspace "$WORKSPACE" \
  --approved-dataset "$APPROVED_DATASET" \
  --run-id "$RUN_ID" \
  --judge-model "$MODEL_ALIAS" \
  --evolution-model "$MODEL_ALIAS" \
  --plan-rounds "$PLAN_ROUNDS" \
  --candidates-per-round "$CANDIDATES_PER_ROUND" \
  --max-external-attempts "$MAX_EXTERNAL_ATTEMPTS" \
  --max-total-cost "$MAX_TOTAL_COST"

CONTRACT="$WORKSPACE/run_contract.json"
[ -f "$CONTRACT" ] || fail "run contract was not created: $CONTRACT"
CONTRACT_HASH="$(
  "$PYTHON_BIN" -c \
    'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["contract_hash"])' \
    "$CONTRACT"
)"

printf '%s\n' "" "[3/4] 生成并校验首个精确请求（零外部调用）"
run_cli run-cycle \
  --workspace "$WORKSPACE" \
  --approved-dataset "$APPROVED_DATASET"

printf '%s\n' \
  "" \
  "[4/4] 开始 DeepSeek 夜间循环" \
  "contract hash: $CONTRACT_HASH" \
  "到时后脚本会发送 SIGINT，让 Python 在安全边界记录可恢复状态。" \
  "也可以随时按 Ctrl+C；以后重新执行本脚本会复用已提交进度。"

DURATION_SECONDS=$((OVERNIGHT_HOURS * 3600))
RUNNER_PID=""
WATCHDOG_PID=""

forward_interrupt() {
  if [ -n "$RUNNER_PID" ] && kill -0 "$RUNNER_PID" 2>/dev/null; then
    kill -INT "$RUNNER_PID" 2>/dev/null || true
  fi
}

cleanup() {
  if [ -n "$WATCHDOG_PID" ] && kill -0 "$WATCHDOG_PID" 2>/dev/null; then
    kill "$WATCHDOG_PID" 2>/dev/null || true
    wait "$WATCHDOG_PID" 2>/dev/null || true
  fi
}

trap forward_interrupt INT TERM
trap cleanup EXIT

PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON_BIN" "$CLI" run-loop \
  --workspace "$WORKSPACE" \
  --approved-dataset "$APPROVED_DATASET" \
  --external \
  --acknowledge-contract-hash "$CONTRACT_HASH" \
  --max-cycles 0 &
RUNNER_PID=$!

"$PYTHON_BIN" -c \
  'import os,signal,sys,time; time.sleep(int(sys.argv[2])); print("夜间时限已到，正在请求安全停止。", flush=True); os.kill(int(sys.argv[1]), signal.SIGINT)' \
  "$RUNNER_PID" "$DURATION_SECONDS" &
WATCHDOG_PID=$!

set +e
wait "$RUNNER_PID"
RUN_STATUS=$?
set -e
RUNNER_PID=""

if [ "$RUN_STATUS" -eq 0 ] || [ "$RUN_STATUS" -eq 130 ]; then
  printf '%s\n' \
    "DeepSeek 夜间运行已停止；已提交进度可恢复。" \
    "workspace: $WORKSPACE" \
    "dashboard: $PROJECT_ROOT/runs/cold_start/evolution/evolution_dashboard.html"
  exit 0
fi

fail "evolution runner exited with status $RUN_STATUS"

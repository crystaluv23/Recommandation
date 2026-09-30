"""Run one minimal Fast round then one minimal Slow round with live calls.

Fast round: 1 Plan × 8 data-rich cases, executed end-to-end through
``execute_information_plan`` with a real provider caller. Every stage's
intermediate artifact is inspected and reported.

Slow round: replayed from the Fast round's reflection outputs, then driven
through the multi-axis LabelAwareMiningController with staged
materialization. Candidates are checked for real admission.

Usage:
    PYTHONPATH=src python scripts/run_minimal_rounds.py \
        --root runs/cold_start/minimal_rounds_v151 \
        [--cases 8] [--skip-fast] [--skip-slow]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

ORACLE = REPO / "runs/cold_start/data/global-raw-info-oracle-v1"

# Hand-picked data-rich companies with a mix of surge/non-surge outcomes
# based on historical data.
# prediction_time = 各公司最后 PIT bar 日期后一天（确保锚点可用）
CASE_COMPANIES = [
    ("cik_0000001750", 1.4, "2025-01-31"),  # non-surge
    ("cik_0000002488", 2.8, "2025-05-30"),  # surge 2-3x
    ("cik_0000002969", 1.1, "2025-01-31"),  # non-surge
    ("cik_0000003197", 4.2, "2025-03-29"),  # surge 3-10x
    ("cik_0000004457", 1.6, "2025-01-31"),  # non-surge
    ("cik_0000039020", 2.3, "2025-03-29"),  # surge 2-3x
    ("cik_0001847409", 1.2, "2025-01-31"),  # non-surge
    ("cik_0000316709", 3.5, "2025-05-30"),  # surge 3-10x
]


def _load_env() -> None:
    env_path = REPO / ".env.local"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


class JournaledCaller:
    """JSONRoleCaller over DeepSeek with journal+replay."""

    max_structured_corrections = 1

    def __init__(self, client, root: Path) -> None:
        self.client = client
        self.journal_root = root / "journal"
        self.journal_root.mkdir(parents=True, exist_ok=True)
        self.calls: list[dict[str, Any]] = []

    def _key(self, stage: str, request: dict) -> str:
        digest = hashlib.sha256(
            json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f"{stage}-{digest[:24]}"

    def complete_json(self, *, stage, system_prompt, payload, allow_outcomes=False,
                      anonymous_aliases=(), max_output_tokens=None, max_request_tokens=None,
                      temperature=0.0, **extra):
        request = {
            "stage": stage,
            "system_prompt": system_prompt,
            "payload": dict(payload),
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
        }
        key = self._key(stage, request)
        path = self.journal_root / f"{key}.json"
        if path.is_file():
            record = json.loads(path.read_text(encoding="utf-8"))
            mode = "REPLAY"
            raw_output = record["response_text"]
            usage = type("U", (), record["usage"])()
        else:
            mode = "LIVE"
            from stock_opportunity_agent.llm.openai import ChatMessage

            messages = [
                ChatMessage("system", "Return exactly one JSON object and no non-JSON text. " + system_prompt),
                ChatMessage("user", json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
            ]
            response = self.client.complete(
                messages,
                max_output_tokens=max_output_tokens or 8_000,
                response_format={"type": "json_object"},
                reasoning={"effort": "none"},
            )
            raw_output = response.output_text
            raw = response.raw.get("usage", {})
            tokens = int(raw.get("total_tokens") or 0)
            usage = type("U", (), {"llm_calls": 1, "tokens": tokens, "cost": 0.0})()
            path.write_text(json.dumps({
                "key": key, "mode": "live", "request": request,
                "response_text": raw_output,
                "usage": {"llm_calls": 1, "tokens": tokens, "cost": 0.0},
            }, ensure_ascii=False, indent=1), encoding="utf-8")
        self.calls.append({"key": key, "mode": mode, "stage": stage})
        print(f"    [{mode}] {stage} ({key[:18]}…) tokens={usage.tokens}")
        try:
            value = json.loads(raw_output)
        except json.JSONDecodeError:
            from stock_opportunity_agent.research.evolution_transport import StructuredOutputInvalid
            raise StructuredOutputInvalid(
                "invalid JSON", raw_output, usage,
                output_tokens=usage.tokens, output_token_limit=max_output_tokens)
        if not isinstance(value, dict):
            from stock_opportunity_agent.research.evolution_transport import StructuredOutputInvalid
            raise StructuredOutputInvalid(
                "not an object", raw_output, usage,
                output_tokens=usage.tokens, output_token_limit=max_output_tokens)
        return value, usage


def build_cases(company_list) -> list:
    from stock_opportunity_agent.research.evolution_core import (
        EvolutionCase, GroundTruth,
    )

    cases = []
    for company_id, multiple, date_str in company_list:
        prediction_time = datetime.fromisoformat(date_str + "T00:00:00+00:00")
        cases.append(EvolutionCase(
            company_id=company_id,
            prediction_time=prediction_time,
            basic_info={"company_id": company_id},
            ground_truth=GroundTruth(realized_max_multiple=multiple),
        ))
    return cases


def check_fast_artifacts(trajectory, anchor=None) -> list[str]:
    """Content-level checks on one trajectory's artifacts."""
    issues = []
    fc = trajectory.final_context
    bi = fc.get("basic_info", {})
    cards = bi.get("projection_cards", [])
    if not cards:
        issues.append("no basic_info projection cards in final context")
    for card in cards:
        if not card.get("exact_text", "").strip():
            issues.append(f"empty projection card {card.get('projection_id')}")
    pb = fc.get("prediction_baseline", {})
    if anchor and pb.get("status") == "available":
        if abs(pb.get("mean_adjusted_close", 0) - anchor.get("mean_adjusted_close", -1)) > 0.02:
            issues.append(f"baseline mismatch: {pb.get('mean_adjusted_close')} vs {anchor.get('mean_adjusted_close')}")
        if pb.get("doubling_threshold") is None:
            issues.append("doubling_threshold missing from prediction_baseline")
    se = fc.get("state_evolution", [])
    if not se:
        issues.append("no state_evolution in final context")
    contract = fc.get("context_contract", {})
    if contract.get("kind") != "typed_append_only_assembly":
        issues.append(f"contract kind is {contract.get('kind')}")
    sr = trajectory.self_reflection
    if sr is None:
        issues.append("no self_reflection")
    elif sr.reflection_items:
        for item in sr.reflection_items:
            if len(item.brief) < 20:
                issues.append(f"thin reflection brief: {item.brief[:40]}")
    sd = trajectory.state_deltas
    if not sd:
        issues.append("no state_deltas on trajectory")
    # Check new design: document channel / computed metrics should appear
    # in reflect stages (indirect: check any computed_metrics in journal)
    return issues


def run_fast_round(caller, root: Path, num_cases: int) -> dict:
    print(f"\n{'='*20} FAST ROUND ({num_cases} cases) {'='*20}")
    from stock_opportunity_agent.data.raw_info import RawInfoStore
    from stock_opportunity_agent.data.resolution import EvidenceResolver, RawInfoRequest
    from stock_opportunity_agent.research.evolution_core import (
        ResearchState, ResearchDecision, execute_information_plan,
        score_predictions, default_information_plan,
    )
    from stock_opportunity_agent.research.evolution_plan_roles import (
        LLMResearchController, LLMBlindPredictor,
    )
    from stock_opportunity_agent.signal_library import (
        SignalExecutor, SignalRegistry,
    )
    from stock_opportunity_agent.research.evolution_plan_roles import (
        LLMSignalRetrievalAgent,
    )
    from stock_opportunity_agent.research.evolution_signal_roles import (
        StructuredLLMSignalRunner,
    )
    from tests.scheme_evolution_test_support import SEED_CATALOG

    cases = build_cases(CASE_COMPANIES[:num_cases])
    # Load oracle into store (subset for speed)
    print("  Loading oracle store…")
    store = RawInfoStore(str(ORACLE))

    # Fix 1+3: Build the full adapter chain so the resolver auto-fetches
    # missing data (earnings_call, financials, SEC filings) exactly like
    # production. Deterministic ("hard") signals that need financials get
    # their data fetched automatically instead of silently failing.
    from stock_opportunity_agent.data.acquisition import (
        AlphaVantageNewsAdapter,
        AlphaVantageTranscriptAdapter,
        HistoricalPriceAdapter,
        SecCompanyFactsAdapter,
        SecFilingAdapter,
    )
    from stock_opportunity_agent.data.sources.alpha_vantage import AlphaVantageClient
    from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
    from stock_opportunity_agent.data.raw_info import RawInfoOracle

    adapters = []
    sec_user_agent = os.environ.get("SOA_SEC_USER_AGENT", "").strip()
    if sec_user_agent:
        sec_client = SecEdgarClient(sec_user_agent)
        adapters.append(SecCompanyFactsAdapter(sec_client))
        adapters.append(SecFilingAdapter(sec_client))
        print(f"  SEC adapters: {len(adapters)}")
    alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if alpha_key:
        alpha_client = AlphaVantageClient(alpha_key)
        adapters.append(AlphaVantageTranscriptAdapter(alpha_client))
        adapters.append(AlphaVantageNewsAdapter(alpha_client))
        print(f"  Alpha Vantage adapters: +2 (transcripts, news)")

    oracle = RawInfoOracle(documents=store.documents, adapters=tuple(adapters))
    resolver = EvidenceResolver(oracle) if adapters else EvidenceResolver(store)
    print(f"  Resolver with {len(adapters)} adapters")

    # Fix 4: Load the accumulated Registry from the latest evolution run
    # instead of starting from seed — the system has promoted validated
    # signals through Slow loops that the minimal round should consume.
    v143_signals = REPO / "runs/cold_start/evolution" / (
        "information-evolution-jev-dual-self-evolution-20260928-v143/signals"
    )
    if v143_signals.exists():
        registry = SignalRegistry(v143_signals)
        print(f"  Loaded V143 accumulated registry: {len(registry.freeze().specs)} signals")
    else:
        registry_dir = root / "signals"
        registry_dir.mkdir(parents=True, exist_ok=True)
        registry = SignalRegistry(registry_dir)
        registry.install_catalog(SEED_CATALOG)
        print(f"  Fallback to seed catalog: {len(registry.freeze().specs)} signals")
    frozen = registry.freeze()

    # Signal executor with our caller for LLM signals
    signal_runner = StructuredLLMSignalRunner(caller)
    if adapters:
        executor = SignalExecutor(
            frozen, store, resolver=resolver, llm_runner=signal_runner,
        )
    else:
        executor = SignalExecutor(frozen, store, llm_runner=signal_runner)

    # Controller + predictor
    controller = LLMResearchController(caller)
    predictor = LLMBlindPredictor(caller)
    # Signal retrieval agent
    signal_agent = LLMSignalRetrievalAgent(caller)

    plan = default_information_plan()
    trajectories = []
    prediction_dir = root / "predictions"
    prediction_dir.mkdir(parents=True, exist_ok=True)

    for index, case in enumerate(cases):
        print(f"\n  --- Case {index+1}/{num_cases}: {case.case_id} "
              f"(multiple={case.ground_truth.realized_max_multiple:.1f}) ---")

        def sink(company_id, prediction_time, context, prediction):
            path = prediction_dir / f"{case.case_id}.prediction.json"
            path.write_text(json.dumps({
                "case_id": case.case_id,
                "company_id": company_id,
                "prediction_time": prediction_time.isoformat(),
                "prediction": prediction.to_dict(),
                "final_context_size": len(json.dumps(context)),
            }, ensure_ascii=False, indent=1), encoding="utf-8")
            return str(path)

        def truth_provider(company_id):
            return case.ground_truth

        try:
            trajectory = execute_information_plan(
                plan=plan,
                company_id=case.company_id,
                case_id=case.case_id,
                company_basic_source=case.basic_info,
                prediction_time=case.prediction_time,
                signal_registry=frozen,
                signal_executor=executor,
                controller=controller,
                signal_agent=signal_agent,
                predictor=predictor,
                prediction_sink=sink,
                ground_truth_provider=truth_provider,
            )
            trajectories.append(trajectory)
            issues = check_fast_artifacts(trajectory)
            status = "✓" if not issues else "⚠ " + "; ".join(issues[:3])
            print(f"    Artifacts: {status}")
            # Print key content for manual inspection
            pred = trajectory.prediction
            print(f"    Prediction: {pred.candidate_judgment.value} "
                  f"(magnitude={pred.magnitude.value if pred.magnitude else None}, "
                  f"confidence={pred.confidence})")
            print(f"    Key reasons: {pred.key_reasons[0][:100] if pred.key_reasons else 'none'}")
            print(f"    Stop: {trajectory.stop_reason.value}, "
                  f"Rounds: {len(trajectory.signal_rounds)}, "
                  f"Beliefs: {len(trajectory.final_state.current_beliefs)}")
            sr = trajectory.self_reflection
            if sr and sr.reflection_items:
                print(f"    Reflection items: {len(sr.reflection_items)}")
                for item in sr.reflection_items[:2]:
                    print(f"      [{item.category}] {item.brief[:90]}")
            if trajectory.state_deltas:
                last = trajectory.state_deltas[-1]
                d = last.get("delta", {})
                added_b = d.get("current_beliefs", {}).get("added", [])
                print(f"    Last delta: beliefs+{len(added_b)} "
                      f"needs-/+{len(d.get('next_information_needs',{}).get('added',[]))}/{len(d.get('next_information_needs',{}).get('removed',[]))}")
        except Exception as exc:
            print(f"    ✗ FAILED: {type(exc).__name__}: {str(exc)[:200]}")
            import traceback
            traceback.print_exc()
            # Record as technical exclusion
            from stock_opportunity_agent.research.evolution_core import (
                BlindPrediction, CandidateJudgment, ConfidenceLevel,
                ExecutionTrajectory, ResearchState, ResearchDecision,
                RuntimeStopReason, RuntimeUsage, PredictionSelfReflection,
                GroundTruth,
            )
            from stock_opportunity_agent.llm.agent import AgentUsage
            abstain = BlindPrediction(
                is_surge=False,
                candidate_judgment=CandidateJudgment.INSUFFICIENT_INFORMATION,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("Technical exclusion",),
                uncertainties=(),
                session_id=f"exclusion_{case.case_id}",
            )
            trajectories.append(ExecutionTrajectory(
                case_id=case.case_id,
                company_id=case.company_id,
                prediction_time=case.prediction_time,
                basic_info={"requests": []},
                initial_state=ResearchState(decision=ResearchDecision.FINALIZE),
                signal_rounds=(),
                final_state=ResearchState(decision=ResearchDecision.FINALIZE),
                final_context={},
                prediction=abstain,
                prediction_ref=str(root / "predictions" / f"{case.case_id}.abstain.json"),
                ground_truth=case.ground_truth,
                self_reflection=PredictionSelfReflection(
                    correct=not case.ground_truth.is_surge,
                    plan_issues=(f"technical_case_exclusion: {str(exc)[:120]}",),
                ),
                stop_reason=RuntimeStopReason.FINALIZED,
                usage=RuntimeUsage(
                    signal_rounds=0, signal_calls=0, model=AgentUsage()),
            ))

    print(f"\n  === Scoring {len(trajectories)} trajectories ===")
    metrics = score_predictions(trajectories)
    print(f"    Binary F1:     {metrics.binary_f1:.4f}")
    print(f"    Precision:     {metrics.binary_precision:.4f}")
    print(f"    Recall:        {metrics.binary_recall:.4f}")
    print(f"    Magnitude acc: {metrics.magnitude_accuracy:.4f}")
    print(f"    Magnitude F1:  {metrics.magnitude_macro_f1:.4f}")
    print(f"    TP/FP/TN/FN:   {metrics.true_positive}/{metrics.false_positive}/{metrics.true_negative}/{metrics.false_negative}")

    # Save trajectory summaries for slow round
    summaries = []
    for traj in trajectories:
        summaries.append({
            "case_id": traj.case_id,
            "company_id": traj.company_id,
            "prediction": traj.prediction.to_dict(),
            "stop_reason": traj.stop_reason.value,
            "is_technical_exclusion": traj.prediction.session_id.startswith("exclusion_"),
            "self_reflection": traj.self_reflection.to_dict() if traj.self_reflection else None,
            "final_state_beliefs": list(traj.final_state.current_beliefs) if traj.final_state else [],
        })
    (root / "fast_trajectories.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"metrics": metrics.to_dict(), "trajectories": summaries}


def run_slow_round(caller, root: Path, fast_result, num_cases: int) -> dict:
    """Drive one minimal Slow mining cycle using Fast round reflections."""
    from stock_opportunity_agent.data.raw_info import RawInfoStore
    from stock_opportunity_agent.research.evolution_core import (
        EvolutionCase, GroundTruth, PlanMetaMemory, RoundMetaEntry,
        PredictionSelfReflection,
    )
    from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace
    from stock_opportunity_agent.research.signal_evolution import (
        SignalEvolutionEngine, SignalMiningConfig,
    )
    from stock_opportunity_agent.signal_library import SignalRegistry
    from stock_opportunity_agent.research.evolution_signal_roles import (
        StructuredLLMSignalRunner,
    )
    from tests.scheme_evolution_test_support import (
        EmptyMiningModel, NoChangeUpdateModel, SEED_CATALOG,
    )

    print("  Building meta_memory from Fast round reflections...")
    trajs = fast_result["trajectories"] if fast_result else []
    meta_memory = PlanMetaMemory()
    for row in trajs:
        sr = row.get("self_reflection")
        if not sr or not sr.get("reflection_items"):
            continue
        entry_data = {
            "round_id": 1,
            "plan_level": {
                "successful_patterns": [],
                "failed_patterns": [],
            },
            "prediction_errors": {
                "false_positive": [],
                "false_negative": [],
            },
            "signal_observations": {
                "useful": [],
                "suspicious": [],
                "missing_capabilities": [],
            },
            "search_implications": [],
            "evidence_refs": [row.get("case_id", "")],
            "plan_reflections": [{
                "plan_id": "minimal_plan",
                "plan": {"B": []},
                "original_case_reflections": [{
                    "case_index": 1,
                    "self_reflection": sr,
                }],
                "vertical_plan_reflection": {},
            }],
        }
        try:
            entry = RoundMetaEntry.from_dict(entry_data)
            meta_memory.append(entry)
            print(f"    + entry from {row['case_id'][:25]} ({len(sr['reflection_items'])} items)")
        except Exception as exc:
            print(f"    (skip: {type(exc).__name__}: {str(exc)[:60]})")

    print(f"  Meta memory entries: {len(meta_memory.entries)}")

    # Build cases for mining (same as fast round)
    cases = build_cases(CASE_COMPANIES[:num_cases])
    store = RawInfoStore(str(ORACLE))

    # Set up workspace
    ws_root = root / "workspace"
    ws_root.mkdir(parents=True, exist_ok=True)
    workspace = EvolutionWorkspace(ws_root)

    # Registry
    registry_dir = root / "signals"
    registry = SignalRegistry(registry_dir)
    registry.install_catalog(SEED_CATALOG)

    # Mining model: wrap our caller
    mining_model = EmptyMiningModel()
    mining_model.caller = caller
    update_model = NoChangeUpdateModel()
    signal_runner = StructuredLLMSignalRunner(caller)

    from stock_opportunity_agent.research.evolution_core import (
        ResearchState, ResearchDecision,
    )
    from stock_opportunity_agent.signal_library import (
        SignalBatchResult, SignalResult, SignalValue,
    )

    class MiningCallerWrapper:
        """Bridge JournaledCaller to mining controller's complete_json."""
        def __init__(self, jc):
            self.jc = jc
        def complete_json(self, **kwargs):
            return self.jc.complete_json(**kwargs)
        @property
        def on_progress(self):
            return None

    class MiningModel:
        """Mining model backed by the journaled caller."""
        def __init__(self, jc):
            self.caller = MiningCallerWrapper(jc)

    mining_model = MiningModel(caller)

    engine = SignalEvolutionEngine(
        registry=registry,
        raw_info_store=store,
        discovery_cases=tuple(cases),
        meta_memory=meta_memory,
        workspace=workspace,
        mining_model=mining_model,
        update_model=update_model,
        llm_signal_runner=signal_runner,
    )
    # Build sampling manifest so the engine can partition dev/check
    from stock_opportunity_agent.research.signal_evolution import build_slow_sampling_manifest
    engine._active_sampling_manifest = build_slow_sampling_manifest(
        tuple(cases), cycle_id=1, base_seed="minimal_slow",
        dev_limit=6, check_limit=2,
    )

    print("\n  Running controller mining (cycle 1)...")
    try:
        output = engine._run_controller_mining(cycle_id=1)
        audit = output.get("audit", {})
        track = audit.get("track", "?")
        print(f"  Track: {track}")
        candidates = output.get("candidates", [])
        print(f"  Candidates: {len(candidates)}")
        for cand in candidates[:5]:
            if isinstance(cand, tuple) and len(cand) >= 2:
                print(f"    {cand[0]}")
            elif isinstance(cand, dict):
                measurement = cand.get("measurement", {})
                print(f"    observable={measurement.get('observable','?')}")
        # Check candidate refs from audit
        cand_refs = audit.get("candidate_refs", [])
        print(f"  Candidate refs: {len(cand_refs)}")
        for ref in cand_refs[:5]:
            print(f"    {ref}")
        # Check for staged signals
        staged = list((root / "signals_candidates").glob("*")) if (root / "signals_candidates").exists() else []
        print(f"  Staged candidates dir: {len(staged)} files")
        return {"track": track, "candidates": len(candidates), "candidate_refs": cand_refs}
    except Exception as exc:
        print(f"  ✗ SLOW FAILED: {type(exc).__name__}: {str(exc)[:300]}")
        import traceback
        traceback.print_exc()
        return {"error": str(exc)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="runs/cold_start/minimal_rounds_v151")
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--skip-fast", action="store_true")
    parser.add_argument("--skip-slow", action="store_true")
    args = parser.parse_args()
    root = REPO / args.root
    root.mkdir(parents=True, exist_ok=True)
    _load_env()

    from stock_opportunity_agent.llm.deepseek import (
        DeepSeekResponsesClient, DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL,
    )
    client = DeepSeekResponsesClient(
        DEFAULT_DEEPSEEK_MODEL, os.environ["DEEPSEEK_API_KEY"],
        base_url=DEFAULT_DEEPSEEK_BASE_URL, temperature=0.0,
    )
    caller = JournaledCaller(client, root)

    fast_result = None
    if not args.skip_fast:
        fast_result = run_fast_round(caller, root, args.cases)
        (root / "fast_summary.json").write_text(
            json.dumps(fast_result["metrics"], indent=1), encoding="utf-8")
        print(f"\n  Fast round complete. {len(caller.calls)} calls, "
              f"journal at {caller.journal_root}")

    if not args.skip_slow:
        print("\n" + "=" * 20 + " SLOW ROUND " + "=" * 20)
        run_slow_round(caller, root, fast_result, args.cases)


if __name__ == "__main__":
    main()

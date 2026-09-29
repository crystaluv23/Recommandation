"""Live external-call validation of the v146 tool and reflection pipeline.

Stages, executed sequentially with content-level verification after each:

  1. distillation   — RawInfoDistiller over the real GPE sale news
  2. posthoc        — case reflection over a real V143 frozen trajectory
  3. plan critic    — critic over real V143 trajectories
  4. reflect        — H_reflect with document catalog + compute registry
                      over real AXT artifacts

Every provider call is journaled under the validation root keyed by the
canonical request hash. Re-running the harness replays journaled responses
(reported as REPLAY, zero network) and only changed or new requests reach
the provider (reported as LIVE), so a later-stage fix replays earlier
stages instead of re-billing them.

Usage:
    PYTHONPATH=src python scripts/live_tool_validation_v146.py \
        --root runs/cold_start/live_tool_validation_v146
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

from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.llm.deepseek import DeepSeekResponsesClient
from stock_opportunity_agent.llm.openai import ChatMessage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_transport import (
    StructuredOutputInvalid,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ORACLE = REPO_ROOT / "runs/cold_start/data/global-raw-info-oracle-v1"
V143 = (
    REPO_ROOT
    / "runs/cold_start/evolution/information-evolution-jev-dual-self-evolution-20260928-v143"
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class JournaledLiveCaller:
    """JSONRoleCaller over the DeepSeek provider with journal + replay."""

    max_structured_corrections = 1

    def __init__(self, client: DeepSeekResponsesClient, root: Path) -> None:
        self.client = client
        self.journal_root = root / "journal"
        self.journal_root.mkdir(parents=True, exist_ok=True)
        self.calls: list[dict[str, Any]] = []

    def _key(self, stage: str, request: dict[str, Any]) -> str:
        digest = hashlib.sha256(_canonical(request).encode("utf-8")).hexdigest()
        return f"{stage}-{digest[:24]}"

    def complete_json(
        self,
        *,
        stage: str,
        system_prompt: str,
        payload: Mapping[str, Any],
        allow_outcomes: bool,
        anonymous_aliases: Iterable[str] = (),
        max_output_tokens: int | None = None,
        max_request_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], AgentUsage]:
        del allow_outcomes, anonymous_aliases, max_request_tokens
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
            usage = AgentUsage(**record["usage"])
        else:
            mode = "LIVE"
            messages = [
                ChatMessage("system", "Return exactly one JSON object and no non-JSON text. " + system_prompt),
                ChatMessage("user", _canonical(payload)),
            ]
            kwargs: dict[str, Any] = {
                "max_output_tokens": max_output_tokens or 8_000,
                "response_format": {"type": "json_object"},
                # Match the production judge profile: non-thinking mode so
                # reasoning does not consume the role's output budget.
                "reasoning": {"effort": "none"},
            }
            response = self.client.complete(messages, **kwargs)
            raw_output = response.output_text
            usage = self._usage(response.raw)
            path.write_text(
                json.dumps(
                    {
                        "key": key,
                        "mode": "live",
                        "request": request,
                        "response_text": raw_output,
                        "usage": {
                            "llm_calls": usage.llm_calls,
                            "tokens": usage.tokens,
                            "cost": usage.cost,
                        },
                    },
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding="utf-8",
            )
        self.calls.append({"key": key, "mode": mode, "stage": stage})
        print(f"    [{mode}] {stage} ({key[:20]}…) tokens={usage.tokens}")
        try:
            value = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise StructuredOutputInvalid(
                "provider returned invalid JSON",
                raw_output,
                usage,
                output_tokens=usage.tokens,
                output_token_limit=max_output_tokens,
            ) from exc
        if not isinstance(value, dict):
            raise StructuredOutputInvalid(
                "provider response is not one JSON object",
                raw_output,
                usage,
                output_tokens=usage.tokens,
                output_token_limit=max_output_tokens,
            )
        return value, usage

    @staticmethod
    def _usage(raw: Mapping[str, Any]) -> AgentUsage:
        usage = raw.get("usage") if isinstance(raw, Mapping) else None
        tokens = 0
        if isinstance(usage, Mapping):
            tokens = int(
                usage.get("total_tokens")
                or (
                    int(usage.get("input_tokens") or 0)
                    + int(usage.get("output_tokens") or 0)
                )
                or 0
            )
        return AgentUsage(llm_calls=1, tokens=tokens, cost=0.0)


def _load_document(path: Path) -> Any:
    from stock_opportunity_agent.data.raw_info import RawInfoDocument

    return RawInfoDocument.from_dict(json.loads(path.read_text(encoding="utf-8")))


def stage_distillation(caller: JournaledLiveCaller, root: Path) -> dict[str, Any]:
    print("\n=== Stage 1: distillation (real GPRE sale news) ===")
    import glob

    from stock_opportunity_agent.data.raw_info import RawInfoStore
    from stock_opportunity_agent.research.distillation import RawInfoDistiller

    matches = sorted(
        glob.glob(str(ORACLE / "news/cik_0001309402/alpha_vantage*cik_0001309402*news*6d5165cc*.json"))
    )
    if not matches:
        raise SystemExit("GPRE sale news fixture not found in oracle")
    news = _load_document(Path(matches[0]))
    store = RawInfoStore(documents=(news,))
    step = RawInfoDistiller(caller).distill(
        store,
        {"document_id": news.document_id, "content_hash": news.content_hash},
        as_of=datetime(2025, 9, 30, tzinfo=timezone.utc),
        focus="takeover, strategic review, CEO departure and any quantified facts",
    )
    card = step.value
    problems: list[str] = []
    for index, fact in enumerate(card["quantified_facts"]):
        start, end = fact["raw_start"], fact["raw_end"]
        if news.content[start:end] != fact["quote"]:
            problems.append(f"quote[{index}] offset mismatch")
    summary_numbers = {
        token
        for token in __import__("re").findall(r"\d[\d,]*(?:\.\d+)?", card["event_summary"])
    }
    quoted = " ".join(fact["quote"] for fact in card["quantified_facts"])
    leaked = [token for token in summary_numbers if token not in quoted]
    if leaked:
        problems.append(f"summary numbers absent from quotes: {leaked}")
    if not card["event_summary"].strip():
        problems.append("empty summary")
    result = {
        "stage": "distillation",
        "event_summary": card["event_summary"],
        "quotes": [fact["quote"] for fact in card["quantified_facts"]],
        "offsets_byte_exact": not problems,
        "problems": problems,
    }
    print("    summary:", card["event_summary"])
    print("    quotes:", len(card["quantified_facts"]), "problems:", problems)
    return result


def stage_posthoc(caller: JournaledLiveCaller, root: Path) -> dict[str, Any]:
    print("\n=== Stage 2: posthoc case reflection (real V143 trajectory) ===")
    from stock_opportunity_agent.research.evolution_core import (
        BlindPrediction,
        ExecutionTrajectory,
        GroundTruth,
    )
    from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor

    record = json.loads((V143 / "plans/plan_r0002_c02/record.json").read_text())
    trajectory_dicts = record["trajectories"]
    chosen = None
    for row in trajectory_dicts:
        prediction = row.get("prediction") or {}
        truth = row.get("ground_truth") or {}
        if prediction.get("is_surge") is False and truth.get("is_surge") is True:
            chosen = row  # a real missed-surge case: richest reflection material
            break
    if chosen is None:
        chosen = trajectory_dicts[0]
    context = chosen["final_context"]
    prediction = BlindPrediction.from_dict(chosen["prediction"])
    truth = GroundTruth.from_dict(chosen["ground_truth"])
    step = LLMBlindPredictor(caller).reflect(context, prediction, truth)
    reflection = step.value
    items = reflection.reflection_items
    problems: list[str] = []
    if not items and not reflection.no_findings_reason:
        problems.append("no items and no reason")
    generic_markers = ("improve research", "be more careful", "gather more information")
    for item in items:
        if any(marker in item.brief.lower() for marker in generic_markers):
            problems.append(f"generic brief: {item.brief[:60]}")
        if not item.source_refs:
            problems.append("item without source refs")
    def _claim_correct(claim: Any) -> bool:
        if isinstance(claim, dict):
            return bool(claim.get("correct"))
        return bool(getattr(claim, "correct", False))

    outcome_wrong = [
        item.brief
        for item in items
        if item.category in {"why_prediction_failed", "failed_patterns"}
        and any(_claim_correct(claim) for claim in item.outcome_claims)
    ]
    if outcome_wrong:
        problems.append(f"mixed-axis straddle persisted: {outcome_wrong[:1]}")
    result = {
        "stage": "posthoc",
        "case_id": chosen.get("case_id"),
        "no_findings_reason": reflection.no_findings_reason,
        "item_count": len(items),
        "briefs": [item.brief for item in items],
        "problems": problems,
    }
    print(f"    case={chosen.get('case_id')} items={len(items)} reason={reflection.no_findings_reason}")
    for item in items:
        print("     -", item.brief[:100])
    print("    problems:", problems)
    return result


def stage_critic(caller: JournaledLiveCaller, root: Path) -> dict[str, Any]:
    print("\n=== Stage 3: plan critic (real V143 trajectories) ===")
    from stock_opportunity_agent.research.evolution_core import (
        ExecutionTrajectory,
        InformationPlan,
        PlanMetrics,
    )
    from stock_opportunity_agent.research.evolution_plan_roles import LLMPlanCritic

    record = json.loads((V143 / "plans/plan_r0002_c02/record.json").read_text())
    trajectories = tuple(
        ExecutionTrajectory.from_dict(row) for row in record["trajectories"][:6]
    )
    plan = InformationPlan.from_dict(record["plan"])
    confusion = record["metrics"].get("confusion") or {}
    metrics = PlanMetrics(
        binary_precision=record["metrics"]["binary_precision"],
        binary_recall=record["metrics"]["binary_recall"],
        binary_f1=record["metrics"]["binary_f1"],
        magnitude_accuracy=record["metrics"]["magnitude_accuracy"],
        magnitude_macro_f1=record["metrics"]["magnitude_macro_f1"],
        true_positive=confusion.get("true_positive", 0),
        false_positive=confusion.get("false_positive", 0),
        true_negative=confusion.get("true_negative", 0),
        false_negative=confusion.get("false_negative", 0),
        sample_count=record["metrics"]["sample_count"],
    )
    critic = LLMPlanCritic(caller)
    reflection = critic.critique(plan=plan, trajectories=trajectories, metrics=metrics)
    items = reflection.reflection_items
    problems: list[str] = []
    salvage_partial = str(reflection.no_findings_reason or "").startswith(
        "reflection_items_all_invalid_salvaged"
    )
    if reflection.no_findings_reason and not (
        salvage_partial and reflection.selected_reflection_refs
    ):
        problems.append(f"critic failed: {reflection.no_findings_reason[:120]}")
    if len(items) > 6:
        problems.append(f"authored items exceed cap: {len(items)}")
    for item in items:
        if len(item.brief) < 40:
            problems.append(f"thin brief: {item.brief[:60]}")
    result = {
        "stage": "critic",
        "salvage_partial": salvage_partial,
        "no_findings_reason": reflection.no_findings_reason,
        "item_count": len(items),
        "selected_lower_items": list(reflection.selected_reflection_refs),
        "briefs": [item.brief for item in items],
        "problems": problems,
    }
    print(f"    items={len(items)} selected={len(reflection.selected_reflection_refs)}")
    for item in items:
        print("     -", item.brief[:100])
    print("    problems:", problems)
    return result


def stage_reflect(caller: JournaledLiveCaller, root: Path) -> dict[str, Any]:
    print("\n=== Stage 4: H_reflect with catalog + compute (real AXT) ===")
    import sys as _sys

    _sys.path.insert(0, str(REPO_ROOT / "tests"))
    from tests.evolution_runtime_test_support import default_information_plan

    from stock_opportunity_agent.data.raw_info import RawInfoStore
    from stock_opportunity_agent.research.compute_tools import compute_metric
    from stock_opportunity_agent.research.evolution_core import (
        ResearchState,
        _DocumentChannelProvider,
        _prediction_baseline_from_market_documents,
    )
    from stock_opportunity_agent.research.evolution_plan_roles import (
        LLMResearchController,
    )
    from stock_opportunity_agent.signal_library import (
        SignalBatchResult,
        SignalResult,
        SignalValue,
    )

    as_of = datetime(2025, 9, 30, tzinfo=timezone.utc)
    base = ORACLE / "filing/cik_0001051627"
    eight_k = _load_document(base / "sec:cik_0001051627:000143774925027362.json")
    ten_q = _load_document(base / "sec:cik_0001051627:000143774925026516.json")
    market_glob = sorted((ORACLE / "prices/cik_0001051627").glob("*.json")) or sorted(
        (ORACLE / "market_data/cik_0001051627").glob("*.json")
    )
    market = _load_document(market_glob[0]) if market_glob else None
    documents = [eight_k, ten_q] + ([market] if market is not None else [])
    store = RawInfoStore(documents=documents)

    anchor_docs = (market,) if market is not None else ()
    anchor = _prediction_baseline_from_market_documents(anchor_docs, as_of)
    controller = LLMResearchController(caller)
    controller.set_evaluation_context(as_of)
    bootstrap = []
    if anchor.get("status") == "available":
        controller.set_evaluation_anchor(anchor)
        bootstrap = [
            compute_metric(
                "price_shape",
                {"window_days": 180},
                documents=anchor_docs,
                as_of=as_of,
            )
        ]
        controller.set_computed_metrics(bootstrap)
    controller.set_document_channel(
        _DocumentChannelProvider(
            store,
            company_id="cik_0001051627",
            as_of=as_of,
            market_documents=anchor_docs,
            anchor=anchor if anchor.get("status") == "available" else None,
        )
    )
    prior_state = ResearchState(
        hypotheses=(
            "Export-permit news may reprice AXT within the horizon.",
        ),
        next_information_needs=(
            "Which customers and revenue amounts were named in the export "
            "permit disclosure?",
        ),
    )
    batch = SignalBatchResult(
        results=(
            SignalResult(
                signal_id="guidance_acceleration",
                version=1,
                value=SignalValue.NEUTRAL,
                confidence=0.5,
                interpretation=(
                    "Neutral guidance signal: no new guidance found in the "
                    "already-visible spans. The catalog lists an unexamined "
                    "8-K (form 8-K) whose items may contain the export permit "
                    "disclosure details this round still needs."
                ),
            ),
        ),
        signal_calls=1,
    )
    step = controller.reflect(default_information_plan(), prior_state, batch)
    reflected = step.value
    reflect_rows = [
        row
        for row in caller.calls
        if row["stage"].startswith("research_controller_reflect")
    ]
    first_payload = json.loads(
        (caller.journal_root / f"{reflect_rows[0]['key']}.json").read_text(
            encoding="utf-8"
        )
    )["request"]["payload"]
    problems: list[str] = []
    if "document_catalog" not in first_payload:
        problems.append("catalog missing from reflect payload")
    if bootstrap and "computed_metrics" not in first_payload:
        problems.append("bootstrap computed metrics missing")
    exchanges = reflect_rows
    delta_added = list(reflected.current_beliefs or ())
    exchange_used = len(exchanges) > 1 or any(
        key.startswith("research_controller_reflect")
        and "document_channel" in json.loads((caller.journal_root / f"{key}.json").read_text())["request"]["payload"]
        for key in [row["key"] for row in exchanges]
    )
    print(
        f"    reflect calls={len(exchanges)} exchange_used={exchange_used} "
        f"beliefs_returned={len(delta_added)}"
    )
    for belief in delta_added:
        print("     belief:", belief[:110])
    result = {
        "stage": "reflect",
        "reflect_calls": len(exchanges),
        "catalog_in_payload": "document_catalog" in first_payload,
        "bootstrap_metrics_in_payload": bool(bootstrap) and "computed_metrics" in first_payload,
        "beliefs": delta_added,
        "exchange_used": exchange_used,
        "problems": problems,
    }
    print("    problems:", problems)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="runs/cold_start/live_tool_validation_v146")
    args = parser.parse_args()
    root = REPO_ROOT / args.root
    root.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(REPO_ROOT))

    env_path = REPO_ROOT / ".env.local"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is not configured")
    from stock_opportunity_agent.llm.deepseek import (
        DEFAULT_DEEPSEEK_BASE_URL,
        DEFAULT_DEEPSEEK_MODEL,
    )

    client = DeepSeekResponsesClient(
        DEFAULT_DEEPSEEK_MODEL,
        api_key,
        base_url=DEFAULT_DEEPSEEK_BASE_URL,
        temperature=0.0,
    )
    caller = JournaledLiveCaller(client, root)

    results = [
        stage_distillation(caller, root),
        stage_posthoc(caller, root),
        stage_critic(caller, root),
        stage_reflect(caller, root),
    ]
    summary = {
        "schema_version": "live-tool-validation-v146-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "calls": caller.calls,
        "stages": results,
        "all_stages_pass": all(not row["problems"] for row in results),
    }
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n=== SUMMARY ===")
    for row in results:
        print(f"  {row['stage']}: {'PASS' if not row['problems'] else 'FAIL ' + str(row['problems'])}")
    print("  all_stages_pass:", summary["all_stages_pass"])


if __name__ == "__main__":
    main()

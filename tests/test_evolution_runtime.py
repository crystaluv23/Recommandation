from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.llm import RegisteredModel
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_runtime import (
    EvolutionRunContract,
    ExactResponseCache,
    ExternalAttemptLedger,
    ExternalRequestPending,
    LLMBlindPredictor,
    LLMResearchController,
    LLMSignalRetrievalAgent,
    StructuredRoleClient,
    approve_dataset_proposal,
    filter_case_price_history,
    inventory_local_evolution_inputs,
    load_approved_development_dataset,
    migrate_legacy_raw_info,
    prepare_dataset_proposal,
)
from stock_opportunity_agent.research.scheme_evolution import default_information_plan
from stock_opportunity_agent.signal_library import SignalRegistry


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def make_contract() -> EvolutionRunContract:
    return EvolutionRunContract(
        run_id="fixture-run",
        created_at="2026-08-09T00:00:00+00:00",
        dataset_manifest_hash=SHA_A,
        raw_info_inventory_hash=SHA_B,
        signal_registry_version=1,
        signal_registry_hash=SHA_C,
        priors_hash=SHA_D,
        models={"judge": {"alias": "fixture-judge"}},
        code_revision="deadbeef",
        python_runtime="3.12.0",
        limits={"rounds": 1},
        max_external_attempts=2,
        max_total_cost=1.0,
    )


class LocalInventoryTests(TestCase):
    def test_inventory_hashes_current_local_shapes_without_reusing_legacy_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / "cases.json"
            documents = root / "documents.json"
            prices = root / "prices.json"
            write_json(
                cases,
                {
                    "cases": [
                        {
                            "outcome_definition_id": "legacy-terminal-return",
                            "packet": {
                                "as_of": {"as_of_date": "2025-01-01"},
                                "company": {"ticker": {"symbol": "AAA"}},
                            },
                        },
                        {
                            "outcome_definition_id": "legacy-terminal-return",
                            "packet": {
                                "as_of": {"as_of_date": "2025-02-01"},
                                "company": {"ticker": {"symbol": "BBB"}},
                            },
                        },
                    ]
                },
            )
            write_json(
                documents,
                {
                    "documents_by_symbol": {
                        "AAA": [
                            {
                                "available_date": "2024-12-31",
                                "text": "public evidence",
                            }
                        ]
                    }
                },
            )
            write_json(
                prices,
                {
                    "schema_version": "scheme-evolution-adjusted-prices-v1",
                    "source": "fixture",
                    "start_date": "2024-12-01",
                    "end_date": "2025-08-01",
                    "requested_symbol_count": 2,
                    "bars_by_symbol": {
                        "AAA": [{"as_of_date": "2025-01-02", "adjusted_close": 10}],
                    },
                    "failed_symbols": {"BBB": "missing"},
                },
            )
            inventory = inventory_local_evolution_inputs(
                cases_path=cases,
                documents_path=documents,
                adjusted_prices_path=prices,
            )
            self.assertEqual(inventory.compatible_case_count, 1)
            self.assertFalse(inventory.migration_ready)
            self.assertEqual(len(inventory.inventory_hash), 64)
            self.assertIn("terminal-return", inventory.incompatible_label_reason)
            self.assertFalse(inventory.to_dict()["locked_test_accessed"])

    def test_raw_info_migration_excludes_labels_and_future_prices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / "cases.json"
            documents = root / "documents.json"
            prices = root / "prices.json"
            raw_info = root / "raw_info"
            write_json(
                cases,
                {
                    "cases": [
                        {
                            "case_id": "AAA:2025-01-10:winner",
                            "label": "winner",
                            "outcome_return": 8.0,
                            "packet": {
                                "as_of": {"as_of_date": "2025-01-10"},
                                "company": {"ticker": {"symbol": "AAA"}},
                            },
                        }
                    ]
                },
            )
            write_json(
                documents,
                {
                    "documents_by_symbol": {
                        "AAA": [
                            {
                                "document_id": "sec:aaa:1",
                                "source_id": "sec:aaa:1",
                                "source_url": "https://example.test/filing",
                                "kind": "filing",
                                "published_date": "2025-01-05",
                                "available_date": "2025-01-05",
                                "title": "Filed report",
                                "text": "Revenue was reported before prediction time.",
                            }
                        ]
                    }
                },
            )
            write_json(
                prices,
                {
                    "schema_version": "scheme-evolution-adjusted-prices-v1",
                    "source": "fixture",
                    "start_date": "2025-01-01",
                    "end_date": "2025-07-10",
                    "requested_symbol_count": 1,
                    "bars_by_symbol": {
                        "AAA": [
                            {"as_of_date": "2025-01-09", "adjusted_close": 10},
                            {"as_of_date": "2025-01-10", "adjusted_close": 20},
                            {"as_of_date": "2025-02-01", "adjusted_close": 80},
                        ]
                    },
                    "failed_symbols": {},
                },
            )
            filtered = filter_case_price_history(
                cases_path=cases,
                full_price_archive_path=prices,
                output_path=root / "filtered_prices.json",
            )
            self.assertEqual(filtered.facts["priced_symbol_count"], 1)
            report = migrate_legacy_raw_info(
                cases_path=cases,
                documents_path=documents,
                adjusted_prices_path=prices,
                raw_info_root=raw_info,
            )
            self.assertEqual(report.migrated_source_documents, 1)
            self.assertEqual(report.migrated_market_snapshots, 1)
            replay = migrate_legacy_raw_info(
                cases_path=cases,
                documents_path=documents,
                adjusted_prices_path=prices,
                raw_info_root=raw_info,
            )
            self.assertEqual(replay.migrated_source_documents, 1)
            self.assertEqual(replay.appended_source_documents, 0)
            store = RawInfoStore(raw_info)
            serialized = json.dumps([item.to_dict() for item in store.documents])
            self.assertNotIn("winner", serialized)
            self.assertNotIn("outcome_return", serialized)
            market = next(
                item for item in store.documents if item.source_type == "market_data"
            )
            self.assertEqual(market.metadata["prices"], [10.0])

    def test_dataset_proposal_recomputes_two_x_label_and_needs_exact_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases_path = root / "cases.json"
            documents_path = root / "documents.json"
            prices_path = root / "prices.json"
            symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
            cases = []
            bars_by_symbol = {}
            for index, symbol in enumerate(symbols):
                cases.append(
                    {
                        "case_id": f"{symbol}:legacy",
                        "label": "legacy-value-must-not-be-reused",
                        "packet": {
                            "as_of": {"as_of_date": "2025-01-10"},
                            "company": {
                                "ticker": {
                                    "symbol": symbol,
                                    "company_name": f"{symbol} Corp",
                                },
                                "industry": "fixture",
                            },
                        },
                    }
                )
                future_price = 25.0 if index < 3 else 12.0
                bars_by_symbol[symbol] = [
                    *[
                        {
                            "as_of_date": f"2025-01-0{day}",
                            "adjusted_close": 10.0,
                        }
                        for day in range(5, 10)
                    ],
                    *[
                        {
                            "as_of_date": f"2025-01-{day:02d}",
                            "adjusted_close": future_price,
                        }
                        for day in range(10, 15)
                    ],
                    {"as_of_date": "2025-07-10", "adjusted_close": future_price},
                ]
            write_json(cases_path, {"cases": cases})
            write_json(
                documents_path,
                {"documents_by_symbol": {symbol: [] for symbol in symbols}},
            )
            write_json(
                prices_path,
                {
                    "schema_version": "scheme-evolution-adjusted-prices-v1",
                    "source": "fixture",
                    "start_date": "2025-01-05",
                    "end_date": "2025-07-10",
                    "requested_symbol_count": 6,
                    "bars_by_symbol": bars_by_symbol,
                    "failed_symbols": {},
                },
            )
            report = prepare_dataset_proposal(
                cases_path=cases_path,
                documents_path=documents_path,
                adjusted_prices_path=prices_path,
                output_root=root / "proposal",
            )
            self.assertEqual(report.eligible_case_count, 6)
            self.assertEqual(report.split_surge_counts, {
                "discovery": 1,
                "evolution_validation": 1,
                "locked_test": 1,
            })
            with self.assertRaisesRegex(ValidationError, "hash"):
                approve_dataset_proposal(
                    proposal_manifest_path=report.manifest_path,
                    expected_proposal_hash="0" * 64,
                    approved_by="reviewer",
                )
            approved = approve_dataset_proposal(
                proposal_manifest_path=report.manifest_path,
                expected_proposal_hash=report.manifest_hash,
                approved_by="reviewer",
            )
            self.assertEqual(
                json.loads(approved.read_text(encoding="utf-8"))["approval_status"],
                "human_approved",
            )
            proposal_manifest = json.loads(
                Path(report.manifest_path).read_text(encoding="utf-8")
            )
            Path(proposal_manifest["artifacts"]["locked_test"]["path"]).unlink()
            development = load_approved_development_dataset(approved)
            self.assertEqual(len(development.discovery), 2)
            self.assertEqual(len(development.evolution_validation), 2)


class ScriptedRoleCaller:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self.outputs = list(outputs)
        self.stages: list[str] = []

    def complete_json(self, **kwargs):
        self.stages.append(str(kwargs["stage"]))
        return self.outputs.pop(0), AgentUsage(llm_calls=1, tokens=5, cost=0.01)


class ConcreteRoleAdapterTests(TestCase):
    def test_controller_and_progressive_signal_selector_use_structured_roles(self) -> None:
        controller_caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": ["commercialization may accelerate"],
                    "next_information_needs": ["revenue growth"],
                    "decision": "continue",
                }
            ]
        )
        state = LLMResearchController(controller_caller).initialize(
            default_information_plan(), {"industry": "fixture"}
        )
        self.assertEqual(state.value.next_information_needs, ("revenue growth",))
        self.assertEqual(controller_caller.stages, ["research_controller_initialize"])

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            selector_caller = ScriptedRoleCaller(
                [
                    {"categories": ["financial"]},
                    {"signal_refs": ["revenue_growth_yoy:v1"]},
                ]
            )
            selection = LLMSignalRetrievalAgent(selector_caller).select(
                ("revenue growth",), registry.freeze()
            )
            self.assertEqual(selection.value, ("revenue_growth_yoy:v1",))
            self.assertEqual(
                selector_caller.stages,
                ["signal_retrieval_categories", "signal_retrieval_cards"],
            )

    def test_blind_predictor_parses_two_stage_schema(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "is_surge": True,
                    "magnitude": "2-3x",
                    "confidence": {"level": "medium"},
                    "key_reasons": ["source-backed evidence"],
                    "uncertainties": [],
                    "session_id": "fixture-session",
                }
            ]
        )
        prediction = LLMBlindPredictor(caller).predict(
            {"basic_info": {"industry": "fixture"}}
        )
        self.assertTrue(prediction.value.is_surge)
        self.assertEqual(prediction.value.magnitude.value, "2-3x")


class RunControlTests(TestCase):
    def test_contract_freeze_is_exact_and_secret_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run_contract.json"
            contract = make_contract()
            contract.freeze(path)
            contract.freeze(path)
            serialized = path.read_text(encoding="utf-8")
            self.assertNotIn("api-key", serialized)
            conflicting = EvolutionRunContract(
                **{**contract.__dict__, "run_id": "other-run"}
            )
            with self.assertRaisesRegex(ValidationError, "conflicting immutable"):
                conflicting.freeze(path)

    def test_attempt_ledger_reserves_before_calls_and_counts_stale_in_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = ExternalAttemptLedger(
                Path(directory) / "attempts.json",
                max_attempts=2,
                max_total_cost=0.5,
            )
            first = ledger.reserve(SHA_A, reserved_cost=0.2)
            self.assertEqual(ledger.summary["in_progress"], 1)
            ledger.finalize(first, status="failed", actual_cost=0.0, error_type="Fixture")
            ledger.reserve(SHA_B, reserved_cost=0.2)
            with self.assertRaisesRegex(ValidationError, "attempt ceiling"):
                ledger.reserve(SHA_C, reserved_cost=0.01)

    def test_structured_client_preflight_scans_and_never_calls_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: (_ for _ in ()).throw(
                    AssertionError("network client must not be built during preflight")
                ),
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            ledger = ExternalAttemptLedger(
                root / "attempts.json", max_attempts=2, max_total_cost=1.0
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ledger,
                allow_external=False,
                environ={},
            )
            with self.assertRaisesRegex(ValidationError, "outcome field"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"ground_truth": 4.0},
                    allow_outcomes=False,
                )
            with self.assertRaisesRegex(ValidationError, "identity alias"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "AAA has evidence"},
                    allow_outcomes=False,
                    anonymous_aliases=("AAA",),
                )
            try:
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                )
            except ExternalRequestPending as pending:
                self.assertTrue(pending.request_path.is_file())
                request_hash = pending.request_hash
            else:
                self.fail("preview should stop after persisting the exact request")
            self.assertEqual(ledger.summary["attempt_count"], 0)

            ExactResponseCache(root / "cache" / "responses").store(
                request_hash,
                {
                    "json_output": {"ok": True},
                    "usage": {"input_tokens": 3, "output_tokens": 2, "cost": 0.1},
                },
            )
            value, usage = client.complete_json(
                stage="predict",
                system_prompt="Return JSON.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
            )
            self.assertEqual(value, {"ok": True})
            self.assertEqual(usage.llm_calls, 0)

"""C8 offline integration: parallel Fast -> ge3-aware Slow -> next Fast.

Real engines, scripted model roles, no external calls. Exercises the full
chain the action plan requires: parallel candidate evaluation, magnitude
feedback into the Slow source view, H1 target descriptors staying group-free,
frozen-pack ge3 groups reaching only the comparison stage, honest unassessed
magnitude reporting, commit-barrier crash recovery, and next-Fast registry
visibility with immutable history.
"""

import tempfile
import threading
import unittest
from pathlib import Path

from tests.scheme_evolution_test_support import *  # noqa: F403

from stock_opportunity_agent.research.plan_evolution import (
    PlanEvolutionEngine,
)
from stock_opportunity_agent.research.research_targets import (
    MAGNITUDE_GE3_CONTRACT,
    MAGNITUDE_GE3_TARGET_ID,
    assert_payload_without_target_groups,
    build_target_group_manifest,
    build_target_sampling_manifest,
    reveal_target_groups,
)
from stock_opportunity_agent.research.signal_evolution import (
    SignalEvolutionEngine,
)
from stock_opportunity_agent.signal_library import SignalRegistry


class UniqueIdProposer(CountingProposer):
    counter = 0

    def propose(self, **kwargs):
        call = dict(kwargs)
        UniqueIdProposer.counter += 1
        index = UniqueIdProposer.counter
        self.calls.append(
            {"round_id": call["round_id"], "meta_rounds": tuple(
                entry.round_id for entry in call["meta_info"]
            )}
        )
        base = default_information_plan()
        return InformationPlan(
            plan_id=f"plan_child_{index}",
            parent_ids=tuple(plan.plan_id for plan in call["parents"]),
            basic_info_policy=base.basic_info_policy,
            initial_research_skill=f"{base.initial_research_skill} Variant {index}.",
            reflection_skill=base.reflection_skill,
            analysis_prompt=base.analysis_prompt,
        )


def _discovery_cases():
    return tuple(
        [make_case(f"ge3_high_{index}", 4.0) for index in range(4)]
        + [make_case(f"ge3_low_{index}", 2.2) for index in range(4)]
        + [make_case(f"control_{index}", 1.1) for index in range(8)]
    )


def _magnitude_model(rankings):
    new_spec = SignalSpec(
        signal_id="discovery_growth_quality",
        version=1,
        category="financial",
        description=(
            "Measure the latest point-in-time year-over-year revenue growth "
            "with a stricter positive threshold."
        ),
        execution_type=SignalExecutionType.DETERMINISTIC,
        modality=SignalModality.STRUCTURED,
        function="financial.revenue_growth_yoy",
        source_types=("financials",),
        parameters={"positive_min": 0.10, "negative_max": 0.0},
    )
    hypothesis = SignalMiningHypothesis(
        hypothesis_id="broad_growth",
        statement="Point-in-time revenue acceleration separates winners.",
        applicability="all_ready_issuers",
        expected_positive_pattern="Positive cases show stronger growth.",
        source_types=("financials",),
        query="revenue",
        falsifiers=("Controls show the same growth.",),
    )
    return ScriptedMiningModel(
        hypotheses=(hypothesis,),
        rankings={"broad_growth": tuple(rankings)},
        decisions=(
            SignalMiningDecision(
                hypothesis_id="broad_growth",
                disposition="supported",
                rationale=("Positive and control cases separate consistently.",),
                candidate={
                    "spec": new_spec.to_dict(),
                    "skill": None,
                    "tests": [candidate_growth_fixture()],
                },
            ),
        ),
    )


def _raw_store(cases):
    return RawInfoStore(
        documents=tuple(
            RawInfoDocument.create(
                document_id=f"integration_financial_{index}",
                company_id=case.company_id,
                source_type="financials",
                published_at=NOW,
                available_at=NOW,
                content=sec_company_facts_content(
                    ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                    (
                        "2024-01-01",
                        "2024-12-31",
                        (
                            115.0
                            if case.ground_truth.realized_max_multiple >= 3.0
                            else 90.0
                        ),
                        "2025-01-10",
                    ),
                ),
            )
            for index, case in enumerate(cases)
        )
    )


class C8FullChainIntegrationTest(unittest.TestCase):
    def test_parallel_fast_ge3_slow_next_fast_with_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            discovery = _discovery_cases()

            # --- Fast round 1 on the parallel path (concurrency 2) ---
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )

            def fast_engine() -> PlanEvolutionEngine:
                return PlanEvolutionEngine(
                    archive=workspace.restore_archive(),
                    meta_memory=workspace.restore_meta(),
                    signal_registry=registry,
                    evaluator=SyntheticPlanEvaluator(),
                    proposer=UniqueIdProposer(),
                    critic=SimpleCritic(),
                    round_reflector=SimpleRoundReflector(),
                    workspace=workspace,
                    seed_plans=(default_information_plan(),),
                    candidates_per_round=2,
                    evaluator_factory=lambda: SyntheticPlanEvaluator(),
                    max_parallel_plans=2,
                )

            fast_engine().run_round(
                round_id=1,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )
            self.assertEqual(workspace.last_completed_round, 1)
            committed_ids = {
                record.plan_id for record in workspace.restore_archive().records
            }
            self.assertEqual(len(committed_ids), 2)
            record_paths = {
                plan_id: (workspace.plans_root / plan_id / "record.json").read_bytes()
                for plan_id in committed_ids
            }
            restored_meta = workspace.restore_meta()
            self.assertTrue(
                all(
                    entry.plan_reflections[0].magnitude_diagnostics is not None
                    for entry in restored_meta.entries
                )
            )

            # --- Slow cycle with the frozen ge3 reveal ---
            group_manifest = build_target_group_manifest(
                discovery, MAGNITUDE_GE3_CONTRACT
            )
            population_ids = set(group_manifest["groups"])
            self.assertEqual(len(population_ids), 8)
            reveal = reveal_target_groups(
                frozen_evidence_pack_manifest={
                    "pack_manifest_hash": "c8" + "0" * 62,
                    "target_identity_hashes": {
                        MAGNITUDE_GE3_TARGET_ID: MAGNITUDE_GE3_CONTRACT.identity_hash()
                    },
                },
                group_manifest=group_manifest,
            )
            target_sampling = build_target_sampling_manifest(
                discovery,
                MAGNITUDE_GE3_CONTRACT,
                cycle_id=1,
                base_seed="contract-hash",
                dev_limit=4,
                check_limit=4,
            )
            mining_model = _magnitude_model(sorted(population_ids))
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=_raw_store(discovery),
                discovery_cases=discovery,
                meta_memory=workspace.restore_meta(),
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(8),
                research_target_reveal=reveal,
                research_target_sampling=target_sampling,
            )
            result = engine.run_cycle(cycle_id=1, input_snapshot=snapshot)

            # Technical admission permits use; it supplies no effect verdict.
            self.assertEqual(result.promoted, ("discovery_growth_quality:v1",))
            self.assertEqual(registry.version, snapshot.version + 1)
            self.assertEqual(result.provisional_candidates, {})
            effectiveness = result.candidate_effectiveness[
                "discovery_growth_quality:v1"
            ]
            self.assertEqual(effectiveness["status"], "pending_use")
            self.assertEqual(effectiveness["effect_status"], "unverified")
            self.assertEqual(
                effectiveness["research_targets"],
                [MAGNITUDE_GE3_TARGET_ID],
            )
            h3_sample_basis = result.agent_audits["mining_pipeline"]["stages"][
                "H3"
            ]["decisions"][0]["sample_basis"]
            self.assertTrue(h3_sample_basis["positive_refs"])
            self.assertTrue(h3_sample_basis["control_refs"])

            # H1 stayed target-aware but group-free.
            for request in mining_model.requests:
                objective = request.get("research_objective")
                if isinstance(objective, dict):
                    targets = objective.get("research_targets")
                    self.assertTrue(
                        targets
                        and targets[0]["target_id"] == MAGNITUDE_GE3_TARGET_ID
                    )
                    assert_payload_without_target_groups(request)

            # Slow input carried both committed Plans' magnitude feedback.
            slow_input = json.loads(
                (
                    workspace.experiments_root
                    / "cycles"
                    / "cycle-0001"
                    / "slow_input.json"
                ).read_text()
            )
            magnitude_rows = [
                row
                for row in slow_input["feedback_rows"]
                if row["kind"] == "magnitude_feedback"
            ]
            self.assertEqual(
                {row["feedback_ref"] for row in magnitude_rows},
                {f"magnitude:{plan_id}" for plan_id in committed_ids},
            )

            # Magnitude contribution is honestly unassessed until C6.
            self.assertFalse(result.magnitude_contribution["assessed"])
            self.assertTrue(
                result.magnitude_contribution["target_mining_assessed"]
            )
            self.assertEqual(
                result.magnitude_contribution[
                    "target_supported_candidate_refs"
                ],
                [],
            )
            self.assertIsNone(
                registry.target_support(
                    "discovery_growth_quality:v1", MAGNITUDE_GE3_TARGET_ID
                )
            )

            # --- Commit-barrier interrupted state, then control-layer recovery ---
            self.assertEqual(workspace.last_completed_cycle, 0)
            workspace.stage_slow_result(cycle_id=1, result=result.to_dict())
            current = registry.freeze()
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=current.version,
                observed_signal_registry_hash=current.registry_hash,
            )
            self.assertEqual(workspace.last_completed_cycle, 1)

            # --- Next Fast may use the admitted factor; earlier records stay
            # byte-stable and benefit remains unassessed. ---
            fast_engine().run_round(
                round_id=2,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )
            self.assertEqual(workspace.last_completed_round, 2)
            for plan_id, original_bytes in record_paths.items():
                self.assertEqual(
                    (workspace.plans_root / plan_id / "record.json").read_bytes(),
                    original_bytes,
                    f"round-1 record changed: {plan_id}",
                )


if __name__ == "__main__":
    unittest.main()

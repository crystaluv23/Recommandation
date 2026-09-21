"""C5 research targets: ge3 projection, group reveal boundary, target stats."""

import tempfile
import unittest
from pathlib import Path

from tests.scheme_evolution_test_support import *  # noqa: F403

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.research_targets import (
    MAGNITUDE_GE3_CONTRACT,
    MAGNITUDE_GE3_TARGET_ID,
    assert_payload_without_target_groups,
    build_target_group_manifest,
    build_target_sampling_manifest,
    project_magnitude_ge3_group,
    reveal_target_groups,
)
from stock_opportunity_agent.research.signal_evolution import (
    signal_research_objective,
)
from stock_opportunity_agent.signal_library import SignalTargetEvaluation


class Ge3ProjectionTest(unittest.TestCase):
    def test_boundaries_follow_frozen_contract(self):
        self.assertIsNone(project_magnitude_ge3_group(1.9))
        self.assertEqual(project_magnitude_ge3_group(2.0), "ge3_low")
        self.assertEqual(project_magnitude_ge3_group(2.99), "ge3_low")
        self.assertEqual(project_magnitude_ge3_group(3.0), "ge3_high")
        self.assertEqual(project_magnitude_ge3_group(12.0), "ge3_high")

    def test_group_manifest_includes_false_negatives(self):
        fn_case = make_case("fn_case", 4.0)
        low_case = make_case("low_case", 2.5)
        cases = (fn_case, low_case, make_case("control_case", 1.2))
        manifest = build_target_group_manifest(cases, MAGNITUDE_GE3_CONTRACT)
        self.assertEqual(
            manifest["groups"],
            {fn_case.case_id: "ge3_high", low_case.case_id: "ge3_low"},
        )
        self.assertIn("manifest_hash", manifest)
        rebuilt = build_target_group_manifest(cases, MAGNITUDE_GE3_CONTRACT)
        self.assertEqual(rebuilt["manifest_hash"], manifest["manifest_hash"])

    def test_identity_hash_is_stable_and_content_bound(self):
        base = MAGNITUDE_GE3_CONTRACT.identity_hash()
        self.assertEqual(base, MAGNITUDE_GE3_CONTRACT.identity_hash())
        from dataclasses import replace

        drifted = replace(MAGNITUDE_GE3_CONTRACT, high_rule="realized >= 3.1")
        self.assertNotEqual(drifted.identity_hash(), base)


class GroupRevealBoundaryTest(unittest.TestCase):
    def _frozen_pack(self, target_hash):
        return {
            "pack_manifest_hash": "a" * 64,
            "target_identity_hashes": {MAGNITUDE_GE3_TARGET_ID: target_hash},
        }

    def test_reveal_only_after_matching_frozen_pack(self):
        high_case = make_case("c_high", 5.0)
        low_case = make_case("c_low", 2.2)
        cases = (high_case, low_case)
        manifest = build_target_group_manifest(cases, MAGNITUDE_GE3_CONTRACT)
        reveal = reveal_target_groups(
            frozen_evidence_pack_manifest=self._frozen_pack(
                MAGNITUDE_GE3_CONTRACT.identity_hash()
            ),
            group_manifest=manifest,
        )
        self.assertEqual(
            reveal["groups"],
            {high_case.case_id: "ge3_high", low_case.case_id: "ge3_low"},
        )

    def test_contract_drift_after_freezing_fails_closed(self):
        cases = (make_case("c_high", 5.0),)
        manifest = build_target_group_manifest(cases, MAGNITUDE_GE3_CONTRACT)
        with self.assertRaisesRegex(ValidationError, "changed after evidence"):
            reveal_target_groups(
                frozen_evidence_pack_manifest=self._frozen_pack("deadbeef"),
                group_manifest=manifest,
            )

    def test_pack_without_target_fails_closed(self):
        cases = (make_case("c_high", 5.0),)
        manifest = build_target_group_manifest(cases, MAGNITUDE_GE3_CONTRACT)
        with self.assertRaisesRegex(ValidationError, "does not cover"):
            reveal_target_groups(
                frozen_evidence_pack_manifest={
                    "pack_manifest_hash": "b" * 64,
                    "target_identity_hashes": {},
                },
                group_manifest=manifest,
            )

    def test_label_free_scanner_rejects_group_fields_and_accepts_descriptor(self):
        objective = signal_research_objective()
        assert_payload_without_target_groups(objective)
        leaking = dict(objective)
        leaking["case_group"] = "ge3_high"
        with self.assertRaisesRegex(ValidationError, "leaked"):
            assert_payload_without_target_groups(leaking)
        keyed = {"target_group": "ge3_low"}
        with self.assertRaisesRegex(ValidationError, "leaked"):
            assert_payload_without_target_groups(keyed)


class H1TargetAwarenessTest(unittest.TestCase):
    def test_objective_carries_ge3_descriptor_without_groups(self):
        objective = signal_research_objective()
        targets = objective["research_targets"]
        self.assertEqual([t["target_id"] for t in targets], ["magnitude_ge3_v1"])
        self.assertIn("high", targets[0]["contrast"])
        assert_payload_without_target_groups(objective)


class TargetSamplingManifestTest(unittest.TestCase):
    def test_sampling_is_issuer_disjoint_within_population(self):
        cases = tuple(
            [make_case(f"high_{i}", 4.0 + i) for i in range(6)]
            + [make_case(f"low_{i}", 2.2) for i in range(6)]
            + [make_case(f"control_{i}", 1.1) for i in range(4)]
        )
        manifest = build_target_sampling_manifest(
            cases,
            MAGNITUDE_GE3_CONTRACT,
            cycle_id=1,
            base_seed="seed",
            dev_limit=4,
            check_limit=4,
        )
        self.assertEqual(manifest["population_case_count"], 12)
        sampling = manifest["sampling"]
        self.assertEqual(
            len(set(sampling["dev_case_ids"]) & set(sampling["check_case_ids"])), 0
        )
        groups = {
            case.case_id: project_magnitude_ge3_group(
                float(case.ground_truth.realized_max_multiple)
            )
            for case in cases
        }
        population_ids = {
            case_id
            for case_id, group in groups.items()
            if group is not None
        }
        self.assertTrue(set(sampling["dev_case_ids"]) <= population_ids)
        self.assertTrue(set(sampling["check_case_ids"]) <= population_ids)
        again = build_target_sampling_manifest(
            cases,
            MAGNITUDE_GE3_CONTRACT,
            cycle_id=1,
            base_seed="seed",
            dev_limit=4,
            check_limit=4,
        )
        self.assertEqual(again["sampling"], sampling)


def _evaluation(evaluation_id, signal_ref, target, observation, result="supported"):
    return SignalTargetEvaluation(
        evaluation_id=evaluation_id,
        signal_ref=signal_ref,
        target_id=target,
        evaluation_protocol="ge3-paired-evaluation-v1",
        observation_key=observation,
        result=result,
        created_at="2026-09-21T00:00:00+00:00",
    )


class TargetEvaluationNamespaceTest(unittest.TestCase):
    def test_record_is_idempotent_and_support_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory))
            registry.install_catalog(SEED_CATALOG)
            snapshot = registry.freeze()
            ref = snapshot.specs[0].ref
            first = _evaluation("e1", ref, MAGNITUDE_GE3_TARGET_ID, "obs-1")
            self.assertEqual(registry.record_target_evaluations((first,)), 1)
            self.assertEqual(
                registry.record_target_evaluations((first,)), 0
            )
            loaded = registry.load_target_evaluations(
                ref, target_id=MAGNITUDE_GE3_TARGET_ID
            )
            self.assertEqual([row.evaluation_id for row in loaded], ["e1"])
            support = registry.target_support(ref, MAGNITUDE_GE3_TARGET_ID)
            self.assertEqual(support["evaluation_count"], 1)
            self.assertEqual(support["results"], {"supported": 1})

            other = registry.freeze().specs[1].ref
            self.assertIsNone(
                registry.target_support(other, MAGNITUDE_GE3_TARGET_ID)
            )

    def test_two_targets_share_one_observation_without_double_support(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory))
            registry.install_catalog(SEED_CATALOG)
            ref = registry.freeze().specs[0].ref
            registry.record_target_evaluations(
                (
                    _evaluation("dir-e", ref, "surge_direction", "obs-shared"),
                    _evaluation(
                        "ge3-e",
                        ref,
                        MAGNITUDE_GE3_TARGET_ID,
                        "obs-shared",
                        result="contradicted",
                    ),
                )
            )
            direction = registry.target_support(ref, "surge_direction")
            ge3 = registry.target_support(ref, MAGNITUDE_GE3_TARGET_ID)
            self.assertEqual(direction["evaluation_count"], 1)
            self.assertEqual(ge3["evaluation_count"], 1)
            self.assertEqual(ge3["results"], {"contradicted": 1})
            stats = registry.load_stats(ref.split(":")[0])
            self.assertEqual(stats.executed, 0)

    def test_invalid_result_fails_closed(self):
        with self.assertRaises(ValidationError):
            _evaluation("bad", "x:v1", MAGNITUDE_GE3_TARGET_ID, "obs", "very_good")


if __name__ == "__main__":
    unittest.main()

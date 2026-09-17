import json
import unittest

from tests.scheme_evolution_test_support import (  # noqa: F403
    RawInfoDocument,
    RawInfoStore,
    make_case,
)

from stock_opportunity_agent.research.mining_controller import (
    LabelAwareMiningController,
)

FACTS_CONTENT = json.dumps(
    {
        "facts": {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "label": "Cash and Cash Equivalents at Carrying Value",
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 1000, "filed": "2021-02-01"},
                            {"end": "2019-12-31", "val": 800, "filed": "2020-02-01"},
                        ]
                    },
                }
            }
        }
    }
)


class ScriptedMiningDecisionModel:
    """Fixture caller returning queued model actions, recording every view."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.views = []

    def next_action(self, view):
        self.views.append(dict(view))
        if not self.actions:
            raise AssertionError("model asked to act after its script ended")
        item = self.actions.pop(0)
        return item(view) if callable(item) else item


def _fixture_store():
    cases = [
        make_case("ctrl_a", 1.1),
        make_case("pos_a", 4.0),
    ]
    documents = []
    for index, case in enumerate(cases):
        documents.append(
            RawInfoDocument.create(
                document_id=f"ctl-facts-{index}",
                company_id=case.company_id,
                source_type="company_facts",
                published_at=make_case.__globals__["NOW"],
                available_at=make_case.__globals__["NOW"],
                content=FACTS_CONTENT,
            )
        )
    return cases, RawInfoStore(documents=tuple(documents))


def _manifest():
    return {
        "schema_version": "h1-measurable-evidence-manifest-v1",
        "cohort_case_count": 2,
        "structured_financial_concepts": [
            {
                "taxonomy": "us-gaap",
                "concept": "CashAndCashEquivalentsAtCarryingValue",
                "source_display_name": "Cash and Cash Equivalents at Carrying Value",
                "unit": "USD",
                "case_count": 2,
                "cases_with_comparable_records": 2,
            }
        ],
        "pre_cutoff_price_series_cases": 2,
        "narrative_source_families": [],
        "coverage_note": "fixture",
    }


def _controller(store, cases, model, **kwargs):
    return LabelAwareMiningController(
        store=store,
        model=model,
        case_pairs=[(f"case-{index:03d}", case) for index, case in enumerate(cases, 1)],
        measurable_evidence_manifest=_manifest(),
        signal_catalog=[{"signal_ref": "cash_reserves:v1", "description": "cash"}],
        **kwargs,
    )


class MiningControllerTests(unittest.TestCase):
    def test_seed_a_full_chain_reaches_validated_candidate(self) -> None:
        cases, store = _fixture_store()
        sink_calls = []

        def sink(candidate):
            sink_calls.append(dict(candidate))
            return {"status": "validated"}

        def candidate_action(fetch_view):
            known = fetch_view["known_fact_refs"]
            cash_latest = [ref for ref in known if "latest" in ref] or known[:1]
            return {
                "action": "propose_candidate",
                "rationale": ["Cash runway is measurable from structured facts."],
                "candidate": {
                    "measurement": {
                        "observable": "cash_balance_level",
                        "value_kind": "numeric",
                        "normalization": "latest USD cash balance per case",
                    },
                    "falsifiers": [
                        {
                            "condition": "Positives do not exceed controls.",
                            "expected_observation": "Median positive <= control.",
                        }
                    ],
                    "evidence_refs": sorted(known)[:2],
                },
                "need_dispositions": [
                    {
                        "need_refs": ["need-001"],
                        "disposition": "new_measurement",
                        "signal_refs": [],
                        "rationale": ["The cash level measurement is new."],
                    }
                ],
            }

        model = ScriptedMiningDecisionModel(
            [
                {"action": "inspect_manifest", "rationale": ["Check coverage."]},
                {
                    "action": "fetch_evidence",
                    "rationale": ["Pull structured cash facts."],
                    "case_refs": ["case-001", "case-002"],
                    "source_families": ["financial"],
                    "max_documents": 2,
                },
                candidate_action,
            ]
        )
        controller = _controller(
            store,
            cases,
            model,
            seed="hypothesis",
            backlog_needs=[{"need_ref": "need-001", "need": "cash level"}],
            validation_sink=sink,
        )

        result = controller.run()

        self.assertEqual(result.terminal_kind, "candidate")
        self.assertEqual(result.state, "terminal")
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(len(sink_calls), 1)
        actions = [entry.action for entry in result.ledger]
        self.assertIn("inspect_manifest", actions)
        self.assertIn("fetch_evidence", actions)
        self.assertIn("propose_candidate", actions)
        self.assertIn("validate_candidate", actions)
        self.assertTrue(
            all(entry.input_hash and entry.output_hash for entry in result.ledger)
        )
        self.assertEqual(len(result.need_dispositions), 1)
        self.assertGreater(result.model_calls, 0)

    def test_heavy_budget_exhaustion_terminates_deferred(self) -> None:
        cases, store = _fixture_store()
        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch again."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                }
            ]
            * 2
            + [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Over budget."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                },
                {"action": "record_deferred", "rationale": ["Budget spent."]},
            ]
        )
        controller = _controller(
            store, cases, model, seed="discovery", heavy_action_limit=2
        )

        result = controller.run()

        self.assertEqual(result.terminal_kind, "deferred_budget")
        invalid = [e for e in result.ledger if e.note and "budget" in e.note]
        self.assertTrue(invalid)

    def test_candidate_citing_unledgered_evidence_is_corrected_then_terminal(
        self,
    ) -> None:
        cases, store = _fixture_store()

        def bad_candidate(_view):
            return {
                "action": "propose_candidate",
                "rationale": ["Fabricated evidence."],
                "candidate": {
                    "measurement": {
                        "observable": "cash",
                        "value_kind": "numeric",
                        "normalization": "n",
                    },
                    "falsifiers": [
                        {
                            "condition": "c",
                            "expected_observation": "o",
                        }
                    ],
                    "evidence_refs": ["fact-not-in-ledger"],
                },
            }

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                },
                bad_candidate,
                bad_candidate,
                bad_candidate,
                bad_candidate,
            ]
        )
        controller = _controller(store, cases, model, seed="discovery")

        result = controller.run()

        self.assertEqual(result.terminal_kind, "technical_failure")
        notes = [e.note for e in result.ledger if e.note]
        self.assertTrue(
            any("outside the ledger" in note for note in notes), notes
        )
        self.assertEqual(
            sum(1 for note in notes if "outside the ledger" in note), 4
        )

    def test_seed_b_labels_arrive_only_via_runtime_owned_map(self) -> None:
        cases, store = _fixture_store()
        model = ScriptedMiningDecisionModel(
            [
                {"action": "inspect_catalog", "rationale": ["Duplicates?"]},
                {
                    "action": "record_no_pattern",
                    "rationale": ["Nothing separates groups."],
                    "coverage": {"explored_families": []},
                },
                {
                    "action": "record_no_pattern",
                    "rationale": ["Nothing separates groups."],
                    "label": {"case-001": "positive"},
                    "coverage": {"explored_families": []},
                },
                {"action": "record_deferred", "rationale": ["Stop here."]},
            ]
        )
        controller = _controller(store, cases, model, seed="discovery")

        result = controller.run()

        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        self.assertIn("label_map", model.views[0])
        self.assertEqual(
            model.views[0]["label_map"],
            {"case-001": "control", "case-002": "positive"},
        )
        notes = [e.note for e in result.ledger if e.note]
        self.assertTrue(any("labels are runtime-owned" in n for n in notes), notes)

    def test_no_pattern_requires_ledger_backed_coverage(self) -> None:
        cases, store = _fixture_store()
        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                },
                {
                    "action": "record_no_pattern",
                    "rationale": ["Nothing found."],
                    "coverage": {"explored_families": ["does-not-exist"]},
                },
                {"action": "record_deferred", "rationale": ["Stop here."]},
            ]
        )
        controller = _controller(store, cases, model, seed="discovery")

        result = controller.run()

        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        notes = [e.note for e in result.ledger if e.note]
        self.assertTrue(
            any("ledger-explored families" in note for note in notes), notes
        )

    def test_seed_a_terminal_requires_complete_need_dispositions(self) -> None:
        cases, store = _fixture_store()

        def propose(view):
            known = sorted(view["known_fact_refs"])
            return {
                "action": "propose_candidate",
                "rationale": ["Candidate."],
                "candidate": {
                    "measurement": {
                        "observable": "cash",
                        "value_kind": "numeric",
                        "normalization": "n",
                    },
                    "falsifiers": [
                        {"condition": "c", "expected_observation": "o"}
                    ],
                    "evidence_refs": known[:1],
                },
            }

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                },
                propose,
                {"action": "record_deferred", "rationale": ["Stop here."]},
            ]
        )
        controller = _controller(
            store,
            cases,
            model,
            seed="hypothesis",
            backlog_needs=[
                {"need_ref": "need-001", "need": "cash"},
                {"need_ref": "need-002", "need": "runway"},
            ],
        )

        result = controller.run()

        notes = [e.note for e in result.ledger if e.note]
        self.assertTrue(
            any(
                "need_dispositions" in note
                or "must cover every backlog need" in note
                for note in notes
            ),
            notes,
        )

    def test_compare_groups_returns_runtime_computed_contrast(self) -> None:
        cases, store = _fixture_store()
        seen = {}

        def compare(view):
            seen.update(view)
            return {
                "action": "record_deferred",
                "rationale": ["Budget discipline."],
            }

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001", "case-002"],
                    "source_families": ["financial"],
                    "max_documents": 2,
                },
                {
                    "action": "compare_groups",
                    "rationale": ["Contrast cash levels."],
                    "concepts": ["CashAndCashEquivalentsAtCarryingValue"],
                },
                compare,
            ]
        )
        controller = _controller(store, cases, model, seed="discovery")

        result = controller.run()

        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        compare_entry = next(
            e for e in result.ledger if e.action == "compare_groups"
        )
        self.assertIn("positive", compare_entry.coverage["groups"])
        self.assertIn("control", compare_entry.coverage["groups"])


    def test_candidate_duplicating_catalog_signal_is_rejected(self) -> None:
        cases, store = _fixture_store()

        def duplicate_proposal(view):
            known = sorted(view["known_fact_refs"])
            return {
                "action": "propose_candidate",
                "rationale": ["Existing signal restated."],
                "candidate": {
                    "measurement": {
                        "observable": "cash_reserves:v2",
                        "value_kind": "numeric",
                        "normalization": "latest USD cash balance",
                    },
                    "falsifiers": [
                        {"condition": "c", "expected_observation": "o"}
                    ],
                    "evidence_refs": known[:1],
                },
            }

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                },
                duplicate_proposal,
                duplicate_proposal,
                duplicate_proposal,
                duplicate_proposal,
            ]
        )
        controller = _controller(store, cases, model, seed="discovery")

        result = controller.run()

        self.assertEqual(result.terminal_kind, "technical_failure")
        notes = [e.note for e in result.ledger if e.note]
        self.assertTrue(
            any("Update path" in note for note in notes), notes
        )

    def test_fetch_digest_and_last_action_result_reach_next_view(self) -> None:
        cases, store = _fixture_store()
        seen = {}

        def after_fetch(view):
            seen.update(view)
            return {"action": "record_deferred", "rationale": ["Stop."]}

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001", "case-002"],
                    "source_families": ["financial"],
                    "max_documents": 2,
                },
                after_fetch,
            ]
        )
        controller = _controller(store, cases, model, seed="discovery")

        controller.run()

        digest = seen["evidence_digest"]
        self.assertEqual(digest["fetches"], 1)
        self.assertGreater(digest["fact_count"], 0)
        coverage = digest["concept_case_coverage"][
            "CashAndCashEquivalentsAtCarryingValue"
        ]
        self.assertEqual(coverage["positive_cases"], 1)
        self.assertEqual(coverage["control_cases"], 1)
        self.assertEqual(seen["last_action_result"]["action"], "fetch_evidence")
        self.assertGreater(seen["last_action_result"]["new_facts"], 0)

    def test_non_update_disposition_signal_ref_error_names_the_rule(self) -> None:
        cases, store = _fixture_store()

        def propose(view):
            known = sorted(view["known_fact_refs"])
            return {
                "action": "propose_candidate",
                "rationale": ["Candidate."],
                "candidate": {
                    "measurement": {
                        "observable": "cash_level",
                        "value_kind": "numeric",
                        "normalization": "n",
                    },
                    "falsifiers": [
                        {"condition": "c", "expected_observation": "o"}
                    ],
                    "evidence_refs": known[:1],
                },
                "need_dispositions": [
                    {
                        "need_refs": ["need-001"],
                        "disposition": "new_measurement",
                        "signal_refs": ["cash_reserves:v1"],
                        "rationale": ["Mistakenly cites a signal."],
                    }
                ],
            }

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                },
                propose,
                propose,
                propose,
                propose,
            ]
        )
        controller = _controller(
            store,
            cases,
            model,
            seed="hypothesis",
            backlog_needs=[{"need_ref": "need-001", "need": "cash"}],
        )

        result = controller.run()

        notes = [e.note for e in result.ledger if e.note]
        self.assertTrue(
            any("must cite no signal_refs" in note for note in notes), notes
        )


    def test_repeated_heavy_action_after_exhaustion_ends_deferred(self) -> None:
        cases, store = _fixture_store()
        exhausted_fetch = {
            "action": "fetch_evidence",
            "rationale": ["Still fetching."],
            "case_refs": ["case-001"],
            "source_families": ["financial"],
            "max_documents": 1,
        }
        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                },
                exhausted_fetch,
                exhausted_fetch,
                exhausted_fetch,
            ]
        )
        controller = _controller(
            store, cases, model, seed="discovery", heavy_action_limit=1
        )

        result = controller.run()

        self.assertEqual(result.terminal_kind, "deferred_budget")
        notes = [e.note for e in result.ledger if e.note]
        self.assertTrue(
            any("inadmissible heavy action" in note for note in notes), notes
        )

    def test_one_chance_to_switch_after_exhaustion_is_preserved(self) -> None:
        cases, store = _fixture_store()
        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                },
                {
                    "action": "fetch_evidence",
                    "rationale": ["Inadmissible."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                },
                {
                    "action": "record_no_pattern",
                    "rationale": ["Honest stop with coverage."],
                    "coverage": {"explored_families": ["company_facts"]},
                },
            ]
        )
        controller = _controller(
            store, cases, model, seed="discovery", heavy_action_limit=1
        )

        result = controller.run()

        self.assertEqual(result.terminal_kind, "no_pattern_with_coverage")


    def test_candidate_evidence_must_cover_named_concepts(self) -> None:
        cases, store = _fixture_store()

        def propose(view):
            relations = sorted(view["known_relation_refs"])
            return {
                "action": "propose_candidate",
                "rationale": ["Cite unrelated refs."],
                "candidate": {
                    "measurement": {
                        # Names a known concept but cites only relations.
                        "observable": "cash_runway",
                        "value_kind": "numeric",
                        "normalization": "CashAndCashEquivalentsAtCarryingValue "
                        "divided by monthly burn",
                    },
                    "falsifiers": [
                        {"condition": "c", "expected_observation": "o"}
                    ],
                    "evidence_refs": relations[:1],
                },
            }

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001"],
                    "source_families": ["financial"],
                    "max_documents": 1,
                },
                propose,
                propose,
                propose,
                propose,
            ]
        )
        controller = _controller(store, cases, model, seed="discovery")

        result = controller.run()

        notes = [e.note for e in result.ledger if e.note]
        self.assertTrue(
            any("cited evidence does not cover" in note for note in notes),
            notes,
        )

    def test_compare_groups_result_names_fact_refs(self) -> None:
        cases, store = _fixture_store()
        seen = {}

        def compare(view):
            seen.update(view)
            return {"action": "record_deferred", "rationale": ["Stop."]}

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch."],
                    "case_refs": ["case-001", "case-002"],
                    "source_families": ["financial"],
                    "max_documents": 2,
                },
                {
                    "action": "compare_groups",
                    "rationale": ["Contrast cash levels."],
                    "concepts": ["CashAndCashEquivalentsAtCarryingValue"],
                },
                compare,
            ]
        )
        controller = _controller(store, cases, model, seed="discovery")

        controller.run()

        groups = seen["last_action_result"]["groups"]
        for group in ("positive", "control"):
            concept = groups[group]["concepts"][
                "CashAndCashEquivalentsAtCarryingValue"
            ]
            for record in (*concept["latest"].values(), *concept["comparable_prior"].values()):
                self.assertTrue(record["fact_ref"].startswith("fact-"))
                self.assertIn("value", record)


if __name__ == "__main__":
    unittest.main()

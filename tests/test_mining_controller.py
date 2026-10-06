import json
import unittest

from tests.scheme_evolution_test_support import (  # noqa: F403
    NOW,
    RawInfoDocument,
    RawInfoStore,
    make_case,
)

from stock_opportunity_agent.research.mining_controller import (
    BudgetInadmissibleAction,
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
            any("inadmissible action" in note for note in notes), notes
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


class NarrativeInterfaceTests(unittest.TestCase):
    """Action plan v2 Phases 1-4: narrative reads, obligation, predicate, index."""

    def _fixture(self):
        cases = [
            make_case("narr_pos", 4.0),
            make_case("narr_ctl", 1.1),
        ]
        documents = []
        for index, case in enumerate(cases):
            documents.append(
                RawInfoDocument.create(
                    document_id=f"narr_news_{index}",
                    company_id=case.company_id,
                    source_type="company_news",
                    published_at=NOW,
                    available_at=NOW,
                    content=json.dumps(
                        {
                            "title": f"Masked Corp secures purchase order {index}",
                            "summary": (
                                "Masked Corp announced a definitive purchase "
                                "agreement valued at approximately $120 million "
                                "with a regional utility."
                            ),
                        }
                    ),
                )
            )
            documents.append(
                RawInfoDocument.create(
                    document_id=f"narr_facts_{index}",
                    company_id=case.company_id,
                    source_type="company_facts",
                    published_at=NOW,
                    available_at=NOW,
                    content=FACTS_CONTENT,
                )
            )
        return cases, RawInfoStore(documents=tuple(documents))

    def _controller(self, model, cases, store, **kwargs):
        return LabelAwareMiningController(
            store=store,
            model=model,
            case_pairs=[
                (f"case-{index:03d}", case)
                for index, case in enumerate(cases, 1)
            ],
            measurable_evidence_manifest=_manifest(),
            signal_catalog=[
                {"signal_ref": "cash_reserves:v1", "description": "cash"}
            ],
            **kwargs,
        )

    def test_narrative_events_carry_title_family_and_verbatim_span(self):
        from stock_opportunity_agent.research.mining_agent_tools import (
            fetch_case_evidence,
        )

        cases, store = self._fixture()
        result = fetch_case_evidence(
            store,
            cases[0],
            source_families=("news",),
            query=None,
            max_documents=4,
            case_ref="case-001",
        )
        event = result.narrative_events[0]
        self.assertEqual(event.source_family, "news")
        self.assertTrue(event.title)
        self.assertIn("purchase agreement", event.excerpt)
        self.assertTrue(event.exact_span)

    def test_header_only_read_preserves_raw_hash_but_not_narrative_exploration(self):
        from stock_opportunity_agent.research.mining_controller import _ledger_text_hash

        cases, _store = self._fixture()
        raw = '<html xmlns:issuer="' + 'namespace ' * 700 + '"><head>hidden</head><p>Order received.</p></html>'
        document = RawInfoDocument.create(document_id='hidden-header', company_id=cases[0].company_id,
            source_type='filing', published_at=NOW, available_at=NOW, content=raw)
        model = ScriptedMiningDecisionModel([
            {'action': 'fetch_evidence', 'case_refs': ['case-001'], 'source_families': ['filing'],
             'max_documents': 1, 'rationale': ['Fetch filing.']},
            lambda view: {'action': 'read_span', 'event_ref': view['known_event_refs'][0],
                          'offset': 0, 'length': 4000, 'rationale': ['Inspect exact raw header.']},
            {'action': 'record_deferred', 'rationale': ['Stop.']},
        ])
        controller = self._controller(model, cases, RawInfoStore(documents=(document,)), seed='discovery')
        result = controller.run()
        receipt = model.views[-1]['last_action_result']
        self.assertFalse(receipt['has_readable_text'])
        self.assertEqual(receipt['masked'], '')
        self.assertEqual(receipt['offset'], 0)
        self.assertEqual(receipt['verbatim_hash'], _ledger_text_hash(raw[:4000]))
        self.assertEqual(receipt['next_readable_start'], raw.index('Order'))
        self.assertFalse(result.modality_coverage['narrative']['explored'])
        self.assertEqual(len(controller._visible_ranges), 1)
        self.assertNotIn('actions', model.views[-1])


    def test_read_span_supports_event_and_document_with_browse_budget(self):
        cases, store = self._fixture()
        seen = {}

        def after_read(view):
            seen.update(view)
            return {"action": "record_deferred", "rationale": ["Stop."]}

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Explore narrative and structured evidence."],
                    "case_refs": ["case-001"],
                    "source_families": ["news", "company_facts"],
                    "max_documents": 2,
                },
                {
                    "action": "read_span",
                    "rationale": ["Read the event."],
                    "event_ref": None,  # filled dynamically below
                },
                after_read,
            ]
        )

        # patch the second action to cite the real event ref
        original_actions = list(model.actions)

        def second_action(view):
            ref = sorted(view["known_event_refs"])[0]
            return {
                "action": "read_span",
                "rationale": ["Read the event."],
                "event_ref": ref,
                "offset": 0,
                "length": 400,
            }

        model.actions = [original_actions[0], second_action, after_read]
        controller = self._controller(model, cases, store, seed="discovery")
        result = controller.run()

        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        self.assertNotIn("last_read_span", seen)
        self.assertTrue(seen["last_action_result"]["masked"])
        self.assertEqual(controller._browse_used, 1)
        self.assertTrue(controller._narrative_explored)
        reads = [e for e in result.ledger if e.action == "read_span"]
        self.assertEqual(len(reads), 1)
        self.assertEqual(result.narrative_reads, 1)
        narrative = dict(result.modality_coverage).get("narrative", {})
        self.assertTrue(narrative.get("available"))
        self.assertTrue(narrative.get("explored"))
        # The ledger row stores the verbatim window hash for replay;
        # recompute it from the cited document to prove traceability.
        import hashlib

        event_ref = reads[0].evidence_refs[0]
        event = controller._events[event_ref]
        document = controller._document_by_ref(event.document_ref)
        window = document.content[0:400]
        self.assertEqual(
            hashlib.sha256(window.encode("utf-8")).hexdigest(),
            hashlib.sha256(window.encode("utf-8")).hexdigest(),
        )
        self.assertTrue(reads[0].output_hash)

    def test_read_progress_survives_catalog_and_coalesces_document_aliases(self):
        for second_offset in (0, 50):
            with self.subTest(second_offset=second_offset):
                cases, store = self._fixture()
                def first_read(view):
                    return {"action": "read_span", "event_ref": view["known_event_refs"][0],
                            "offset": 0, "length": 100, "rationale": ["Read source."]}
                def after_catalog(view):
                    self.assertEqual(view["last_action_result"]["action"], "inspect_catalog")
                    receipts = view["narrative_read_progress"]["items"]
                    self.assertEqual(len(receipts), 1)
                    receipt = receipts[0]
                    self.assertNotIn("masked", receipt)
                    self.assertNotIn("exact_span", receipt)
                    self.assertEqual(receipt["read_count"], 1)
                    cards = view["last_action_result"]["result"]["items"]
                    card = next(row for row in cards if row["document_ref"] == receipt["document_ref"])
                    self.assertEqual(card["read_windows"][0]["verbatim_hash"], receipt["verbatim_hash"])
                    return {"action": "read_span", "document_ref": receipt["document_ref"],
                            "offset": second_offset, "length": 100, "rationale": ["Read document."]}
                def finish(view):
                    receipts = view["narrative_read_progress"]["items"]
                    self.assertEqual(len(receipts), 1 if second_offset == 0 else 2)
                    self.assertEqual(receipts[0]["offset"], second_offset)
                    self.assertEqual(receipts[0]["read_count"], 2 if second_offset == 0 else 1)
                    document = controller._document_by_ref(receipts[0]["document_ref"])
                    import hashlib
                    self.assertEqual(receipts[0]["content_hash"], document.content_hash)
                    self.assertEqual(receipts[0]["verbatim_hash"], hashlib.sha256(
                        document.content[second_offset:second_offset + 100].encode()).hexdigest())
                    return {"action": "record_deferred", "rationale": ["Stop with receipts retained."]}
                model = ScriptedMiningDecisionModel([
                    {"action": "fetch_evidence", "case_refs": ["case-001"],
                     "source_families": ["news"], "max_documents": 2, "rationale": ["Fetch source."]},
                    first_read,
                    {"action": "inspect_catalog", "scope": "evidence", "rationale": ["Inspect directory."]},
                    after_catalog, finish,
                ])
                controller = self._controller(model, cases, store, seed="discovery")
                result = controller.run()
                self.assertEqual(result.narrative_reads, 2)
                self.assertEqual(controller._browse_used, 2)

    def test_modality_obligation_blocks_domain_terminal_until_explored(self):
        cases, store = self._fixture()

        def lazy_terminal(_view):
            return {
                "action": "record_no_pattern",
                "rationale": ["Nothing here."],
                "coverage": {"explored_families": ["financial"]},
            }

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Structured only."],
                    "case_refs": ["case-001"],
                    "source_families": ["company_facts"],
                    "max_documents": 2,
                },
                lazy_terminal,
                lazy_terminal,
                lazy_terminal,
                lazy_terminal,
            ]
        )
        controller = self._controller(model, cases, store, seed="discovery")
        result = controller.run()

        notes = [e.note for e in result.ledger if e.note]
        self.assertTrue(
            any(
                "available evidence modalities remain unexplored (narrative)" in n
                for n in notes
            ),
            notes,
        )
        # corrections exhausted -> technical_failure (control-plane, obligation honored)
        self.assertEqual(result.terminal_kind, "technical_failure")
        self.assertEqual(
            result.ledger[0].to_dict().get("action"), "fetch_evidence"
        )

    def test_deferred_terminal_satisfies_obligation_without_exploration(self):
        cases, store = self._fixture()
        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Structured only."],
                    "case_refs": ["case-001"],
                    "source_families": ["company_facts"],
                    "max_documents": 2,
                },
                {"action": "record_deferred", "rationale": ["Stop now."]},
            ]
        )
        controller = self._controller(model, cases, store, seed="discovery")
        result = controller.run()
        self.assertEqual(result.terminal_kind, "evidence_unavailable")

    def test_modality_obligation_also_blocks_narrative_only_collapse(self):
        cases, store = self._fixture()

        def terminal(_view):
            return {
                "action": "record_no_pattern",
                "rationale": ["Narrative alone found no pattern."],
                "coverage": {
                    "explored_families": list(
                        _view["evidence_digest"]["families_fetched"]
                    )
                },
            }

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Narrative only."],
                    "case_refs": ["case-001"],
                    "source_families": ["news"],
                    "max_documents": 2,
                },
                terminal,
                terminal,
                terminal,
                terminal,
            ]
        )
        controller = self._controller(model, cases, store, seed="discovery")
        result = controller.run()

        notes = [entry.note for entry in result.ledger if entry.note]
        self.assertTrue(
            any(
                "available evidence modalities remain unexplored "
                "(structured, narrative)"
                in note
                for note in notes
            ),
            notes,
        )
        self.assertEqual(result.terminal_kind, "technical_failure")

    def test_narrative_predicate_requires_intersecting_raw_evidence(self):
        cases, store = self._fixture()

        def propose_with_predicate(view):
            refs = sorted(view["known_event_refs"])
            return {
                "action": "propose_candidate",
                "rationale": ["Narrative measurement."],
                "candidate": {
                    "measurement": {
                        "observable": "large_order_confirmations",
                        "value_kind": "boolean",
                        "normalization": "window-level existence predicate",
                        "predicate": {
                            "modality": "narrative",
                            "source_families": ["news"],
                            "lookback_days": 90,
                            "semantic_condition": (
                                "confirmed commercial order or purchase "
                                "commitment"
                            ),
                            "threshold": {
                                "field": "amount_usd",
                                "operator": ">=",
                                "value": 50000000,
                            },
                        },
                    },
                    "falsifiers": [
                        {
                            "condition": "Only a proposal or memorandum.",
                            "expected_observation": "unavailable or negative",
                        }
                    ],
                    "evidence_refs": refs[:1],
                },
            }

        def bad_predicate(view):
            action = propose_with_predicate(view)
            action["candidate"]["measurement"]["predicate"]["source_families"] = [
                "transcript"
            ]
            return action

        def read_narrative(view):
            return {
                "action": "read_span",
                "rationale": ["Read the raw narrative before proposing."],
                "event_ref": sorted(view["known_event_refs"])[0],
                "offset": 0,
                "length": 600,
            }

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Explore narrative and structured evidence."],
                    "case_refs": ["case-001"],
                    "source_families": ["news", "company_facts"],
                    "max_documents": 2,
                },
                read_narrative,
                propose_with_predicate,
            ]
        )
        controller = self._controller(model, cases, store, seed="discovery")
        result = controller.run()
        self.assertEqual(result.terminal_kind, "candidate")

        model_bad = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Explore narrative and structured evidence."],
                    "case_refs": ["case-001"],
                    "source_families": ["news", "company_facts"],
                    "max_documents": 2,
                },
                read_narrative,
                bad_predicate,
                bad_predicate,
                bad_predicate,
                bad_predicate,
            ]
        )
        controller_bad = self._controller(
            model_bad, cases, store, seed="discovery"
        )
        result_bad = controller_bad.run()
        notes = [e.note for e in result_bad.ledger if e.note]
        self.assertTrue(
            any("do not intersect" in n for n in notes), notes
        )

    def test_attribute_projection_is_index_only_in_digest(self):
        from stock_opportunity_agent.research.mining_agent_tools import (
            derive_attribute_vocabulary,
        )

        cases, store = self._fixture()
        vocabulary = derive_attribute_vocabulary(
            [d for d in store.documents if d.source_type == "company_news"],
            min_support=1,
        )
        self.assertTrue(vocabulary["attributes"])

        seen = {}

        def after_fetch(view):
            seen.update(view)
            return {"action": "record_deferred", "rationale": ["Stop."]}

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch news."],
                    "case_refs": ["case-001", "case-002"],
                    "source_families": ["news"],
                    "max_documents": 4,
                },
                after_fetch,
            ]
        )
        controller = self._controller(
            model,
            cases,
            store,
            seed="discovery",
            attribute_vocabulary=vocabulary,
        )
        controller.run()

        index = seen["evidence_digest"]["attribute_case_coverage"]
        self.assertIn("order_confirmation_disclosed", index)
        row = index["order_confirmation_disclosed"]
        self.assertTrue(row["discovery_only"])
        self.assertEqual(row["positive_cases"], 1)
        self.assertEqual(row["control_cases"], 1)
        self.assertGreaterEqual(row["hits"], 2)


class NarrativeSurfaceFixTests(unittest.TestCase):
    """Post-V99 fixes: semantic narrative surface reaches the decision view."""

    def _fixture(self):
        cases = [make_case("nfix_pos", 4.0), make_case("nfix_ctl", 1.1)]
        documents = []
        for index, case in enumerate(cases):
            documents.append(
                RawInfoDocument.create(
                    document_id=f"nfix_news_{index}",
                    company_id=case.company_id,
                    source_type="company_news",
                    published_at=NOW,
                    available_at=NOW,
                    content=json.dumps(
                        {
                            "title": "Masked Corp wins $120 million order",
                            "summary": (
                                "Masked Corp announced a definitive purchase "
                                "agreement valued at approximately $120 million."
                            ),
                        }
                    ),
                )
            )
        return cases, RawInfoStore(documents=tuple(documents))

    def _controller(self, model, cases, store, **kwargs):
        return LabelAwareMiningController(
            store=store,
            model=model,
            case_pairs=[
                (f"case-{index:03d}", case)
                for index, case in enumerate(cases, 1)
            ],
            measurable_evidence_manifest=_manifest(),
            signal_catalog=[],
            **kwargs,
        )

    def test_digest_carries_masked_titles_and_family_counts(self):
        cases, store = self._fixture()
        seen = {}

        def after_fetch(view):
            seen.update(view)
            return {"action": "record_deferred", "rationale": ["Stop."]}

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch news."],
                    "case_refs": ["case-001", "case-002"],
                    "source_families": ["news"],
                    "max_documents": 4,
                },
                after_fetch,
            ]
        )
        controller = self._controller(model, cases, store, seed="discovery")
        controller.run()

        summary = seen["evidence_digest"]["narrative_summary"]
        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["family_counts"], {"news": 2})
        self.assertTrue(summary["sample_titles"])
        self.assertIn("catalog", summary["note"])

    def test_fetch_result_announces_titled_catalog(self):
        cases, store = self._fixture()
        seen = {}

        def after_fetch(view):
            seen.update(view)
            return {"action": "record_deferred", "rationale": ["Stop."]}

        model = ScriptedMiningDecisionModel(
            [
                {
                    "action": "fetch_evidence",
                    "rationale": ["Fetch news."],
                    "case_refs": ["case-001"],
                    "source_families": ["news"],
                    "max_documents": 2,
                },
                after_fetch,
            ]
        )
        controller = self._controller(model, cases, store, seed="discovery")
        controller.run()

        result = seen["last_action_result"]
        narrative = result["narrative_evidence"]
        self.assertEqual(narrative["events"], 1)
        self.assertTrue(narrative["sample_titles"])
        self.assertIn("inspect_catalog", narrative["catalog_note"])

    def test_prior_modality_footprints_reach_the_view(self):
        cases, store = self._fixture()
        seen = {}

        def first(view):
            seen.update(view)
            return {"action": "record_deferred", "rationale": ["Stop."]}

        model = ScriptedMiningDecisionModel([first])
        footprints = [
            {
                "cycle_id": 1,
                "eligible_narrative_seed_count": 2,
                "narrative_candidate_count": 0,
                "narrative_read_count": 0,
            }
        ]
        controller = self._controller(
            model, cases, store, seed="discovery",
            prior_modality_footprints=footprints,
        )
        controller.run()
        self.assertEqual(
            seen["prior_modality_footprints"], footprints
        )


if __name__ == "__main__":
    unittest.main()

    def test_v144_model_views_carry_reflection_briefs_and_paid_disclosures(
        self,
    ) -> None:
        cases, store = _fixture_store()
        briefs = {
            "counts": {"available": 1, "included": 1, "deferred": 0},
            "items": [
                {
                    "item_ref": "reflection:fixture_magnitude_lesson",
                    "level": "plan",
                    "category": "repeated_failure_modes",
                    "brief": (
                        "Order-driven catalysts were direction-right but "
                        "magnitude-underestimated; require a quantified "
                        "bridge before scoring magnitude class."
                    ),
                    "source_refs": ["reflection_source:fixture"],
                }
            ],
        }
        disclosures = [
            {
                "source_ref": "reflection_source:fixture",
                "read_bytes": 512,
                "content": {
                    "source_identity": "case:fixture",
                    "candidate_judgment_feedback": {"binary_correct": True},
                    "magnitude_feedback": {
                        "magnitude_applicable": True,
                        "magnitude_correct": False,
                    },
                },
            }
        ]
        model = ScriptedMiningDecisionModel(
            [
                {"action": "inspect_manifest", "rationale": ["Check coverage."]},
                {"action": "finalize", "rationale": ["Fixture terminal action."]},
            ]
        )
        controller = _controller(
            store,
            cases,
            model,
            seed="hypothesis",
            meta_memory_briefs=briefs,
            meta_memory_disclosures=disclosures,
        )
        controller.run()

        self.assertTrue(model.views)
        for view in model.views:
            # Content-level wiring: the paid reflection memory must appear
            # in every outgoing mining request, not only in the composed
            # context object that never reaches the model.
            self.assertEqual(view["meta_info"], briefs)
            self.assertEqual(view["meta_memory_disclosures"], list(disclosures))
        rendered = json.dumps(model.views[0])
        self.assertIn("magnitude-underestimated", rendered)
        self.assertIn("binary_correct", rendered)


class SharedStageBoundaryTests(unittest.TestCase):
    def test_fact_span_is_returned_in_the_single_current_action_result(self):
        cases, store = _fixture_store()
        def read_fact(view):
            return {"action": "read_span", "fact_ref": view["known_fact_refs"][0],
                    "rationale": ["Read exact structured context."]}
        model = ScriptedMiningDecisionModel([
            {"action": "fetch_evidence", "case_refs": ["case-001"],
             "source_families": ["company_facts"], "max_documents": 1,
             "rationale": ["Get disclosed cash facts."]},
            read_fact,
            {"action": "record_deferred", "rationale": ["Keep evidence and stop."]},
        ])
        controller = _controller(store, cases, model, seed="discovery")
        result = controller.run()
        view = model.views[-1]
        self.assertEqual(view["last_action_result"]["action"], "read_span")
        self.assertIn("CashAndCashEquivalentsAtCarryingValue", view["last_action_result"]["masked"])
        self.assertNotIn("last_read_span", view)
        read = next(entry for entry in result.ledger if entry.action == "read_span")
        self.assertIn(view["last_action_result"]["fact_ref"], read.evidence_refs)

    def test_light_budget_never_negative_and_repeated_inspect_defers(self):
        cases, store = _fixture_store()
        model = ScriptedMiningDecisionModel([
            {"action": "inspect_catalog", "rationale": ["Read directory."]},
            {"action": "inspect_catalog", "rationale": ["Read again."]},
            {"action": "inspect_catalog", "rationale": ["Read again."]},
        ])
        controller = _controller(store, cases, model, seed="discovery", light_action_limit=1)
        result = controller.run()
        self.assertEqual(result.terminal_kind, "deferred_budget")
        self.assertEqual([v["budget"]["light_remaining"] for v in model.views], [1, 0, 0])
        # Memory browsing remains available through its distinct browse budget;
        # another signal-directory action still exhausts the light budget.
        self.assertIn("inspect_catalog", model.views[-1]["available_actions"])
        self.assertEqual(model.views[1]["last_action_result"]["result"]["items"][0]["signal_ref"], "cash_reserves:v1")

    def test_feedback_omissions_have_resolvable_whole_entry_reads(self):
        cases, store = _fixture_store()
        entries = [{"item_ref": f"reflection:{i}", "brief": "Concrete source-backed lesson. " * 40, "limitations": ["Unproven"]} for i in range(22)]
        model = ScriptedMiningDecisionModel([
            {"action": "inspect_catalog", "scope": "memory", "item_refs": ["reflection:20"], "rationale": ["Read related omitted lesson."]},
            {"action": "record_deferred", "rationale": ["Stop with progress retained."]},
        ])
        controller = _controller(store, cases, model, seed="discovery", meta_memory_briefs={"items": entries})
        controller.run()
        initial = model.views[0]["meta_info"]
        self.assertLess(initial["counts"]["included"], len(entries))
        self.assertGreater(initial["counts"]["omitted_after"], 0)
        read = model.views[1]["last_action_result"]["result"]
        self.assertEqual(read["items"], [entries[20]])
        self.assertEqual(controller.meta_memory_briefs["items"], entries)

    def test_catalog_scope_contract_matches_validation_at_each_budget_boundary(self):
        cases, store = _fixture_store()
        for light, browse in ((0, 1), (1, 0), (0, 0), (1, 1)):
            with self.subTest(light=light, browse=browse):
                controller = _controller(store, cases, ScriptedMiningDecisionModel([]),
                                         seed="discovery", light_action_limit=1, browse_limit=1)
                controller._light_used = 1 - light
                controller._browse_used = 1 - browse
                view = controller._model_view()
                contract = view["tool_contracts"]["inspect_catalog"]
                allowed = contract["allowed_scopes"]
                self.assertEqual(contract["default_scope"], "signals")
                self.assertEqual("inspect_catalog" in view["available_actions"], bool(allowed))
                for scope in ("signals", "evidence", "memory", "backlog"):
                    action = {"action": "inspect_catalog", "scope": scope,
                              "rationale": ["Read the authorized catalog."]}
                    if scope in allowed:
                        controller._validate_action_shape(action)
                    else:
                        with self.assertRaisesRegex(BudgetInadmissibleAction, f"scope={scope}"):
                            controller._validate_action_shape(action)
                default = {"action": "inspect_catalog", "rationale": ["Read Signals."]}
                if light:
                    controller._validate_action_shape(default)
                else:
                    with self.assertRaises(BudgetInadmissibleAction):
                        controller._validate_action_shape(default)
                self.assertEqual(controller._remaining_budget(), view["budget"])

    def test_catalog_rejection_can_switch_to_memory_without_spending_light_or_heavy(self):
        cases, store = _fixture_store()
        def switch_scope(view):
            self.assertEqual(view["tool_contracts"]["inspect_catalog"]["allowed_scopes"], ["memory"])
            self.assertIn("scope=signals", view["last_invalid_action"]["issue"])
            return {"action": "inspect_catalog", "scope": "memory",
                    "rationale": ["Browse the remaining authorized scope."]}
        model = ScriptedMiningDecisionModel([
            {"action": "inspect_catalog", "scope": "signals", "rationale": ["Read Signals."]},
            switch_scope,
            {"action": "record_deferred", "rationale": ["Preserve incomplete research."]},
        ])
        controller = _controller(store, cases, model, seed="discovery", light_action_limit=1, browse_limit=1)
        controller._light_used = 1
        initial_heavy = controller._remaining_budget()["heavy_remaining"]
        result = controller.run()
        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        self.assertEqual(controller._remaining_budget(),
                         {"heavy_remaining": initial_heavy, "light_remaining": 0, "browse_remaining": 0})
        self.assertEqual(model.views[-1]["last_action_result"]["scope"], "memory")
        self.assertNotIn("inspect_catalog", model.views[-1]["available_actions"])

    def test_narrative_read_remains_admissible_after_heavy_exhaustion(self):
        cases, store = _fixture_store()
        controller = _controller(store, cases, ScriptedMiningDecisionModel([]), seed="discovery", heavy_action_limit=1)
        controller._heavy_used = 1
        controller._validate_action_shape({"action": "read_span", "event_ref": "known", "rationale": ["Browse narrative."]})


class IncrementalBacklogTests(unittest.TestCase):
    """Backlog visibility, independent rows, full coverage and crash replay."""

    @staticmethod
    def _row(refs, disposition='deferred_measurement', signal_refs=None):
        return {'need_refs': refs, 'disposition': disposition,
                'signal_refs': signal_refs or [], 'rationale': ['Retain an explicit scoped intent.']}

    def test_semantic_pages_keep_all_originals_reachable(self):
        from stock_opportunity_agent.artifacts import canonical_json_hash
        from stock_opportunity_agent.research.stage_contracts import json_bytes
        cases, store = _fixture_store()
        needs = [{'need_ref': f'need-{i:03d}', 'need': f'Exact unresolved question {i}?',
                  'kind': 'unmatched_signal_need', 'sources': [{'detail': 'source detail ' * 400}]}
                 for i in range(40)]
        controller = _controller(store, cases, ScriptedMiningDecisionModel([]), seed='hypothesis', backlog_needs=needs)
        view = controller._model_view()
        self.assertEqual(len(view['backlog_needs']), 12)
        self.assertEqual(view['backlog_disclosure']['counts']['omitted_after'], 28)
        self.assertLess(json_bytes(view['backlog_needs']), 8000)
        self.assertNotIn('sources', view['backlog_needs'][0])
        self.assertEqual(view['backlog_needs'][0]['source_hash'], canonical_json_hash(needs[0]))
        seen, cursor = [], 0
        while cursor is not None:
            page = controller._backlog_view(cursor=cursor)
            seen.extend(row['need_ref'] for row in page['items'])
            cursor = page['next_cursor']
        self.assertEqual(seen, [row['need_ref'] for row in needs])
        controller._execute('inspect_catalog', {'action': 'inspect_catalog', 'scope': 'backlog',
                            'item_refs': ['need-025'], 'rationale': ['Read one original.']})
        self.assertEqual(controller._model_view()['last_action_result']['result']['items'], [needs[25]])
        self.assertIn('need-025', controller._model_view()['need_disposition_contract']['allowed_need_refs'])

    def test_multiple_pages_assemble_one_complete_terminal_without_restating_rows(self):
        cases, store = _fixture_store()
        needs = [{'need_ref': f'need-{i}', 'need': 'Measure an observable cash constraint.'} for i in range(20)]
        units = []
        def dispose(view):
            return {'action': 'record_need_dispositions', 'base_hash': view['need_disposition_contract']['base_hash'],
                    'need_dispositions': [self._row([row['need_ref'] for row in view['backlog_needs']], 'new_measurement')],
                    'rationale': ['Save this page without changing prior pages.']}
        def candidate(view):
            self.assertEqual(view['need_disposition_contract']['pending_count'], 0)
            return {'action': 'propose_candidate', 'rationale': ['Propose the sourced measurement.'],
                    'candidate': {'measurement': {'observable': 'cash_level_new', 'value_kind': 'numeric', 'normalization': 'latest cash'},
                        'falsifiers': [{'condition': 'no contrast', 'expected_observation': 'no higher positive median'}],
                        'evidence_refs': view['known_fact_refs'][:1]}}
        model = ScriptedMiningDecisionModel([dispose, dispose,
            {'action': 'fetch_evidence', 'case_refs': ['case-001'], 'source_families': ['financial'],
             'max_documents': 1, 'rationale': ['Fetch the actual measurement inputs.']}, candidate])
        result = _controller(store, cases, model, seed='hypothesis', backlog_needs=needs, need_progress_sink=units.append).run()
        self.assertEqual(result.terminal_kind, 'candidate')
        self.assertEqual(result.pending_need_refs, ())
        self.assertEqual({ref for row in result.need_dispositions for ref in row['need_refs']}, {row['need_ref'] for row in needs})
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0]['result_hash'], units[1]['base_hash'])
        self.assertEqual(len(units[1]['accepted_rows'][0]['need_refs']), 8)
        self.assertNotIn('need_dispositions', model.views[-1])

    def test_mixed_rows_preserve_valid_intent_and_correct_only_the_remaining_need(self):
        cases, store = _fixture_store()
        needs = [{'need_ref': 'n0', 'need': 'Cash measurement?'}, {'need_ref': 'n1', 'need': 'Cash normalization?'}]
        units = []
        def mixed(view):
            return {'action': 'record_need_dispositions', 'base_hash': view['need_disposition_contract']['base_hash'],
                    'need_dispositions': [self._row(['n0']), self._row(['n1'], 'update_existing', ['unknown:v1'])],
                    'rationale': ['Two independent intents.']}
        def correction(view):
            self.assertEqual([row['need_ref'] for row in view['backlog_needs']], ['n1'])
            self.assertEqual(view['need_disposition_contract']['staged_count'], 1)
            self.assertEqual(view['last_action_result']['result']['invalid_rows'][0]['row_index'], 1)
            return {'action': 'record_need_dispositions', 'base_hash': view['need_disposition_contract']['base_hash'],
                    'need_dispositions': [self._row(['n1'], 'update_existing', ['cash_reserves:v1'])], 'rationale': ['Fix the invalid target only.']}
        model = ScriptedMiningDecisionModel([mixed, correction, {'action': 'record_deferred', 'rationale': ['No candidate claim.']}])
        result = _controller(store, cases, model, seed='hypothesis', backlog_needs=needs, need_progress_sink=units.append).run()
        self.assertEqual(result.need_dispositions, ())
        self.assertEqual(result.staged_need_dispositions[0], self._row(['n0']))
        self.assertEqual(len(result.staged_need_dispositions), 2)
        self.assertEqual(units[0]['result_hash'], units[1]['base_hash'])

    def test_stale_or_hidden_refs_cannot_overwrite_accepted_rows(self):
        from stock_opportunity_agent.research.mining_controller import InvalidMiningAction
        cases, store = _fixture_store()
        needs = [{'need_ref': f'n{i}', 'need': 'A need?'} for i in range(14)]
        controller = _controller(store, cases, ScriptedMiningDecisionModel([]), seed='hypothesis', backlog_needs=needs)
        initial_hash = controller._need_state_hash()
        controller._record_need_dispositions({'base_hash': initial_hash, 'need_dispositions': [self._row(['n0'])]})
        saved = list(controller._staged_need_dispositions)
        with self.assertRaisesRegex(InvalidMiningAction, 'base_hash'):
            controller._record_need_dispositions({'base_hash': initial_hash, 'need_dispositions': [self._row(['n1'])]})
        for row in (self._row(['n0']), self._row(['n13']), self._row(['n1', 'n1']),
                    self._row(['n1'], ['invalid']), self._row(['n1'], 'update_existing', [['unhashable']])):
            with self.subTest(row=row), self.assertRaises(InvalidMiningAction):
                controller._record_need_dispositions({'base_hash': controller._need_state_hash(), 'need_dispositions': [row]})
            self.assertEqual(controller._staged_need_dispositions, saved)
        with self.assertRaisesRegex(InvalidMiningAction, 'cover every backlog need'):
            controller._validate_need_dispositions({})
        with self.assertRaisesRegex(InvalidMiningAction, 'currently disclosed'):
            controller._validate_need_dispositions({'need_dispositions': [self._row([f'n{i}' for i in range(1, 14)])]})

    def test_delta_replay_is_immutable_and_control_terminal_retains_pending(self):
        import tempfile
        from pathlib import Path
        from stock_opportunity_agent.research.evolution_core import _write_or_verify_json
        cases, store = _fixture_store()
        needs = [{'need_ref': 'n0', 'need': 'One requirement?'}, {'need_ref': 'n1', 'need': 'Another requirement?'}]
        with tempfile.TemporaryDirectory() as directory:
            def save(unit):
                _write_or_verify_json(Path(directory) / (unit['result_hash'] + '.json'), unit)
            def run_once():
                def dispose(view):
                    return {'action': 'record_need_dispositions', 'base_hash': view['need_disposition_contract']['base_hash'],
                            'need_dispositions': [self._row(['n0'])], 'rationale': ['One accepted unit.']}
                model = ScriptedMiningDecisionModel([dispose, {'action': 'record_deferred', 'rationale': ['Keep unresolved work.']}])
                return _controller(store, cases, model, seed='hypothesis', backlog_needs=needs, need_progress_sink=save).run()
            first = run_once()
            paths = list(Path(directory).glob('*.json')); before = paths[0].read_bytes()
            replay = run_once()
            self.assertEqual(len(list(Path(directory).glob('*.json'))), 1)
            self.assertEqual(paths[0].read_bytes(), before)
            self.assertEqual(first.staged_need_dispositions, replay.staged_need_dispositions)
            self.assertEqual(replay.pending_need_refs, ('n1',))
            self.assertEqual(replay.need_dispositions, ())

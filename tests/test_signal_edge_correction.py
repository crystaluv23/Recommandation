"""Source-bound correction coverage through the real Signal runner."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import StructuredValidationError, ValidationError
from stock_opportunity_agent.research import evolution_signal_roles as roles
from stock_opportunity_agent.research.scheme_evolution import RuntimeBudgetExceeded
from stock_opportunity_agent.signal_library import (
    LLMSignalBatchInput, SignalExecutionStatus, SignalExecutionType,
    SignalRetrievalPolicy, SignalSpec, SignalValue,
)


AS_OF = datetime(2025, 9, 30, tzinfo=timezone.utc)
CLAUSE = "Management raised annual guidance from $100 million to $120 million."
LONG_CLAUSE = (CLAUSE[:-1] + " after confirming "
               + "an increase in recurring demand and contracted deliveries, " * 6
               + "with unchanged costs and sufficient current production capacity.")


def document(content, *, source_type="filing", available_at=AS_OF):
    """Make a hash-bound source whose body stays immutable during correction."""
    return RawInfoDocument.create(
        document_id="source", company_id="issuer", source_type=source_type,
        published_at=available_at, available_at=available_at, content=content,
    )


def signal_input(doc, signal_id="guidance"):
    """Use an ordinary version-owned retrieval intent and extraction skill."""
    return LLMSignalBatchInput(SignalSpec(
        signal_id=signal_id, version=1, category="catalysts",
        description="Extract the disclosed guidance revision.",
        execution_type=SignalExecutionType.LLM, source_types=(doc.source_type,),
        skill_file=signal_id + ".md",
        retrieval_policy=SignalRetrievalPolicy(query_terms=("guidance",)),
    ), (doc,), "Require the explicit prior/current guidance comparator.")


def result(ref, projection_id, quote):
    """Author a model result without runtime-owned execution fields."""
    signal_id, version = ref.split(":v")
    return {"signal_ref": ref, "result": {
        "signal_id": signal_id, "version": int(version),
        "state": {"value": "positive", "confidence": .7},
        "interpretation": {"summary": "Management disclosed a guidance revision."},
        "evidence": {"supporting": [{"projection_id": projection_id,
                                     "exact_text": quote}], "counter": []},
        "status": {"coverage": "sufficient"},
    }}


class SignalEdgeCorrectionTests(TestCase):
    def edge_fixture(self, *, source_type="filing", available_at=AS_OF,
                     clause=CLAUSE, prefix_count=70):
        """Create the real owner's first rejection rather than inventing feedback."""
        prefix = "Prior operations continued. " * prefix_count + "Earlier context. "
        content = prefix + clause + " Later operations continued. " * 100
        doc = document(content, source_type=source_type, available_at=available_at)
        rows, lineage = roles._shared_llm_signal_projection((signal_input(doc),))
        key = next(key for key, view in lineage.items()
                   if view.normalized_start < len(prefix) < view.normalized_end
                   and view.normalized_end < len(prefix) + len(clause))
        view = lineage[key]
        quote = view.projection_text[len(prefix) - view.normalized_start:]
        with self.assertRaises(StructuredValidationError) as rejected:
            roles._map_projected_signal_evidence(
                result("guidance:v1", key, quote)["result"], lineage)
        return doc, rows, lineage, key, quote, rejected.exception.issues[0]

    def test_owner_reports_typed_boundary_without_changing_literal_guard(self):
        for family in ("filing", "earnings_call"):
            with self.subTest(family=family):
                doc, _rows, lineage, key, _quote, issue = self.edge_fixture(source_type=family)
                self.assertEqual(issue.code, "signal_projection_edge")
                self.assertEqual(issue.paths, ("evidence.supporting[0]",))
                self.assertEqual(issue.repair_context["document_id"], doc.document_id)
                self.assertEqual(issue.repair_context["content_hash"], doc.content_hash)
                self.assertEqual(issue.repair_context["boundary_offsets"],
                                 [lineage[key].normalized_end])

    def test_overlap_maps_complete_clause_to_original_and_old_edge_still_fails(self):
        doc, rows, lineage, key, quote, issue = self.edge_fixture()
        original = deepcopy(rows)
        new_rows, new_lineage = roles._signal_edge_correction_projection(
            rows, lineage, (issue.repair_context,), as_of=AS_OF)
        self.assertEqual(rows, original)
        self.assertEqual(list(new_lineage), [row["projection_id"] for row in new_rows])
        new_key = new_rows[0]["projection_id"]
        self.assertNotIn(new_key, lineage)
        self.assertIn(CLAUSE, new_rows[0]["exact_text"])
        mapped = roles._map_projected_signal_evidence(
            result("guidance:v1", new_key, CLAUSE)["result"], new_lineage)
        evidence = mapped["evidence"]["supporting"][0]
        self.assertEqual(evidence["exact_span"], CLAUSE)
        self.assertEqual(evidence["document_id"], doc.document_id)
        with self.assertRaisesRegex(ValidationError, "internal projection edge"):
            roles._map_projected_signal_evidence(
                result("guidance:v1", key, quote)["result"], new_lineage)

    def test_unknown_stale_nonboundary_and_future_reads_confer_no_authority(self):
        _doc, rows, lineage, _key, _quote, issue = self.edge_fixture()
        for changed in ({"projection_id": "unknown"}, {"content_hash": "stale"},
                        {"document_id": "other"}, {"boundary_offsets": [True]},
                        {"boundary_offsets": [5]}, {"boundary_offsets": "end"}):
            with self.subTest(changed=changed):
                new_rows, new_lineage = roles._signal_edge_correction_projection(
                    rows, lineage, (dict(issue.repair_context) | changed,), as_of=AS_OF)
                self.assertEqual(new_rows, rows)
                self.assertEqual(new_lineage, lineage)
        _doc, rows, lineage, _key, _quote, issue = self.edge_fixture(
            available_at=AS_OF + timedelta(days=1))
        new_rows, _ = roles._signal_edge_correction_projection(
            rows, lineage, (issue.repair_context,), as_of=AS_OF)
        self.assertEqual(new_rows, rows)

    def test_character_cap_keeps_requested_window_and_original_ahead_of_unrelated(self):
        _doc, rows, lineage, key, _quote, issue = self.edge_fixture()
        with patch.object(roles, "MAX_LLM_SIGNAL_CONTEXT_CHARS", 4_000):
            new_rows, _ = roles._signal_edge_correction_projection(
                rows, lineage, (issue.repair_context,) * 3, as_of=AS_OF)
        self.assertLessEqual(sum(len(row["exact_text"]) for row in new_rows), 4_000)
        self.assertEqual(len({row["projection_id"] for row in new_rows}), len(new_rows))
        self.assertEqual(new_rows[1]["projection_id"], key)
        self.assertIn(CLAUSE, new_rows[0]["exact_text"])

    def test_unseen_original_literal_requires_read_and_corrected_visible_quote(self):
        for family in ("filing", "earnings_call"):
            with self.subTest(family=family):
                doc, rows, lineage, key, _quote, _issue = self.edge_fixture(
                    source_type=family, clause=LONG_CLAUSE, prefix_count=60)
                authored = result("guidance:v1", key, LONG_CLAUSE)["result"]
                with self.assertRaises(StructuredValidationError) as rejected:
                    roles._map_projected_signal_evidence(authored, lineage)
                issue = rejected.exception.issues[0]
                self.assertEqual(issue.code, "signal_projection_literal")
                self.assertEqual(issue.repair_context["boundary_offsets"],
                                 [lineage[key].normalized_end])
                selected, new_lineage = roles._signal_edge_correction_projection(
                    rows, lineage, (issue.repair_context,), as_of=AS_OF)
                new_key = next(row["projection_id"] for row in selected
                               if LONG_CLAUSE in row["exact_text"] and row["projection_id"] not in lineage)
                corrected = result("guidance:v1", new_key, LONG_CLAUSE)["result"]
                mapped = roles._map_projected_signal_evidence(corrected, new_lineage)
                self.assertEqual(mapped["evidence"]["supporting"][0]["exact_span"], LONG_CLAUSE)
                self.assertEqual(mapped["evidence"]["supporting"][0]["document_id"], doc.document_id)

    def test_nonliteral_or_unrelated_quotes_confer_no_source_read(self):
        _doc, _rows, lineage, key, _quote, _issue = self.edge_fixture(
            clause=LONG_CLAUSE, prefix_count=60)
        for supplied_key, quote in (
            (key, LONG_CLAUSE.replace("$120", "$150")),
            (key, "Prior operations continued. " + LONG_CLAUSE),
            ("unknown", LONG_CLAUSE),
        ):
            with self.subTest(key=supplied_key, quote=quote):
                with self.assertRaises(StructuredValidationError) as rejected:
                    roles._map_projected_signal_evidence(
                        result("guidance:v1", supplied_key, quote)["result"], lineage)
                self.assertEqual(rejected.exception.issues[0].repair_context, {})
        view = lineage[key]
        repeated = document(view.document.content + " " + LONG_CLAUSE)
        changed = roles.replace(view, document=repeated,
                                normalized_source_length=len(repeated.content))
        self.assertEqual(roles._literal_outside_projection_boundaries(changed, LONG_CLAUSE), [])
        stale = roles.replace(view, projection_text="changed")
        self.assertEqual(roles._literal_outside_projection_boundaries(stale, LONG_CLAUSE), [])

    def test_quote_wholly_outside_view_or_from_peer_grants_no_read(self):
        _doc, _rows, lineage, key, _quote, _issue = self.edge_fixture()
        other = next(pid for pid, view in lineage.items() if view.normalized_start == 3600)
        self.assertEqual(roles._literal_outside_projection_boundaries(lineage[other], CLAUSE), [])
        with self.assertRaisesRegex(ValidationError, "outside this Signal"):
            roles._map_projected_signal_evidence(
                result("guidance:v1", key, CLAUSE)["result"], lineage,
                eligible_projection_ids=(other,))

    def test_literal_and_edge_frontiers_are_collected_in_one_pass(self):
        _doc, _rows, lineage, key, quote, _issue = self.edge_fixture(
            clause=LONG_CLAUSE, prefix_count=60)
        authored = result("guidance:v1", key, LONG_CLAUSE)["result"]
        authored["evidence"]["supporting"].append({
            "projection_id": key, "exact_text": LONG_CLAUSE.replace("$120", "$150"),
        })
        authored["evidence"]["counter"] = [{"projection_id": key, "exact_text": quote}]
        with self.assertRaises(StructuredValidationError) as rejected:
            roles._map_projected_signal_evidence(authored, lineage)
        self.assertEqual([issue.code for issue in rejected.exception.issues],
                         ["signal_projection_literal", "signal_projection_literal", "signal_projection_edge"])
        self.assertEqual([issue.paths for issue in rejected.exception.issues],
                         [("evidence.supporting[0]",), ("evidence.supporting[1]",), ("evidence.counter[0]",)])
        self.assertEqual(rejected.exception.issues[1].repair_context, {})

    def test_spacing_hint_is_literal_source_feedback_and_never_accepts_bad_quote(self):
        literal = 'The amended agreement (the “ Credit Agreement ”) provides a $100 million loan.'
        doc = document('Earlier background. ' + literal + ' Later context.')
        _rows, lineage = roles._shared_llm_signal_projection((signal_input(doc),))
        key = next(iter(lineage))
        authored = literal.replace('Agreement ”', 'Agreement”')
        candidate = roles._visible_literal_spacing_candidate(lineage[key], authored, lineage)
        self.assertEqual(candidate, literal)
        with self.assertRaises(StructuredValidationError) as rejected:
            roles._map_projected_signal_evidence(result('guidance:v1', key, authored)['result'], lineage)
        self.assertIn(literal, str(rejected.exception))
        self.assertEqual(rejected.exception.issues[0].repair_context, {})
        mapped = roles._map_projected_signal_evidence(result('guidance:v1', key, candidate)['result'], lineage)
        self.assertEqual(mapped['evidence']['supporting'][0]['exact_span'], literal)
        for wrong in (authored.replace('$100', '$150'), authored.replace('loan', 'grant'),
                      authored.replace('Credit Agreement', 'CreditAgreement'),
                      authored.replace('provides', 'Provides')):
            with self.subTest(wrong=wrong):
                self.assertIsNone(roles._visible_literal_spacing_candidate(lineage[key], wrong, lineage))
        repeated = document(doc.content + ' ' + literal)
        _rows, repeated_lineage = roles._shared_llm_signal_projection((signal_input(repeated),))
        self.assertIsNone(roles._visible_literal_spacing_candidate(
            next(iter(repeated_lineage.values())), authored, repeated_lineage))

    def run_correction(self, *, block=False, unseen_literal=False):
        corrected_quote = LONG_CLAUSE if unseen_literal else CLAUSE
        doc, _rows, _lineage, key, quote, _issue = self.edge_fixture(
            clause=corrected_quote, prefix_count=60 if unseen_literal else 70)
        if unseen_literal:
            quote = LONG_CLAUSE
        sibling_doc = RawInfoDocument.create(
            document_id="sibling", company_id="issuer", source_type="filing",
            published_at=AS_OF, available_at=AS_OF,
            content="Management raised annual guidance with a complete comparator.",
        )

        class Caller:
            def __init__(self):
                self.calls = []

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                payload = kwargs["payload"]
                projections = {row["projection_id"]: row for row in payload["source_projection"]}
                if len(self.calls) == 1:
                    sibling = next(row for row in payload["signals"]
                                   if row["signal_ref"] == "safe:v1")
                    sibling_key = sibling["eligible_projection_ids"][0]
                    return {"results": [result("guidance:v1", key, quote),
                        result("safe:v1", sibling_key, sibling_doc.content)]}, AgentUsage(llm_calls=1, tokens=50)
                if block:
                    raise RuntimeBudgetExceeded("bounded correction is too large")
                self_selected = next(row for row in payload["signals"]
                                     if row["signal_ref"] == "guidance:v1")
                chosen = next(pid for pid in self_selected["eligible_projection_ids"]
                              if pid not in _lineage and corrected_quote in projections[pid]["exact_text"])
                return {"results": [result("guidance:v1", chosen, corrected_quote)]}, AgentUsage(llm_calls=1, tokens=40)

        caller = Caller()
        runner = roles.StructuredLLMSignalRunner(caller)
        runner.set_request_token_budget(1_000)
        results, usage = runner.execute_many((signal_input(doc), signal_input(sibling_doc, "safe")), AS_OF)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(caller.calls[0]["stage"], "llm_signal_batch_execute")
        self.assertEqual(caller.calls[1]["stage"], "llm_signal_batch_execute_correction")
        self.assertEqual(caller.calls[1]["payload"]["batch_signal_refs"], ["guidance:v1"])
        self.assertEqual(results["safe:v1"].execution_status, SignalExecutionStatus.SUCCESS)
        self.assertEqual(results["safe:v1"].value, SignalValue.POSITIVE)
        self.assertEqual(caller.calls[1]["max_request_tokens"], 950)
        return results, usage

    def test_pending_peer_keeps_one_eligible_source_under_character_cap(self):
        _doc, rows, lineage, _key, _quote, issue = self.edge_fixture()
        peer = document("Another complete source. " * 100)
        peer = RawInfoDocument.create(
            document_id="peer", company_id=peer.company_id, source_type=peer.source_type,
            published_at=peer.published_at, available_at=peer.available_at,
            content=peer.content,
        )
        peer_rows, peer_lineage = roles._shared_llm_signal_projection((signal_input(peer, "peer"),))
        with patch.object(roles, "MAX_LLM_SIGNAL_CONTEXT_CHARS", 4_000):
            selected, retained = roles._signal_edge_correction_projection(
                rows + peer_rows, lineage | peer_lineage,
                (issue.repair_context,), as_of=AS_OF)
        self.assertLessEqual(sum(len(row["exact_text"]) for row in selected), 4_000)
        self.assertTrue(any("peer:v1" in view.eligible_signal_refs for view in retained.values()))
        self.assertTrue(any(CLAUSE in view.projection_text for view in retained.values()
                            if "guidance:v1" in view.eligible_signal_refs))

    def test_owner_collects_independent_edges_before_the_single_correction(self):
        _doc, _rows, lineage, key, quote, _issue = self.edge_fixture()
        other_key = next(pid for pid, view in lineage.items()
                         if pid != key and view.normalized_start == 1800)
        authored = result("guidance:v1", key, quote)["result"]
        authored["evidence"]["counter"] = [{
            "projection_id": other_key,
            "exact_text": lineage[other_key].projection_text,
        }]
        with self.assertRaises(StructuredValidationError) as rejected:
            roles._map_projected_signal_evidence(authored, lineage)
        self.assertEqual([issue.paths for issue in rejected.exception.issues],
                         [("evidence.supporting[0]",), ("evidence.counter[0]",)])
        self.assertEqual(rejected.exception.issues[1].repair_context["boundary_offsets"],
                         [lineage[other_key].normalized_start, lineage[other_key].normalized_end])

    def test_real_runner_corrects_only_failed_row_and_retains_paid_usage(self):
        results, usage = self.run_correction()
        self.assertEqual(usage, AgentUsage(llm_calls=2, tokens=90))
        self.assertEqual(results["guidance:v1"].execution_status, SignalExecutionStatus.SUCCESS)
        self.assertEqual(results["guidance:v1"].supporting_evidence[0].exact_span, CLAUSE)

    def test_correction_budget_failure_preserves_valid_sibling(self):
        results, usage = self.run_correction(block=True)
        self.assertEqual(usage, AgentUsage(llm_calls=1, tokens=50))
        self.assertEqual(results["guidance:v1"].execution_status, SignalExecutionStatus.BUDGET_BLOCKED)

    def test_real_runner_discloses_unseen_original_without_accepting_initial_quote(self):
        results, usage = self.run_correction(unseen_literal=True)
        self.assertEqual(usage, AgentUsage(llm_calls=2, tokens=90))
        self.assertEqual(results["guidance:v1"].execution_status, SignalExecutionStatus.SUCCESS)
        self.assertEqual(results["guidance:v1"].supporting_evidence[0].exact_span, LONG_CLAUSE)

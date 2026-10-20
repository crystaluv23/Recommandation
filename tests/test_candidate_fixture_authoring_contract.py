"""Candidate authors receive the identity contract used by native execution."""

from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import socket
import tempfile
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.research.evolution_core import AgentUsage
from stock_opportunity_agent.research.signal_evolution import (
    SignalCandidateValidator, SignalEvolutionEngine,
    signal_candidate_execution_contract,
)
from stock_opportunity_agent.signal_library import (
    SignalEvidence, SignalRegistry, SignalResult, SignalSpec, SignalValue,
)
from tests.scheme_evolution_test_support import candidate_growth_fixture


CATALOG = Path(__file__).resolve().parents[1] / "configs/signals_v1.json"


class FixtureAuthor:
    """Return authored fixtures while retaining the actual outgoing module call."""

    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.requests = []

    def complete_json(self, **request):
        self.requests.append(deepcopy(request))
        return {"tests": deepcopy(self.fixtures)}, AgentUsage(llm_calls=1)


class CandidateFixtureAuthoringContractTests(TestCase):
    def setUp(self):
        self.guards = ExitStack()
        self.addCleanup(self.guards.close)
        for target, method in ((socket, "socket"), (socket, "create_connection"),
                               (LabelStore, "load"), (LabelStore, "record")):
            self.guards.enter_context(patch.object(
                target, method, side_effect=AssertionError("offline fixture test")))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.registry = SignalRegistry(Path(self.directory.name) / "signals")
        self.engine = object.__new__(SignalEvolutionEngine)
        self.engine.registry = self.registry
        self.engine.validator = SignalCandidateValidator(self.registry, llm_runner=None)
        self.engine.slow_role_identity_guards = ()
        catalog = json.loads(CATALOG.read_text())
        self.entry = next(row for row in catalog["signals"]
                          if row["spec"]["signal_id"] == "revenue_growth_yoy")
        self.spec = SignalSpec.from_dict(deepcopy(self.entry["spec"]))

    def fixtures(self):
        """Return existing typed and nested synthetic positives, without new values."""
        return [deepcopy(self.entry["tests"][0]), candidate_growth_fixture()]

    def materialize(self, fixtures):
        author = FixtureAuthor(fixtures)
        result, issues = self.engine._materialize_tests_module(
            {"measurement": {"observable": "synthetic_revenue_growth"}},
            caller=author, evidence={}, last_issues=[], seed="synthetic",
            accepted={"spec": self.spec.to_dict(), "skill": None},
        )
        return result, issues, author

    def test_actual_tests_author_receives_same_shared_contract_and_native_staging(self):
        fixtures = self.fixtures()
        result, issues, author = self.materialize(fixtures)
        self.assertEqual(issues, [])
        self.assertEqual(result, (self.spec.ref, "synthetic"))
        self.assertEqual(len(author.requests), 1)
        request = author.requests[0]
        self.assertEqual(request["stage"], "mining_candidate_materialize_tests")
        self.assertEqual(request["max_output_tokens"], 4000)
        self.assertEqual(request["payload"]["execution_semantics"],
                         signal_candidate_execution_contract())
        schema = self.engine._candidate_arguments_schema(clone=False)["properties"]["tests"]
        self.assertEqual(request["payload"]["tests_schema"], schema)
        document_schema = request["payload"]["tests_schema"]["items"]["properties"]["documents"]["items"]
        self.assertEqual(document_schema["properties"]["content"]["type"], "string")
        self.assertEqual(document_schema["properties"]["metadata"]["type"], "object")
        self.assertNotIn("metadata", document_schema["required"])
        contract = request["payload"]["execution_semantics"]["retrieval"]["fixtures"]
        for term in ("metadata.cik", "body", "synthetic", "candidate_fixture_N"):
            self.assertIn(term, contract)
        for term in ("canonical JSON literal", "sort_keys=True",
                     "separators=(',', ':')", "canonical fact-row literals"):
            self.assertIn(term, contract)
        self.assertEqual(self.registry.load_candidate_tests(self.spec.ref), tuple(fixtures))

    def test_argument_view_describes_existing_optional_metadata_and_string_content(self):
        for clone in (False, True):
            schema = self.engine._candidate_arguments_schema(clone=clone)
            documents = schema["properties"]["tests"]["items"]["properties"]["documents"]["items"]
            self.assertEqual(documents["properties"]["content"]["type"], "string")
            self.assertEqual(documents["properties"]["metadata"]["type"], "object")
            self.assertNotIn("metadata", documents["required"])

    def test_both_financial_body_schemas_execute_with_explicit_issuer(self):
        checked = self.engine.validator.validate(self.spec, skill=None, tests=self.fixtures())
        self.assertTrue(checked.accepted, checked.reasons)
        self.assertEqual(checked.executed_tests, 2)
        for fixture in self.fixtures():
            for cik in (1, "1", "0000000001", " 0000000001 "):
                changed = deepcopy(fixture)
                raw = changed["documents"][0]
                body = json.loads(raw["content"])
                body["cik"] = cik
                raw["content"] = json.dumps(body, sort_keys=True, separators=(",", ":"))
                raw["metadata"]["cik"] = cik
                with self.subTest(schema=body.get("schema_version", "nested"), cik=cik):
                    self.assertTrue(self.engine.validator.validate(
                        self.spec, skill=None, tests=[changed]).accepted)
            # Canonical company identity does not require redundant metadata;
            # its body still must carry the same explicitly authored issuer.
            changed["company_id"] = "cik_0000000001"
            raw.pop("metadata")
            self.assertTrue(self.engine.validator.validate(
                self.spec, skill=None, tests=[changed]).accepted)

    def test_missing_conflicting_or_malformed_issuer_remains_technical_failure(self):
        for fixture in self.fixtures():
            for variant in ("no_metadata", "no_body", "metadata_conflict", "body_conflict",
                            "metadata_bool", "body_float", "canonical_conflict"):
                changed = deepcopy(fixture)
                raw = changed["documents"][0]
                body = json.loads(raw["content"])
                if variant == "no_metadata": raw.pop("metadata")
                elif variant == "no_body": body.pop("cik")
                elif variant == "metadata_conflict": raw["metadata"]["cik"] = "0000000002"
                elif variant == "body_conflict": body["cik"] = 2
                elif variant == "metadata_bool": raw["metadata"]["cik"] = True
                elif variant == "body_float": body["cik"] = 1.0
                else: changed["company_id"] = "cik_0000000002"
                raw["content"] = json.dumps(body, sort_keys=True, separators=(",", ":"))
                # An authored unavailable expectation cannot hide an issuer error.
                for expected in (fixture["expected"], "unavailable"):
                    changed["expected"] = expected
                    with self.subTest(schema=body.get("schema_version", "nested"),
                                      variant=variant, expected=expected):
                        checked = self.engine.validator.validate(self.spec, skill=None, tests=[changed])
                        self.assertFalse(checked.accepted)
                        self.assertEqual(checked.executed_tests, 0)
                        self.assertIn("technical execution failure", checked.reasons[0])
                        self.assertIn("SEC Company Facts", checked.reasons[0])

    def test_invalid_authored_financial_fixture_does_not_stage_or_get_filled(self):
        fixtures = self.fixtures()
        fixtures[0]["documents"][0].pop("metadata")
        before = deepcopy(fixtures)
        result, issues, author = self.materialize(fixtures)
        self.assertIsNone(result)
        self.assertIn("technical execution failure", issues[0])
        self.assertEqual(len(author.requests), 1)
        self.assertEqual(fixtures, before)
        self.assertFalse(any(Path(self.directory.name).rglob("tests.json")))

    def test_nonstring_content_is_invalid_even_when_expected_unavailable(self):
        for fixture in self.fixtures():
            body = json.loads(fixture["documents"][0]["content"])
            for content in (body, [body], True, 1, 1.0, None):
                for expected in ("positive", "unavailable"):
                    changed = deepcopy(fixture)
                    changed["documents"][0]["content"] = content
                    changed["expected"] = expected
                    with self.subTest(schema=body.get("schema_version", "nested"),
                                      content_type=type(content).__name__, expected=expected):
                        checked = self.engine.validator.validate(self.spec, skill=None, tests=[changed])
                        self.assertFalse(checked.accepted)
                        self.assertEqual(checked.executed_tests, 0)
                        self.assertIn("fixture document content must be a string", checked.reasons[0])

    def test_nonfinancial_fixture_can_execute_without_metadata(self):
        def source_present(spec, documents, as_of):
            document = documents[0]
            return SignalResult(signal_id=spec.signal_id, version=spec.version,
                value=SignalValue.NEUTRAL, confidence=1.0, interpretation="Source is present.",
                supporting_evidence=(SignalEvidence(document.document_id, document.content, as_of),))
        spec_data = self.spec.to_dict()
        spec_data["signal_id"] = "nonfinancial_fixture_probe"
        spec_data["execution"] = {"type": "deterministic", "function": "offline.source_present"}
        spec_data["raw_retrieval"] = {"source_types": ["news"]}
        spec = SignalSpec.from_dict(spec_data)
        fixture = {"name": "nonfinancial source", "as_of": "2025-02-01T00:00:00+00:00",
            "expected": "neutral", "documents": [{"source_type": "news",
            "available_at": "2025-01-20T00:00:00+00:00", "content": "A source-owned announcement."}]}
        validator = SignalCandidateValidator(self.registry, llm_runner=None,
            deterministic_functions={"offline.source_present": source_present})
        checked = validator.validate(spec, skill=None, tests=[fixture])
        self.assertTrue(checked.accepted, checked.reasons)
        self.assertEqual(checked.executed_tests, 1)

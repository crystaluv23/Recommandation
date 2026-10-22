"""SEC source coordinates share reversible native identity boundaries."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_transport import ExternalRequestPending, _CaseIdentityProjection
from tests.test_same_request_guard import _client
from tests.test_mining_controller import _controller, _fixture_store

ACCESSION = "0001213900-24-092156"
COMPACT = ACCESSION.replace("-", "")
URL = f"https://www.sec.gov/Archives/edgar/data/1951089/{COMPACT}/form20-f.htm"
HANDLE = f"document-secfacts:0001951089:{ACCESSION}:" + "a" * 64


class SourceCoordinateIdentityTests(TestCase):
    def projection(self):
        return _CaseIdentityProjection(("cik_0001951089",), "", "", expand_aliases=False)

    def test_filing_agent_accession_and_sec_paths_restore_exactly(self):
        original = {"document_ref": HANDLE, "source_url": URL,
            "nested": json.dumps({"accession_number": ACCESSION, "source_url": URL}),
            "slash_escaped": URL.replace("/", "\\/"),
            "nested_slash_escaped": json.dumps(json.dumps(URL.replace("/", "\\/"))),
            "relative_path": f"/Archives/edgar/data/1951089/{COMPACT}/form20-f.htm",
            "accession_endpoint": URL.rsplit("/", 1)[0] + "?output=1",
            "issuer_endpoint": "https://www.sec.gov/Archives/edgar/data/1951089",
            "literal": '{"value":-15122354,"start":"2023-07-01","end":"2024-06-30"}',
            "content_hash": "a" * 64}
        baseline = deepcopy(original)
        projection = self.projection()
        view, inverse = projection.project(original)
        wire = json.dumps(view)
        for identifier in (ACCESSION, COMPACT, "1951089"):
            self.assertNotIn(identifier, wire)
        self.assertIn("sec.gov", view["source_url"])
        self.assertIn("/Archives/edgar/data/", view["source_url"])
        self.assertEqual(view["literal"], original["literal"])
        self.assertEqual(view["content_hash"], original["content_hash"])
        self.assertEqual(projection.restore(view, inverse), original)
        self.assertEqual(original, baseline)
        # A filing agent accession equal to the issuer prefix is still one token.
        own = "0001951089-24-092156"
        masked, table = projection.project(own)
        self.assertEqual(list(table.values()), [own])
        self.assertEqual(projection.restore(masked, table), own)

    def test_financial_numbers_dates_and_ordinary_prose_are_not_source_ids(self):
        original = {"big": 121390024092156123, "numeric_text": COMPACT,
            "cash": -15122354, "ratio": "6.357163", "date": "2024-06-30",
            "ordinary": "document-local comparable prior; 1234567890 - 12 - 123456",
            "non_sec_path": f"/table/1951089/{COMPACT}/value"}
        self.assertEqual(self.projection().project(original), (original, {}))
        for tail in ("1234567890-document.htm", "1234567890_local.txt", "1234567890.csv"):
            path = "/Archives/edgar/data/" + tail
            self.assertEqual(self.projection().project(path), (path, {}))

    def test_raw_coordinate_guess_quarantined_but_disclosed_token_copy_restores(self):
        projection = self.projection()
        view, inverse = projection.project({"document_ref": HANDLE})
        valid, issues = projection.quarantine_output(view, inverse)
        self.assertEqual(issues, ())
        self.assertEqual(valid, {"document_ref": HANDLE})
        guessed, issues = projection.quarantine_output({"document_ref": HANDLE}, inverse)
        self.assertEqual(guessed, {"document_ref": None})
        self.assertEqual(issues, ("document_ref",))
        with self.assertRaises(ValidationError):
            projection.restore("[ANON_ID_9999]", inverse)

    def test_exact_estimate_wire_cache_and_restored_tool_argument_agree(self):
        payload = {"document_ref": HANDLE, "source_url": URL, "value": -15122354,
            "content_hash": "a" * 64}
        with TemporaryDirectory() as directory:
            client = _client(Path(directory))
            cases, store = _fixture_store()
            view = _controller(store, cases, object(), seed="discovery")._model_view()
            view["source_probe"] = payload
            with client.anonymous_case(aliases=("cik_0001951089",), company_id="cik_0001951089", ticker=""):
                kwargs = dict(stage="mining_controller_step", system_prompt="Copy source handle.",
                    payload=view, allow_outcomes=True, max_output_tokens=2000)
                estimate = client.estimate_json_request_tokens(**{k: v for k, v in kwargs.items() if k != "stage"})
                with self.assertRaises(ExternalRequestPending) as pending:
                    client.complete_json(**kwargs)
                request = json.loads(Path(pending.exception.request_path).read_text())["request"]
                self.assertEqual(estimate, request["wire_request"]["body_bytes"] + request["max_output_tokens"])
                wire_payload = json.loads(request["messages"][1]["content"])
                response = {"action": "read_span", "document_ref": wire_payload["source_probe"]["document_ref"], "rationale": ["Read original source."]}
                client.cache.store(pending.exception.request_hash, {"json_output": response, "usage": {}})
                parsed, usage = client.complete_json(**kwargs)
                self.assertEqual(parsed["document_ref"], HANDLE)
                self.assertEqual(usage.llm_calls, 0)
                cached = client.cache.load(pending.exception.request_hash)
                self.assertEqual(cached["json_output"], response)
            self.assertIsNone(getattr(client._chain_state, "identity_projection", None))

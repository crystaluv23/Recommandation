"""Literal SEC exhibit numbers retain row position and numeric-note provenance."""
from dataclasses import replace
from datetime import timedelta
import gzip
import hashlib
import json
from pathlib import Path
import re
import tempfile
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import content_sha256
from stock_opportunity_agent.data.reviewed_snapshot import (
    _SecExhibitLinks, _proved_sec_exhibit_code, ReviewedSourceRejected,
    materialize_reviewed_snapshot, open_raw_info_store,
)
from tests.test_reviewed_sec_response_profile import SecResponseFixture, bound, write


REPO = Path(__file__).resolve().parents[1]
TGB_RAW = REPO / "runs/diagnostics/frozen40_source_proofs_20261020_v1/final-plan-v2/collection/responses/proof-059.response.raw"
TGB_SHA = "0de96e11838f320df72cf26953842b5680e8c535060aece0c402b892874350a0"
TGB_PARENT = "https://www.sec.gov/Archives/edgar/data/878518/000106299325006514/form40f.htm"


def parser_for(html):
    parser = _SecExhibitLinks()
    parser.feed(html)
    parser.close()
    return parser


def tgb_html():
    raw = TGB_RAW.read_bytes()
    if hashlib.sha256(raw).hexdigest() != TGB_SHA:
        raise AssertionError("Actual retained TGB parent changed")
    return gzip.decompress(raw).decode("utf-8")


class ReviewedSecExhibitIndexTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.counter = 0

    def fixture(self, html, claimed="99.1"):
        """Bind a synthetic parent layout through actual native receipt/profile APIs."""
        self.counter += 1
        fixture = SecResponseFixture(self.base / str(self.counter), exhibit=True)
        path = fixture.base / "parent.raw"
        path.write_bytes(html.encode())
        item = next(x for x in fixture.receipt["requests"] if x["name"] == "parent")
        item.update(bytes=path.stat().st_size, raw_sha256=bound(path)["sha256"])
        fixture.proofs[-1].update(raw_response=bound(path), expected_content_hash=content_sha256(html))
        fixture.proofs[0]["exhibit_type"] = claimed
        fixture.document = replace(fixture.document, metadata={**fixture.document.metadata, "exhibit_type": claimed})
        fixture.review["records"][0]["original_record"] = write(fixture.original, fixture.document.to_dict())
        return fixture

    def restored(self, fixture):
        binding = materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
        store = open_raw_info_store(binding["root"], reviewed_snapshot=binding)
        for restored in (store, store.snapshot(), open_raw_info_store(binding["root"], reviewed_snapshot=binding)):
            self.assertEqual([x.to_dict() for x in restored.documents], [fixture.document.to_dict()])
            self.assertFalse(restored.append(fixture.document))
        return binding, store

    def test_actual_tgb_whole_parent_and_each_literal_row_prove_exact_numbers(self):
        html = tgb_html()
        parser = parser_for(html)
        actual_rows = [m.group() for m in re.finditer(r"<tr\b[\s\S]*?</tr>", html, re.IGNORECASE)
            if "exhibit99-1.htm" in m.group() or "exhibit99-3.htm" in m.group()]
        self.assertEqual(len(actual_rows), 4)
        for code in ("99.1", "99.3"):
            endpoint = TGB_PARENT.rsplit("/", 1)[0] + "/exhibit" + code.replace(".", "-") + ".htm"
            self.assertTrue(_proved_sec_exhibit_code(parser, TGB_PARENT, endpoint, code))
            self.assertFalse(_proved_sec_exhibit_code(parser, TGB_PARENT, endpoint, "99.2"))
            for row in actual_rows:
                if "exhibit" + code.replace(".", "-") + ".htm" in row:
                    self.assertTrue(_proved_sec_exhibit_code(parser_for(row), TGB_PARENT, endpoint, code))
        # Text remains literal, including the note, while the parser preserves its markup.
        note_cell = next(c for r in parser.rows for c in r["cells"] if "".join(c["text"]) == "99.1(1)")
        self.assertEqual([p["sup"] for p in note_cell["parts"] if isinstance(p, dict)], [["(1)"]])

    def test_actual_row_layouts_pass_native_profile_restart_and_worker_without_relabeling(self):
        # These are actual TGB table rows transplanted into the isolated fixture's
        # source URLs; this tests layout wiring, not admission of actual TGB originals.
        rows = [m.group() for m in re.finditer(r"<tr\b[\s\S]*?</tr>", tgb_html(), re.IGNORECASE)
            if "exhibit99-1.htm" in m.group()]
        self.assertEqual(len(rows), 2)
        for row in rows:
            with self.subTest(layout=row[:90]):
                self.restored(self.fixture("<table>" + row.replace("exhibit99-1.htm", "operating-aif.htm") + "</table>"))

    def test_only_explicit_trailing_numeric_superscripts_are_footnotes(self):
        valid = ["99.1<sup>(1)</sup>", "99.1<sup>2</sup>", "Exhibit 99.1 <sup><b>(3)</b></sup>",
            "99.1<sup>(1)</sup><sup>2</sup>"]
        invalid = ["99.1(1)", "99.1 1", "99.1\x00", "99.1<sup>99.2</sup>", "99.1<sup>note</sup>",
            "99.1<sup>1a</sup>", "99.1<sup>(1)(2)</sup>", "99.1<sup>[1]</sup>",
            "99.1<sup>１</sup>", "99<sup>(1)</sup>.1", "99.1<sup>(1)", "99.1<sup>(1)</sup> suffix"]
        for text in valid + invalid:
            with self.subTest(cell=text):
                html = '<table><tr><td><a href="aif.htm">AIF; see Exhibit99.2</a></td><td>' + text + '</td></tr></table>'
                parsed = parser_for(html)
                self.assertEqual(_proved_sec_exhibit_code(parsed, TGB_PARENT,
                    TGB_PARENT.rsplit("/", 1)[0] + "/aif.htm", "99.1"), text in valid)

    def test_native_wrong_claim_crossreferences_ambiguity_and_nonnotes_reject(self):
        cases = [
            ('<td>99.1</td><td><a href="operating-aif.htm">AIF; see Exhibit99.2 for financials</a></td>', "99.2"),
            ('<td><a href="operating-aif.htm">AIF</a></td><td>99.1<sup>99.2</sup></td>', "99.1"),
            ('<td><a href="operating-aif.htm">AIF</a></td><td>99.1(1)</td>', "99.1"),
            ('<td><a href="operating-aif.htm">AIF</a><a href="fs.htm">FS</a></td><td>99.1</td>', "99.1"),
            ('<td><a href="operating-aif.htm">AIF</a></td><td>99.1</td><td>99.3</td>', "99.1"),
            ('<td><a href="operating-aif.htm">AIF</a></td><td>99.1</td></tr><tr><td>99.3</td><td><a href="operating-aif.htm">FS</a></td>', "99.1"),
        ]
        for cells, claimed in cases:
            with self.subTest(cells=cells):
                fixture = self.fixture("<table><tr>" + cells + "</tr></table>", claimed)
                with self.assertRaises(ReviewedSourceRejected):
                    materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
                self.assertFalse((fixture.base / "view").exists())
        self.restored(self.fixture('<table><tr><td>99.1</td><td><a href="operating-aif.htm">AIF; see Exhibit99.2</a></td></tr></table>'))

    def test_actual_hiti_index_still_rejects_old_cover_prose_number(self):
        path = REPO / "runs/cold_start/evolution/deepseek-v4-flash-signal-wildcard-20260822-v1/cache/data/sec_edgar/filing_documents/292e64a32568298c937907f6.json"
        self.assertEqual(bound(path)["sha256"], "10eb3c457bb076495393575dec6ac612ee9c7174b6608205b0fb7ce756e00bee")
        html = json.loads(path.read_text())["body"]
        parent = "https://www.sec.gov/Archives/edgar/data/1847409/000162828025002990/hiti-20241031.htm"
        target = parent.rsplit("/", 1)[0] + "/hiti-annualinformationform.htm"
        parser = parser_for(html)
        self.assertTrue(_proved_sec_exhibit_code(parser, parent, target, "99.3"))
        self.assertFalse(_proved_sec_exhibit_code(parser, parent, target, "99.1"))

    def test_position_and_note_support_do_not_relax_cutoff_or_refresh_proof(self):
        html = '<table><tr><td><a href="operating-aif.htm">AIF</a></td><td>99.1<sup>(1)</sup></td></tr></table>'
        fixture = self.fixture(html)
        fixture.review["scope"]["as_of"] = (fixture.document.available_at - timedelta(microseconds=1)).isoformat()
        with self.assertRaises(ReviewedSourceRejected):
            materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
        fixture = self.fixture(html)
        binding, store = self.restored(fixture)
        (fixture.base / "parent.raw").write_text(html.replace("99.1", "99.2"))
        for action in (store.refresh, store.snapshot, lambda: open_raw_info_store(binding["root"], reviewed_snapshot=binding)):
            with self.assertRaises(ReviewedSourceRejected): action()

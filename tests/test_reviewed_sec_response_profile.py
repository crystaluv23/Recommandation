"""Retained SEC response carriers and literal parent/exhibit source boundaries."""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import zlib
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoOracle, RawInfoStore, content_sha256
from stock_opportunity_agent.data.reviewed_snapshot import (
    materialize_reviewed_snapshot, open_raw_info_store, ReviewedSourceRejected,
    _SecExhibitLinks, _proved_sec_exhibit_code,
)


def bound(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    return bound(path)


class SecResponseFixture:
    """Create exact receipt/native-record shapes under a temporary real oracle."""

    def __init__(self, base, *, linked=True, root_response=False, archive_response=False, exhibit=False, compression=None):
        self.base, self.linked = Path(base), linked
        self.base.mkdir(parents=True, exist_ok=True)
        self.root_response, self.archive_response, self.exhibit = root_response, archive_response, exhibit
        self.company, self.cik, self.accession = "cik_0000000001", "0000000001", "0000000002-25-000001"
        self.form = "40-F" if exhibit else "10-Q"
        self.parent_url = "https://www.sec.gov/Archives/edgar/data/1/000000000225000001/primary.htm"
        self.body_url = self.parent_url.replace("primary.htm", "operating-aif.htm") if exhibit else self.parent_url
        self.root_url = "https://data.sec.gov/submissions/CIK0000000001.json"
        self.filename = "CIK0000000001-submissions-001.json"
        self.archive_url = "https://data.sec.gov/submissions/" + self.filename
        self.arrays = {"accessionNumber": [self.accession, "0000000002-25-000002"],
            "filingDate": ["2025-05-05", "2025-05-30"], "form": [self.form, "8-K"],
            "primaryDocument": ["primary.htm", "other.htm"], "reportDate": ["2025-03-31", "2025-05-30"],
            "acceptanceDateTime": ["2025-05-05T20:00:00Z", "2025-05-30T20:00:00Z"]}
        self.root = {"cik": 1, "filings": {"recent": {k: [] for k in self.arrays} if linked else deepcopy(self.arrays),
            "files": [{"name": self.filename, "filingCount": 2, "filingFrom": "2025-05-01", "filingTo": "2025-05-29"}]}}
        self.archive = deepcopy(self.arrays)
        self.parent = '<html><table><tr><td>99.1</td><td><a href="operating-aif.htm">Annual Information Form, referencing February 12</a></td></tr></table></html>'
        self.content = "<html>Whole operating source é; scope still requires review.</html>"
        self.receipt = {"requests": [], "automatic_retries": 0, "redirects_followed": 0, "GET_attempts": 0}
        self.proofs = []
        self.add_response("root", self.root_url, json.dumps(self.root).encode())
        self.add_response("archive", self.archive_url, json.dumps(self.archive).encode())
        raw = self.content.encode()
        if compression == "gzip": raw = gzip.compress(raw)
        if compression == "deflate": raw = zlib.compress(raw)
        body = self.add_response("body", self.body_url, raw, compression)
        body.update(kind="sec_static_archive_body_response", document_role="incorporated_exhibit" if exhibit else "primary",
            expected_content_hash=content_sha256(self.content))
        self.proofs.append(body)
        self.root_proof = {"kind": "sec_submissions_root_response" if root_response else "sec_submissions_root",
            "issuer_cik": self.cik, "accession_number": self.accession, "form": self.form,
            "primary_document": "primary.htm", "filing_date": "2025-05-05", "accepted_at": "2025-05-05T20:00:00Z"}
        if root_response: self.root_proof.update(self.response_proof("root"))
        self.proofs.append(self.root_proof)
        if linked:
            archive = {"kind": "sec_submissions_linked_archive_response" if archive_response else "sec_submissions_linked_archive", "filename": self.filename}
            if archive_response: archive.update(self.response_proof("archive"))
            self.proofs.append(archive)
        metadata = {"source_url": self.body_url, "provider": "sec_edgar", "cik": self.cik,
            "form": self.form, "accession_number": self.accession}
        document_id = "sec:" + self.company + ":" + self.accession.replace("-", "")
        if exhibit:
            parent = self.add_response("parent", self.parent_url, self.parent.encode())
            parent.update(kind="sec_parent_primary_response", document_role="primary", expected_content_hash=content_sha256(self.parent))
            self.proofs.append(parent)
            body.update(exhibit_document="operating-aif.htm", exhibit_type="99.1")
            metadata.update(parent_form=self.form, parent_primary_document="primary.htm", exhibit_document="operating-aif.htm",
                document_role="incorporated_exhibit", exhibit_type="99.1")
            document_id = "sec-exhibit:" + self.company + ":" + self.accession.replace("-", "") + ":operating-aif.htm"
        accepted = datetime(2025, 5, 5, 20, tzinfo=timezone.utc)
        self.document = RawInfoDocument.create(document_id=document_id, company_id=self.company, source_type="filing",
            published_at=accepted, available_at=accepted, content=self.content, metadata=metadata)
        self.oracle = self.base / "oracle"
        RawInfoOracle.load_or_create(self.oracle)
        RawInfoStore(self.oracle).append(self.document)
        self.original = next(p for p in self.oracle.rglob("*.json") if p.name != "oracle.json")
        self.review = {"schema_version": "reviewed-raw-info-snapshot-v1", "oracle_identity": bound(self.oracle / "oracle.json"),
            "scope": {"company_ids": [self.company], "as_of": "2025-07-31T00:00:00Z", "acquisition_allowed": False},
            "records": [{"document_id": document_id, "company_id": self.company, "original_record": bound(self.original),
                "content_hash": self.document.content_hash, "verdict": "admitted", "reason": "Isolated source proof, no semantic sufficiency claim.",
                "reviewed_available_at": accepted.isoformat(), "proof_profile": "sec_filing_exhibit_response_v1" if exhibit else "sec_filing_response_acceptance_v1",
                "proofs": self.proofs}]}

    def add_response(self, name, endpoint, raw, encoding=None):
        path = self.base / (name + ".raw")
        path.write_bytes(raw)
        self.receipt["requests"].append({"name": name, "method": "GET", "url": endpoint, "response_url": endpoint,
            "status": "http_response_retained", "http_status": 200, "started_at_utc": "2026-10-20T00:00:00Z",
            "retrieved_at_utc": "2026-10-20T00:00:01Z", "raw_response": str(path), "raw_sha256": bound(path)["sha256"],
            "bytes": len(raw), "response_headers": {"Content-Encoding": encoding} if encoding else {}})
        self.receipt["GET_attempts"] += 1
        return self.response_proof(name)

    def response_proof(self, name):
        item = next(item for item in self.receipt["requests"] if item["name"] == name)
        return {"entry_name": name, "endpoint": item["url"], "raw_response": bound(Path(item["raw_response"]))}

    def save(self):
        receipt_binding = write(self.base / "results.json", self.receipt)
        for proof in self.proofs:
            if proof["kind"].endswith("_response"):
                proof["artifact"] = receipt_binding
            else:
                payload, endpoint = (self.root, self.root_url) if proof["kind"] == "sec_submissions_root" else (self.archive, self.archive_url)
                proof["artifact"] = write(self.base / (proof["kind"] + ".json"), {"source_key": "sec_edgar",
                    "capability": "filing_documents", "payload_kind": "json", "endpoint": endpoint,
                    "params": [["method", "GET"]], "retrieved_at": "2026-09-01T00:00:00Z", "body": payload})
        self.review["manifest_hash"] = canonical_json_hash({k: v for k, v in self.review.items() if k != "manifest_hash"})
        path = self.base / "review.json"
        write(path, self.review)
        return path


class ReviewedSecResponseProfileTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)

    def rejected(self, fixture):
        with self.assertRaises(ReviewedSourceRejected):
            materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
        self.assertFalse((fixture.base / "view").exists())

    def test_explicit_root_linked_and_response_carriers_restore_without_repackaging(self):
        for i, (linked, root_response, archive_response) in enumerate(((False, False, False), (False, True, False),
                (True, False, False), (True, True, False), (True, False, True), (True, True, True))):
            fixture = SecResponseFixture(self.base / str(i), linked=linked, root_response=root_response, archive_response=archive_response)
            binding = materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
            store = open_raw_info_store(binding["root"], reviewed_snapshot=binding)
            self.assertEqual(store.documents, (fixture.document,))
            self.assertEqual(store.snapshot().documents, store.documents)
            self.assertEqual(store.refresh(), 0)
            self.assertFalse(store.append(fixture.document))

    def test_native_compression_and_equivalent_aware_offsets(self):
        for encoding in ("gzip", "deflate"):
            fixture = SecResponseFixture(self.base / encoding, compression=encoding)
            fixture.archive["acceptanceDateTime"][0] = "2025-05-05T16:00:00-04:00"
            fixture.root_proof["accepted_at"] = "2025-05-05T16:00:00-04:00"
            fixture.review["scope"]["as_of"] = "2025-07-30T20:00:00-04:00"
            binding = materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
            self.assertEqual(open_raw_info_store(binding["root"], reviewed_snapshot=binding).documents, (fixture.document,))

    def test_rehashed_receipt_mechanical_tampering_rejects(self):
        for variant in ("method", "status", "response_url", "duplicate_name", "duplicate_url", "retry", "redirect",
                        "sha", "path", "bytes", "naive", "reversed_clock", "role"):
            with self.subTest(variant=variant):
                fixture = SecResponseFixture(self.base / variant)
                item = next(item for item in fixture.receipt["requests"] if item["name"] == "body")
                if variant == "method": item["method"] = "POST"
                elif variant == "status": item["http_status"] = 302
                elif variant == "response_url": item["response_url"] += "?redirected=1"
                elif variant == "duplicate_name": fixture.receipt["requests"].append(deepcopy(item))
                elif variant == "duplicate_url": fixture.receipt["requests"].append({**item, "name": "again"})
                elif variant == "retry": fixture.receipt["automatic_retries"] = 1
                elif variant == "redirect": fixture.receipt["redirects_followed"] = False
                elif variant == "sha": item["raw_sha256"] = "0" * 64
                elif variant == "path": item["raw_response"] = str(fixture.base / "other.raw")
                elif variant == "bytes": item["bytes"] += 1
                elif variant == "naive": item["started_at_utc"] = "2026-10-20T00:00:00"
                elif variant == "reversed_clock": item["retrieved_at_utc"] = "2026-10-19T23:59:59Z"
                else: fixture.proofs[0]["document_role"] = "incorporated_exhibit"
                self.rejected(fixture)

    def test_root_link_array_target_and_cutoff_counterexamples(self):
        for variant in ("issuer", "missing_link", "duplicate_link", "count", "date_window", "unequal", "scalar",
                        "duplicate_target", "form", "primary", "filed", "naive_accepted", "after_cutoff", "extra_kind", "competing_root"):
            with self.subTest(variant=variant):
                fixture = SecResponseFixture(self.base / variant)
                if variant == "issuer": fixture.root["cik"] = "CIK0000000001"
                elif variant == "missing_link": fixture.root["filings"]["files"] = []
                elif variant == "duplicate_link": fixture.root["filings"]["files"] *= 2
                elif variant == "count": fixture.root["filings"]["files"][0]["filingCount"] = True
                elif variant == "date_window": fixture.root["filings"]["files"][0]["filingFrom"] = "2025-05-06"
                elif variant == "unequal": fixture.archive["acceptanceDateTime"].pop()
                elif variant == "scalar": fixture.archive["reportDate"] = "2025-03-31"
                elif variant == "duplicate_target":
                    for values in fixture.archive.values(): values[1] = values[0]
                elif variant == "form": fixture.archive["form"][0] = "6-K"
                elif variant == "primary": fixture.archive["primaryDocument"][0] = "../primary.htm"
                elif variant == "filed": fixture.archive["filingDate"][0] = "2025-05-04"
                elif variant == "naive_accepted": fixture.archive["acceptanceDateTime"][0] = "2025-05-05T20:00:00"
                elif variant == "after_cutoff": fixture.review["scope"]["as_of"] = "2025-05-05T19:59:59Z"
                elif variant == "extra_kind": fixture.proofs.append({"kind": "unexpected", **fixture.response_proof("body")})
                else:
                    fixture.proofs.append({**fixture.root_proof, **fixture.response_proof("root"), "kind": "sec_submissions_root_response"})
                self.rejected(fixture)

    def test_rehashed_original_and_raw_bytes_cannot_change(self):
        for variant in ("original_clock", "original_metadata", "raw", "gzip"):
            fixture = SecResponseFixture(self.base / variant, compression="gzip" if variant == "gzip" else None)
            if variant.startswith("original"):
                record = fixture.document.to_dict()
                if variant == "original_clock": record["available_at"] = "2025-05-05T00:00:00+00:00"
                else: record["metadata"]["extra_claim"] = True
                fixture.review["records"][0]["original_record"] = write(fixture.original, record)
            else:
                path = fixture.base / "body.raw"
                path.write_bytes(b'\x1f\x8b' if variant == "gzip" else b'changed body')
                item = next(item for item in fixture.receipt["requests"] if item["name"] == "body")
                item.update(bytes=path.stat().st_size, raw_sha256=bound(path)["sha256"])
                fixture.proofs[0]["raw_response"] = bound(path)
            self.rejected(fixture)

    def test_literal_parent_exhibit_role_type_and_parent_acceptance(self):
        fixture = SecResponseFixture(self.base, exhibit=True)
        binding = materialize_reviewed_snapshot(fixture.save(), self.base / "view")
        store = open_raw_info_store(binding["root"], reviewed_snapshot=binding)
        self.assertEqual(store.documents, (fixture.document,))
        self.assertEqual(store.snapshot().documents, (fixture.document,))
        self.assertEqual(fixture.document.metadata["parent_form"], "40-F")
        self.assertEqual(fixture.document.metadata["exhibit_type"], "99.1")
        self.assertEqual(fixture.document.available_at.month, 5)
        self.assertTrue(fixture.document.document_id.startswith("sec-exhibit:"))

    def test_exhibit_cannot_relabel_unguarded_links_form_or_time(self):
        for variant in ("no_parent", "parent_role", "wrong_type", "missing_link", "other_accession", "primary_id", "form", "backdate"):
            with self.subTest(variant=variant):
                fixture = SecResponseFixture(self.base / variant, exhibit=True)
                if variant == "no_parent": fixture.proofs.pop()
                elif variant == "parent_role": fixture.proofs[-1]["document_role"] = "incorporated_exhibit"
                elif variant == "wrong_type": fixture.proofs[0]["exhibit_type"] = "99.2"
                elif variant in {"missing_link", "other_accession"}:
                    parent = fixture.parent.replace("operating-aif.htm", "unlinked.htm" if variant == "missing_link" else "../000000000225000002/operating-aif.htm")
                    path = fixture.base / "parent.raw";path.write_bytes(parent.encode())
                    item = next(item for item in fixture.receipt["requests"] if item["name"] == "parent")
                    item.update(bytes=path.stat().st_size, raw_sha256=bound(path)["sha256"])
                    fixture.proofs[-1].update(raw_response=bound(path), expected_content_hash=content_sha256(parent))
                else:
                    record = fixture.document.to_dict()
                    if variant == "primary_id":
                        record["document_id"] = "sec:" + fixture.company + ":" + fixture.accession.replace("-", "")
                        fixture.review["records"][0]["document_id"] = record["document_id"]
                    elif variant == "form": record["metadata"]["form"] = "6-K"
                    else:
                        record["available_at"] = record["published_at"] = "2025-02-12T00:00:00+00:00"
                        fixture.review["records"][0]["reviewed_available_at"] = record["available_at"]
                    fixture.review["records"][0]["original_record"] = write(fixture.original, record)
                self.rejected(fixture)

    def test_raw_proof_drift_reverified_at_refresh_and_worker_restore(self):
        fixture = SecResponseFixture(self.base)
        binding = materialize_reviewed_snapshot(fixture.save(), self.base / "view")
        store = open_raw_info_store(binding["root"], reviewed_snapshot=binding)
        (fixture.base / "body.raw").write_bytes(b'changed')
        for action in (store.refresh, store.snapshot):
            with self.assertRaises(ReviewedSourceRejected): action()

    def test_index_code_cell_excludes_description_cross_reference_and_ambiguous_rows(self):
        cases = [
            ('<td>99.1</td><td><a href="operating-aif.htm">AIF; see Exhibit99.2 for financials</a></td>', "99.2", False),
            ('<td>99.1</td><td><a href="operating-aif.htm">AIF; see Exhibit99.2 for financials</a></td>', "99.1", True),
            ('<td>99.1</td><td><a href="operating-aif.htm">AIF</a><a href="financials.htm">99.2</a></td>', "99.1", False),
            ('<td>99.1</td><td>99.2</td><td><a href="operating-aif.htm">AIF</a></td>', "99.1", False),
            ('<td>99.1</td><td><a href="operating-aif.htm">AIF</a></td></tr><tr><td>99.2</td><td><a href="operating-aif.htm">FS</a></td>', "99.1", False),
            ('<td>99.1</td><td><a href="operating-aif.htm">AIF</a><a href="financials.htm">FS</a></td>', None, True),
        ]
        for i, (cells, claimed, valid) in enumerate(cases):
            with self.subTest(case=i):
                fixture = SecResponseFixture(self.base / str(i), exhibit=True)
                parent = "<html><table><tr>" + cells + "</tr></table></html>"
                path = fixture.base / "parent.raw"
                path.write_bytes(parent.encode())
                item = next(item for item in fixture.receipt["requests"] if item["name"] == "parent")
                item.update(bytes=path.stat().st_size, raw_sha256=bound(path)["sha256"])
                fixture.proofs[-1].update(raw_response=bound(path), expected_content_hash=content_sha256(parent))
                fixture.proofs[0]["exhibit_type"] = claimed
                record = fixture.document.to_dict()
                record["metadata"]["exhibit_type"] = claimed
                fixture.review["records"][0]["original_record"] = write(fixture.original, record)
                if valid:
                    binding = materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
                    restored = open_raw_info_store(binding["root"], reviewed_snapshot=binding).snapshot()
                    self.assertEqual(restored.documents[0].metadata["exhibit_type"], claimed)
                else:
                    self.rejected(fixture)

    def test_actual_retained_kgc_parent_index_layout_proves_only_its_literal_codes(self):
        path = Path(__file__).resolve().parents[1] / "runs/diagnostics/periodic_source_qualification_20261020_v1/fetch-v1/kgc-fy2024-40f-primary.response.raw"
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "014548bf51ae4915583b200660f77068f180444ff5d412107282840351847d97")
        parser = _SecExhibitLinks()
        parser.feed(raw.decode("utf-8"))
        parent = "https://www.sec.gov/Archives/edgar/data/701818/000110465925028819/kgc-20241231x40f.htm"
        for filename, code in (("kgc-20241231xex99d1.htm", "99.1"), ("kgc-20241231xex99d2.htm", "99.2")):
            endpoint = parent.rsplit("/", 1)[0] + "/" + filename
            self.assertTrue(_proved_sec_exhibit_code(parser, parent, endpoint, code))
            self.assertFalse(_proved_sec_exhibit_code(parser, parent, endpoint, "99.3"))

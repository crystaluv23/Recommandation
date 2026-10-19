"""Proof-bound, read-only Raw Info snapshots for explicitly reviewed local scope."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Mapping

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore, content_sha256
from stock_opportunity_agent.models import ValidationError


_MANIFEST = "reviewed_snapshot.json"


class ReviewedSourceRejected(RuntimeError):
    """A source-boundary failure, never a research-negative observation."""


def _source_boundary(function):
    """Keep malformed/missing local proof failures on the source boundary."""
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (KeyError, TypeError, ValueError, AttributeError, OSError, ValidationError) as exc:
            raise ReviewedSourceRejected(f"invalid reviewed source artifact: {exc}") from exc
    return checked


@_source_boundary
def _read_bound(binding: Mapping[str, Any]) -> tuple[bytes, Any]:
    path = Path(str(binding["path"]))
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReviewedSourceRejected(f"reviewed source artifact missing: {path}") from exc
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ReviewedSourceRejected(f"reviewed source artifact changed: {path}")
    return raw, json.loads(raw)


def _instant(value: Any) -> datetime:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ReviewedSourceRejected("reviewed source time is invalid") from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ReviewedSourceRejected("reviewed source time must be aware")
    return result


@_source_boundary
def _verified_review(binding: Mapping[str, Any]) -> tuple[dict, list[RawInfoDocument]]:
    _raw, review = _read_bound(binding)
    if review.get("schema_version") != "reviewed-raw-info-snapshot-v1":
        raise ReviewedSourceRejected("unsupported reviewed source manifest")
    unhashed = {key: value for key, value in review.items() if key != "manifest_hash"}
    if canonical_json_hash(unhashed) != review.get("manifest_hash"):
        raise ReviewedSourceRejected("reviewed source manifest identity differs")
    scope = review["scope"]
    if scope.get("acquisition_allowed") is not False:
        raise ReviewedSourceRejected("this reviewed snapshot forbids acquisition")
    cutoff = _instant(scope["as_of"])
    _read_bound(review["oracle_identity"])
    oracle_root = Path(review["oracle_identity"]["path"]).resolve().parent
    documents, seen = [], set()
    for row in review["records"]:
        if row["document_id"] in seen:
            raise ReviewedSourceRejected("duplicate reviewed document")
        seen.add(row["document_id"])
        if not Path(row["original_record"]["path"]).resolve().is_relative_to(oracle_root):
            raise ReviewedSourceRejected("original record is outside the declared oracle root")
        _record_bytes, record = _read_bound(row["original_record"])
        document = RawInfoDocument.from_dict(record)
        if (document.document_id != row["document_id"] or document.company_id != row["company_id"]
                or document.content_hash != row["content_hash"] or document.company_id not in scope["company_ids"]):
            raise ReviewedSourceRejected("reviewed document identity/scope differs")
        kinds = [item["kind"] for item in row["proofs"]]
        if len(kinds) != len(set(kinds)):
            raise ReviewedSourceRejected("duplicate reviewed proof kind")
        proofs = {item["kind"]: (item, _read_bound(item["artifact"])[1]) for item in row["proofs"]}
        if row["verdict"] in {"unknown", "excluded"}:
            continue
        if row["verdict"] != "admitted":
            raise ReviewedSourceRejected("unknown reviewed disposition")
        if set(proofs) != {"sec_static_archive_body", "sec_submissions_acceptance"}:
            raise ReviewedSourceRejected("admitted source requires retained SEC body and acceptance proof")
        if document.source_type != "filing":
            raise ReviewedSourceRejected("static SEC filing proof requires filing source type")
        body_proof, body = proofs["sec_static_archive_body"]
        acceptance, submissions = proofs["sec_submissions_acceptance"]
        if (body.get("endpoint") != body_proof["endpoint"] or body.get("body") != document.content
                or content_sha256(body["body"]) != body_proof["expected_content_hash"]):
            raise ReviewedSourceRejected("static SEC body differs from admitted original")
        source = submissions["body"]
        if submissions.get("endpoint") != "https://data.sec.gov/submissions/CIK" + acceptance["issuer_cik"] + ".json":
            raise ReviewedSourceRejected("SEC submissions endpoint differs from reviewed issuer")
        recent = source["filings"]["recent"]
        accession = acceptance["accession_number"]
        matches = [i for i, value in enumerate(recent["accessionNumber"]) if value == accession]
        if (str(source["cik"]).zfill(10) != acceptance["issuer_cik"] or len(matches) != 1
                or document.company_id != "cik_" + acceptance["issuer_cik"]
                or document.document_id != "sec:" + document.company_id + ":" + accession.replace("-", "")):
            raise ReviewedSourceRejected("SEC issuer/accession identity differs")
        index = matches[0]
        accepted = _instant(recent["acceptanceDateTime"][index])
        expected_endpoint = ("https://www.sec.gov/Archives/edgar/data/" + str(int(acceptance["issuer_cik"]))
            + "/" + accession.replace("-", "") + "/" + acceptance["primary_document"])
        expected_metadata = {"source_url": expected_endpoint, "accession_number": accession,
            "form": acceptance["form"], "provider": "sec_edgar", "cik": acceptance["issuer_cik"]}
        if any(key in document.metadata and document.metadata[key] != expected
               for key, expected in expected_metadata.items()):
            raise ReviewedSourceRejected("SEC source metadata differs from retained proof")
        if (recent["form"][index] != acceptance["form"]
                or recent["primaryDocument"][index] != acceptance["primary_document"]
                or body_proof["endpoint"] != expected_endpoint
                or accepted != _instant(acceptance["accepted_at"])
                or accepted != _instant(row["reviewed_available_at"])
                or document.available_at != accepted or document.published_at != accepted
                or accepted > cutoff):
            raise ReviewedSourceRejected("SEC availability/filing proof differs from original or scope")
        documents.append(document)
    return review, documents


@_source_boundary
def materialize_reviewed_snapshot(review_path: str | Path, root: str | Path) -> dict:
    """Verify retained review proofs and materialize a new isolated input view."""
    root = Path(root).resolve()
    if root.exists():
        raise ReviewedSourceRejected("reviewed snapshot destination must be new")
    review_path = Path(review_path).resolve()
    review_binding = {"path": str(review_path), "sha256": hashlib.sha256(review_path.read_bytes()).hexdigest()}
    review, documents = _verified_review(review_binding)
    oracle_root = Path(review["oracle_identity"]["path"]).resolve().parent
    if root.is_relative_to(oracle_root):
        raise ReviewedSourceRejected("reviewed snapshot must be outside the original oracle root")
    root.mkdir(parents=True)
    rows = []
    for index, document in enumerate(documents):
        path = root / "documents" / f"{index:04d}.json"
        atomic_write_json(path, document.to_dict())
        rows.append({"document_id": document.document_id, "path": str(path.relative_to(root)),
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    oracle_raw, _oracle = _read_bound(review["oracle_identity"])
    (root / "oracle.json").write_bytes(oracle_raw)
    manifest = {"schema_version": "materialized-reviewed-raw-info-v1", "root": str(root),
                "source_review": review_binding, "scope": review["scope"], "documents": rows,
                "oracle_sha256": hashlib.sha256(oracle_raw).hexdigest()}
    atomic_write_json(root / _MANIFEST, manifest)
    return {"store_type": "reviewed", "root": str(root),
            "manifest_sha256": hashlib.sha256((root / _MANIFEST).read_bytes()).hexdigest()}


class ReviewedRawInfoStore(RawInfoStore):
    """RawInfoStore-compatible view that never widens beyond an explicit binding."""

    acquisition_allowed = False

    def __init__(self, binding: Mapping[str, Any]) -> None:
        if binding.get("store_type") != "reviewed":
            raise ReviewedSourceRejected("reviewed store type is required")
        if not all(isinstance(binding.get(key), str) and binding[key] for key in ("root", "manifest_sha256")):
            raise ReviewedSourceRejected("reviewed root and manifest hash are required")
        self.binding = dict(binding)
        super().__init__()
        self.root = Path(str(binding["root"])).resolve()
        self.refresh()

    def append(self, document: RawInfoDocument) -> bool:
        """Allow only an exact admitted replay, without writing anything."""
        self.refresh()
        existing = self._documents.get(document.document_id)
        if existing is None or existing.to_dict() != document.to_dict():
            raise ReviewedSourceRejected("document is outside the immutable reviewed input set")
        return False

    @_source_boundary
    def refresh(self) -> int:
        """Reverify the exact manifest, all original proofs and admitted files."""
        if self.root is None:
            return 0
        _raw, manifest = _read_bound({"path": str(self.root / _MANIFEST), "sha256": self.binding["manifest_sha256"]})
        if manifest.get("schema_version") != "materialized-reviewed-raw-info-v1" or manifest["root"] != str(self.root):
            raise ReviewedSourceRejected("reviewed snapshot root/type differs")
        review, documents = _verified_review(manifest["source_review"])
        if manifest["scope"] != review["scope"]:
            raise ReviewedSourceRejected("reviewed snapshot scope differs")
        _read_bound({"path": str(self.root / "oracle.json"), "sha256": manifest["oracle_sha256"]})
        expected = {self.root / _MANIFEST, self.root / "oracle.json"}
        loaded = {}
        by_id = {document.document_id: document for document in documents}
        for row in manifest["documents"]:
            path = self.root / row["path"]
            if not path.resolve().is_relative_to(self.root) or path in expected:
                raise ReviewedSourceRejected("reviewed document path escapes or repeats")
            expected.add(path)
            _raw, value = _read_bound({"path": str(path), "sha256": row["sha256"]})
            document = RawInfoDocument.from_dict(value)
            if (document.document_id in loaded or document.document_id != row["document_id"]
                    or document != by_id.get(document.document_id)):
                raise ReviewedSourceRejected("materialized document differs from admitted original")
            loaded[document.document_id] = document
        if set(loaded) != set(by_id) or set(self.root.rglob("*.json")) != expected:
            raise ReviewedSourceRejected("reviewed snapshot document membership differs")
        added = len(set(loaded) - set(self._documents))
        self._documents = loaded
        return added

    def snapshot(self) -> "ReviewedRawInfoStore":
        """Retain read-only review qualification in an isolated worker view."""
        return ReviewedRawInfoStore(self.binding)


def open_raw_info_store(root: str | Path, *, reviewed_snapshot: Mapping[str, Any] | None = None) -> RawInfoStore:
    """Open an explicitly frozen reviewed view or a legacy ordinary oracle."""
    root = Path(root).resolve()
    if reviewed_snapshot is not None:
        if str(root) != reviewed_snapshot.get("root"):
            raise ReviewedSourceRejected("frozen reviewed root differs from requested source root")
        return ReviewedRawInfoStore(reviewed_snapshot)
    if (root / _MANIFEST).exists():
        raise ReviewedSourceRejected("reviewed source requires an explicit frozen binding")
    return RawInfoStore(root)

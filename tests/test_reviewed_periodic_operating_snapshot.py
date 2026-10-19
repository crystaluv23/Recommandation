"""Temporary-boundary tests; no real diagnostic preparation or source mutation."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import diagnose_reviewed_periodic_operating_snapshot as diagnostic


class PeriodicDiagnosticBoundaryTests(TestCase):
    def test_qualification_dispatches_only_the_two_explicit_profiles(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "proof.json"
            path.write_text('{}')
            clock = datetime(2025, 1, 1, tzinfo=timezone.utc)
            document = diagnostic.RawInfoDocument.create(document_id="offline", company_id="offline",
                source_type="filing", published_at=clock, available_at=clock, content="offline fixture")
            candidate = {"document": document.to_dict(), "proofs": [
                {"kind": "sec_submissions_root", "artifact": diagnostic._binding(path)}]}
            cases = [{"company_id": "offline", "cutoff": clock.isoformat()}]
            for profile, exhibit in (("sec_filing_response_acceptance_v1", False),
                                     ("sec_filing_exhibit_response_v1", True)):
                candidate["proof_profile"] = profile
                with self.subTest(profile=profile), patch.object(diagnostic, "_verify_sec_response_document") as verifier:
                    diagnostic._qualify([candidate], cases)
                    verifier.assert_called_once()
                    self.assertIs(verifier.call_args.kwargs["exhibit"], exhibit)
            candidate["proof_profile"] = "unknown_profile"
            with patch.object(diagnostic, "_verify_sec_response_document") as verifier:
                with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, "unsupported periodic proof profile"):
                    diagnostic._qualify([candidate], cases)
                verifier.assert_not_called()

    def test_source_only_guards_actual_entry_points_and_restores_them(self):
        targets = [(diagnostic.socket, "socket"), (diagnostic.socket, "create_connection"),
            (diagnostic.LabelStore, "load"), (diagnostic.LabelStore, "ground_truth"),
            (diagnostic.run_minimal_rounds, "prepare"),
            *[(diagnostic.StructuredRoleClient, name) for name in
              ("complete_json", "complete_json_with_token_scores", "complete_binary_token_with_scores")],
            (diagnostic.SignalExecutor, "execute_batch")]
        originals = [getattr(target, name) for target, name in targets]
        with diagnostic._source_only():
            for target, name in targets:
                with self.subTest(entry=name), self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, "forbidden"):
                    getattr(target, name)()
        for (target, name), original in zip(targets, originals, strict=True):
            self.assertEqual(getattr(target, name), original)

    def test_preappend_qualification_checks_proof_binding_before_verifier(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "proof.json"
            path.write_text(json.dumps({"source": "initial"}))
            binding = diagnostic._binding(path)
            path.write_text(json.dumps({"source": "changed"}))
            clock = datetime(2025, 1, 1, tzinfo=timezone.utc)
            document = diagnostic.RawInfoDocument.create(document_id="offline", company_id="offline",
                source_type="filing", published_at=clock, available_at=clock, content="offline fixture")
            candidate = {"document": document.to_dict(), "proof_profile": "sec_filing_response_acceptance_v1",
                "proofs": [{"kind": "sec_submissions_root", "artifact": binding}]}
            with patch.object(diagnostic, "_verify_sec_response_document") as verifier:
                with self.assertRaises(diagnostic.ReviewedSourceRejected):
                    diagnostic._qualify([candidate], [{"company_id": "offline", "cutoff": clock.isoformat()}])
                verifier.assert_not_called()
            candidate["proofs"] *= 2
            with patch.object(diagnostic, "_verify_sec_response_document") as verifier:
                with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, "duplicate periodic proof kind"):
                    diagnostic._qualify([candidate], [{"company_id": "offline", "cutoff": clock.isoformat()}])
                verifier.assert_not_called()

    def test_existing_execution_marker_blocks_reentry_before_any_global_store(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            marker = output / "execution-start.json"
            marker.write_bytes(b'{"prior":"failed or completed"}')
            with patch.object(diagnostic, "_verify_plan", return_value={"plan_hash": "offline"}), \
                    patch.object(diagnostic, "RawInfoStore") as store:
                with self.assertRaises(FileExistsError):
                    diagnostic._execute(output)
                store.assert_not_called()
            self.assertEqual(marker.read_bytes(), b'{"prior":"failed or completed"}')

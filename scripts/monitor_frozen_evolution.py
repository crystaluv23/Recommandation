"""Monitor an authorized frozen diagnostic run and recover terminal transport gaps.

Example:
    python scripts/monitor_frozen_evolution.py --source /frozen/checkout \
        --root /runs/diagnostic --control /run-control
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    """Replace one process record atomically without modifying archived records."""
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _frozen_identity(source: Path, root: Path) -> tuple[str, str, str]:
    """Check source/contract alignment and return immutable monitor fingerprints."""
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source, text=True)
    contract = _read(root / "run_contract.json")["contract"]
    if dirty or revision != contract["code_revision"]:
        raise ValueError("frozen source differs from the authorized run contract")
    return (revision, *(hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ("run_contract.json", "input_manifest.json")))


def _budget_available(contract: dict, ledger: dict) -> bool:
    """Require the unchanged, settled-cost ledger to have remaining headroom."""
    if (ledger["max_attempts"] != contract["max_external_attempts"]
        or ledger["max_total_cost"] != contract["max_total_cost"]):
        raise ValueError("monitor cannot change the authorized attempt/cost ceilings")
    costs = [row["actual_cost"] if row.get("actual_cost") is not None else row["reserved_cost"]
        for row in ledger["attempts"]]
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) or value < 0 for value in costs):
        raise ValueError("invalid attempt cost in authoritative ledger")
    return len(costs) < ledger["max_attempts"] and sum(costs) < ledger["max_total_cost"]


def _fresh_transport_failure(exit_code: int, last_line: str, attempt: dict, started_at: str) -> bool:
    """Accept only a terminal transport error produced by this child invocation."""
    return (exit_code > 0 and last_line.startswith("stock_opportunity_agent.llm.openai.RetryableOpenAIClientError:")
        and attempt.get("status") == "failed" and attempt.get("error_type") == "RetryableOpenAIClientError"
        and datetime.fromisoformat(attempt["finished_at"]) >= datetime.fromisoformat(started_at))


def _assert_no_recorded_process(control: Path) -> None:
    """Refuse a duplicate monitor/executor while an existing recorded PID is live."""
    path = control / "process.json"
    if not path.exists():
        return
    record = _read(path)
    for key in ("pid", "wrapper_pid"):
        if record.get(key):
            try:
                os.kill(record[key], 0)
            except ProcessLookupError:
                continue
            raise ValueError("an existing recorded process is live; observe that handle")


def monitor(source: Path, root: Path, control: Path, *, max_resumes: int = 10, retry_seconds: int = 30) -> int:
    """Run one monitor; child exit is the only automatic recovery trigger."""
    if max_resumes < 0 or retry_seconds < 0:
        raise ValueError("monitor recovery limits must be non-negative")
    control.mkdir(parents=True, exist_ok=True)
    with (control / "monitor.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _assert_no_recorded_process(control)
        baseline = _frozen_identity(source, root)
        contract = _read(root / "run_contract.json")["contract"]
        command = [sys.executable, str(source / "scripts/run_minimal_rounds.py"), "--root", str(root), "--run"]
        environment = dict(os.environ, PYTHONPATH=str(source / "src"), PYTHONUNBUFFERED="1")
        stop = {"requested": False}
        child = None

        def interrupt(_signum, _frame):
            stop["requested"] = True
            if child is not None and child.poll() is None:
                child.terminate()

        previous_handlers = {kind: signal.signal(kind, interrupt) for kind in (signal.SIGINT, signal.SIGTERM)}
        archive = control / "monitor_exits"
        archive.mkdir(exist_ok=True)
        sequence = max((int(path.stem) for path in archive.glob("*.json")), default=0)
        resumes = 0
        record = {"wrapper_pid": os.getpid(), "command": command, "source_revision": baseline[0]}

        def publish(event, **fields):
            record.update(fields)
            _write(control / "process.json", record)
            with (control / "monitor_events.jsonl").open("a", encoding="utf-8") as journal:
                journal.write(json.dumps({"event": event, "at": _now(), **record}) + "\n")

        try:
            while not stop["requested"]:
                if _frozen_identity(source, root) != baseline:
                    raise ValueError("frozen contract or input manifest changed during monitoring")
                ledger = _read(root / "attempts.json")
                if not _budget_available(contract, ledger):
                    reason, code = "budget_exhausted", 1
                    break
                started = _now()
                with (control / "cycle.log").open("ab") as log:
                    offset = log.tell()
                    child = subprocess.Popen(command, cwd=source, env=environment, stdout=log, stderr=subprocess.STDOUT)
                    publish("child_started", pid=child.pid, started_at=started, status="running", automatic_resumes=resumes)
                    code = child.wait()
                sequence += 1
                outcome = {"exit_code": code, "finished_at": _now(), "pid": child.pid, "started_at": started}
                _write(archive / f"{sequence:04d}.json", outcome)
                with (control / "cycle.log").open("rb") as log:
                    end = log.seek(0, os.SEEK_END)
                    log.seek(max(offset, end - 4096))
                    lines = log.read().decode("utf-8", errors="replace").strip().splitlines()
                last_line = lines[-1] if lines else ""
                ledger = _read(root / "attempts.json")
                fresh = bool(ledger["attempts"]) and _fresh_transport_failure(code, last_line, ledger["attempts"][-1], started)
                if stop["requested"]:
                    reason, code = "interrupted", 130
                    break
                if not fresh:
                    reason = "child_terminal"
                    break
                if not _budget_available(contract, ledger):
                    reason = "budget_exhausted"
                    break
                if resumes >= max_resumes:
                    reason = "transient_recovery_limit"
                    break
                resumes += 1
                publish("transport_retry_wait", status="retry_wait", automatic_resumes=resumes, last_exit_code=code)
                time.sleep(retry_seconds)
            else:
                reason, code = "interrupted", 130
            publish("monitor_stopped", status="stopped", reason=reason)
            _write(control / "exit.json", {"exit_code": code, "reason": reason, "finished_at": _now()})
            return code
        except Exception as exc:
            publish("monitor_stopped", status="stopped", reason="monitor_control_failure", error_type=type(exc).__name__)
            _write(control / "exit.json", {"exit_code": 1, "reason": "monitor_control_failure", "finished_at": _now()})
            raise
        finally:
            for kind, handler in previous_handlers.items():
                signal.signal(kind, handler)


def main() -> int:
    """Parse explicit frozen-run coordinates; never infer a different run to start."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "root", "control"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    return monitor(args.source.resolve(), args.root.resolve(), args.control.resolve())


if __name__ == "__main__":
    raise SystemExit(main())

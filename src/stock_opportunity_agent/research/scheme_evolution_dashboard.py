"""Local, dependency-free drift dashboard for information-scheme evolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from stock_opportunity_agent.models import ValidationError


HISTORY_SCHEMA_VERSION = "scheme-evolution-history-v1"
DASHBOARD_SCHEMA_VERSION = "scheme-evolution-dashboard-v1"
DASHBOARD_DATA_NAME = "evolution_dashboard_data.js"
DASHBOARD_HTML_NAME = "evolution_dashboard.html"
DASHBOARD_INDEX_NAME = "evolution_dashboard_index.json"


def write_evolution_dashboard(run_dir: str | Path) -> dict[str, Path]:
    """Refresh a run's file-openable HTML dashboard from local metric history.

    The HTML loads an adjacent JavaScript data file instead of using ``fetch``.
    This keeps direct ``file://`` opening reliable under normal browser security
    rules while preserving ``evolution_history.json`` as the canonical record.
    """

    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    history_path = root / "evolution_history.json"
    history = _load_or_recover_history(root, history_path)
    _validate_history(history)
    _write_json(history_path, history)

    data_path = root / DASHBOARD_DATA_NAME
    _write_data_bundle(data_path, _dashboard_bundle([history]))

    html_path = root / DASHBOARD_HTML_NAME
    _write_text(html_path, _dashboard_html())
    return {"history": history_path, "data": data_path, "dashboard": html_path}


def write_evolution_dashboard_index(evolution_root: str | Path) -> dict[str, Path]:
    """Refresh the one stable dashboard entry point across direct child runs."""

    root = Path(evolution_root)
    root.mkdir(parents=True, exist_ok=True)
    histories: list[dict[str, Any]] = []
    skipped_runs: list[dict[str, str]] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        history_path = child / "evolution_history.json"
        if not history_path.exists() and not (child / "state.json").exists():
            continue
        try:
            history = _load_or_recover_history(child, history_path)
            _validate_history(history)
        except ValidationError as exc:
            skipped_runs.append({"run_directory": child.name, "reason": str(exc)})
            continue
        histories.append(history)
    bundle = _dashboard_bundle(histories, skipped_runs=skipped_runs)
    index_path = root / DASHBOARD_INDEX_NAME
    data_path = root / DASHBOARD_DATA_NAME
    html_path = root / DASHBOARD_HTML_NAME
    _write_json(index_path, bundle)
    _write_data_bundle(data_path, bundle)
    _write_text(html_path, _dashboard_html())
    return {"index": index_path, "data": data_path, "dashboard": html_path}


def _dashboard_bundle(
    histories: list[dict[str, Any]],
    *,
    skipped_runs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    ordered = sorted(
        histories,
        key=lambda history: (_history_updated_at(history), str(history.get("run_id", ""))),
        reverse=True,
    )
    return {
        "schema_version": DASHBOARD_SCHEMA_VERSION,
        "primary_metric": "binary_f1",
        "contains_final_test_metrics": False,
        "runs": ordered,
        "skipped_runs": list(skipped_runs or []),
    }


def _history_updated_at(history: Mapping[str, Any]) -> str:
    rounds = history.get("rounds", [])
    if not isinstance(rounds, list):
        return ""
    completed = [
        str(row.get("completed_at", ""))
        for row in rounds
        if isinstance(row, Mapping) and row.get("completed_at")
    ]
    return max(completed, default="")


def _write_data_bundle(path: Path, bundle: Mapping[str, Any]) -> None:
    serialized = json.dumps(bundle, sort_keys=True, ensure_ascii=False)
    serialized = serialized.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    _write_text(path, f"window.__SCHEME_EVOLUTION_DASHBOARD__ = {serialized};\n")


def _load_or_recover_history(root: Path, history_path: Path) -> dict[str, Any]:
    if history_path.exists():
        return _read_json(history_path)
    state = _read_optional_json(root / "state.json")
    run_id = str(state.get("run_id") or root.name)
    history: dict[str, Any] = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "run_id": run_id,
        "primary_metric": "binary_f1",
        "contains_final_test_metrics": False,
        "rounds": [],
    }
    recovered = _recover_legacy_latest_round(root, state)
    if recovered is not None:
        history["rounds"] = [recovered]
    return history


def _recover_legacy_latest_round(
    root: Path,
    state: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Recover only the latest representable round from pre-dashboard artifacts."""

    experiments_artifact = _read_optional_json(root / "scheme_experiments.json")
    archive_artifact = _read_optional_json(root / "top_k.json")
    experiment_rows = experiments_artifact.get("experiments", [])
    archive_rows = archive_artifact.get("entries", [])
    if not isinstance(experiment_rows, list) or not isinstance(archive_rows, list):
        return None
    if not experiment_rows and not archive_rows:
        return None
    iteration = _positive_int(state.get("current_iteration"), default=1)
    candidates = []
    completed_times = []
    for row in experiment_rows:
        if not isinstance(row, Mapping):
            continue
        evaluation = row.get("evaluation_result")
        admission = row.get("admission_decision")
        if not isinstance(evaluation, Mapping) or not isinstance(admission, Mapping):
            continue
        completed_at = row.get("completed_at")
        if isinstance(completed_at, str) and completed_at:
            completed_times.append(completed_at)
        candidates.append(
            {
                "genome_id": str(row.get("candidate_genome_id") or "unknown-candidate"),
                "parent_genome_ids": [
                    str(value) for value in row.get("parent_genome_ids", [])
                ],
                "admitted": bool(admission.get("admitted", False)),
                "admission_status": str(admission.get("status") or "legacy_unknown"),
                "metrics": _metric_subset(evaluation),
            }
        )
    best_entry = archive_rows[0] if archive_rows and isinstance(archive_rows[0], Mapping) else {}
    best_genome = best_entry.get("genome", {}) if isinstance(best_entry, Mapping) else {}
    best_evaluation = best_entry.get("evaluation", {}) if isinstance(best_entry, Mapping) else {}
    if not isinstance(best_genome, Mapping):
        best_genome = {}
    if not isinstance(best_evaluation, Mapping):
        best_evaluation = {}
    incumbent_id = str(best_genome.get("genome_id") or "unknown-incumbent")
    rejection_rows = experiments_artifact.get("candidate_rejections", [])
    return {
        "iteration": iteration,
        "completed_at": max(completed_times) if completed_times else "",
        "source": "legacy_latest_only",
        "incumbent_genome_id": incumbent_id,
        "archive_best_genome_id": incumbent_id,
        "archive_best_metrics": _metric_subset(best_evaluation),
        "candidate_count": len(candidates),
        "rejection_count": len(rejection_rows) if isinstance(rejection_rows, list) else 0,
        "candidates": candidates,
    }


def _metric_subset(evaluation: Mapping[str, Any]) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {}
    for key in (
        "sample_count",
        "binary_f1",
        "binary_precision",
        "binary_recall",
        "multiclass_macro_f1",
        "class_c_recall",
        "ordinal_distance",
        "data_cost_usd",
        "token_cost_usd",
        "latency_ms",
    ):
        value = evaluation.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            value = 0
        metrics[key] = value
    return metrics


def _validate_history(history: Mapping[str, Any]) -> None:
    if history.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise ValidationError("unsupported evolution history schema")
    if history.get("primary_metric") != "binary_f1":
        raise ValidationError("evolution dashboard requires binary_f1 as primary metric")
    if history.get("contains_final_test_metrics") is not False:
        raise ValidationError("evolution dashboard cannot include final-test metrics")
    rounds = history.get("rounds")
    if not isinstance(rounds, list):
        raise ValidationError("evolution history rounds must be a list")
    seen: set[int] = set()
    for row in rounds:
        if not isinstance(row, Mapping):
            raise ValidationError("evolution history round must be an object")
        iteration = _positive_int(row.get("iteration"), default=0)
        if iteration < 1 or iteration in seen:
            raise ValidationError("evolution history iterations must be unique positive integers")
        seen.add(iteration)
        if not isinstance(row.get("candidates", []), list):
            raise ValidationError("evolution history candidates must be a list")


def _positive_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read evolution dashboard artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"evolution dashboard artifact must be an object: {path}")
    return value


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    _write_text(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>信息方案自进化 Drift</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f5f3ee;
      --surface: #fffdf8;
      --text: #1d2528;
      --muted: #667277;
      --border: #d7d2c7;
      --grid: #ded9cf;
      --candidate: #cf6d3b;
      --median: #087f8c;
      --best: #3843a5;
      --focus: #087f8c;
      --warning-bg: #fff1cf;
      --warning-text: #654a00;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #171b1d;
        --surface: #202629;
        --text: #eef2f2;
        --muted: #aab4b7;
        --border: #3c464a;
        --grid: #343d41;
        --candidate: #f08a54;
        --median: #58c5cf;
        --best: #929cff;
        --focus: #58c5cf;
        --warning-bg: #4b3b12;
        --warning-text: #ffe39a;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main { max-width: 1180px; margin: 0 auto; padding: 28px 22px 48px; }
    header { display: flex; gap: 18px; align-items: flex-start; justify-content: space-between; }
    h1 { margin: 0; font-size: clamp(24px, 4vw, 40px); font-weight: 650; letter-spacing: -0.03em; }
    .subhead { margin: 8px 0 0; color: var(--muted); }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; justify-content: flex-end; }
    .run-picker { display: grid; gap: 5px; color: var(--muted); font-size: 13px; }
    button, select {
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 9px 13px;
      background: var(--surface);
      color: var(--text);
    }
    button { cursor: pointer; }
    button:focus-visible, select:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
    .summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 24px 0 18px; }
    .metric { border-top: 2px solid var(--border); padding-top: 10px; }
    .metric-label { color: var(--muted); font-size: 13px; }
    .metric-value { margin-top: 5px; font-size: clamp(22px, 3vw, 30px); font-variant-numeric: tabular-nums; }
    .chart-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 14px 14px 8px; }
    svg { display: block; width: 100%; height: auto; min-height: 340px; }
    .legend { display: flex; flex-wrap: wrap; gap: 16px; margin: 4px 8px 12px; color: var(--muted); font-size: 13px; }
    .legend span { display: inline-flex; gap: 7px; align-items: center; }
    .swatch { width: 22px; height: 3px; border-radius: 2px; background: currentColor; }
    .candidate-swatch { color: var(--candidate); }
    .median-swatch { color: var(--median); }
    .best-swatch { color: var(--best); }
    .note { margin: 16px 0; padding: 12px 14px; border-radius: 10px; background: var(--warning-bg); color: var(--warning-text); }
    .status { margin: 12px 0 0; color: var(--muted); font-size: 13px; }
    details { margin-top: 20px; }
    summary { cursor: pointer; color: var(--muted); }
    .table-scroll { overflow-x: auto; margin-top: 10px; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { padding: 9px 10px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
    th { color: var(--muted); font-weight: 600; }
    .empty { padding: 100px 20px; text-align: center; fill: var(--muted); }
    @media (max-width: 640px) {
      main { padding: 20px 14px 36px; }
      header { display: block; }
      .actions { margin-top: 14px; justify-content: flex-start; }
      .summary { grid-template-columns: 1fr; }
      svg { min-height: 300px; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>信息方案自进化 Drift</h1>
        <p class="subhead" id="run-label">固定指标：Binary F1 · 开发集轮次</p>
      </div>
      <div class="actions">
        <label class="run-picker" for="run-select">本地运行
          <select id="run-select" aria-label="选择本地运行"></select>
        </label>
        <button type="button" id="reload-button">重新读取本地记录</button>
      </div>
    </header>
    <section class="summary" aria-label="趋势摘要">
      <div class="metric"><div class="metric-label">已记录轮次</div><div class="metric-value" id="round-count">—</div></div>
      <div class="metric"><div class="metric-label">最新候选中位数</div><div class="metric-value" id="latest-median">—</div></div>
      <div class="metric"><div class="metric-label">中位数趋势斜率 / 轮</div><div class="metric-value" id="drift-slope">—</div></div>
    </section>
    <section class="chart-wrap" aria-label="轮次效果图">
      <svg id="drift-chart" viewBox="0 0 1040 520" role="img" aria-labelledby="chart-title chart-description">
        <title id="chart-title">信息方案逐轮 Binary F1</title>
        <desc id="chart-description">每轮候选散点、候选中位数和历史保留最优曲线。</desc>
      </svg>
      <div class="legend" aria-label="图例">
        <span><i class="swatch candidate-swatch"></i>当轮候选</span>
        <span><i class="swatch median-swatch"></i>候选中位数</span>
        <span><i class="swatch best-swatch"></i>历史保留最优</span>
      </div>
    </section>
    <p class="note">历史保留最优线因 Top-K 机制天然不会下降，不能单独证明存在向上 drift；应重点观察候选散点与候选中位数。</p>
    <p class="status" id="data-status"></p>
    <details>
      <summary>查看逐轮数值</summary>
      <div class="table-scroll"><table>
        <thead><tr><th>轮次</th><th>候选数</th><th>候选中位数</th><th>当轮候选最佳</th><th>历史保留最优</th><th>来源</th></tr></thead>
        <tbody id="history-table"></tbody>
      </table></div>
    </details>
  </main>
  <script src="evolution_dashboard_data.js"></script>
  <script>
    (() => {
      "use strict";
      const legacyHistory = window.__SCHEME_EVOLUTION_HISTORY__;
      const bundle = window.__SCHEME_EVOLUTION_DASHBOARD__ || {
        runs: legacyHistory ? [legacyHistory] : [],
        skipped_runs: []
      };
      const histories = Array.isArray(bundle.runs) ? bundle.runs : [];
      const skippedRuns = Array.isArray(bundle.skipped_runs) ? bundle.skipped_runs : [];
      const runSelect = document.getElementById("run-select");
      histories.forEach((history, index) => {
        const option = document.createElement("option");
        option.value = String(index);
        const roundCount = Array.isArray(history.rounds) ? history.rounds.length : 0;
        option.textContent = `${history.run_id || `运行 ${index + 1}`} · ${roundCount} 轮`;
        runSelect.appendChild(option);
      });
      if (!histories.length) {
        const option = document.createElement("option");
        option.textContent = "暂无本地运行";
        option.value = "";
        runSelect.appendChild(option);
        runSelect.disabled = true;
      }
      const number = value => Number.isFinite(Number(value)) ? Number(value) : null;
      const score = row => number(row && row.metrics && row.metrics.binary_f1);
      const median = values => {
        const sorted = values.filter(value => value !== null).slice().sort((a, b) => a - b);
        if (!sorted.length) return null;
        const middle = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
      };
      const slope = rows => {
        if (rows.length < 3) return null;
        const meanX = rows.reduce((sum, row) => sum + row.iteration, 0) / rows.length;
        const meanY = rows.reduce((sum, row) => sum + row.candidateMedian, 0) / rows.length;
        const numerator = rows.reduce((sum, row) => sum + (row.iteration - meanX) * (row.candidateMedian - meanY), 0);
        const denominator = rows.reduce((sum, row) => sum + Math.pow(row.iteration - meanX, 2), 0);
        return denominator ? numerator / denominator : null;
      };
      const format = value => value === null ? "—" : value.toFixed(3);
      document.getElementById("reload-button").addEventListener("click", () => window.location.reload());
      const table = document.getElementById("history-table");
      const svg = document.getElementById("drift-chart");
      const ns = "http://www.w3.org/2000/svg";
      const add = (name, attrs, text) => {
        const node = document.createElementNS(ns, name);
        Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));
        if (text !== undefined) node.textContent = text;
        svg.appendChild(node);
        return node;
      };
      const render = history => {
        const rounds = Array.isArray(history.rounds)
          ? history.rounds.slice().sort((a, b) => Number(a.iteration) - Number(b.iteration))
          : [];
        const summaries = rounds.map(round => {
          const candidateScores = Array.isArray(round.candidates) ? round.candidates.map(score).filter(value => value !== null) : [];
          return {
            iteration: Number(round.iteration),
            source: round.source || "unknown",
            candidateScores,
            candidateMedian: median(candidateScores),
            candidateBest: candidateScores.length ? Math.max(...candidateScores) : null,
            archiveBest: number(round.archive_best_metrics && round.archive_best_metrics.binary_f1),
            candidates: Array.isArray(round.candidates) ? round.candidates : []
          };
        });
        const medianRows = summaries.filter(row => row.candidateMedian !== null);
        document.getElementById("round-count").textContent = String(rounds.length);
        document.getElementById("latest-median").textContent = medianRows.length ? format(medianRows[medianRows.length - 1].candidateMedian) : "—";
        const driftSlope = slope(medianRows);
        document.getElementById("drift-slope").textContent = driftSlope === null ? "至少需要 3 轮" : `${driftSlope >= 0 ? "+" : ""}${driftSlope.toFixed(4)}`;
        document.getElementById("run-label").textContent = `${history.run_id || "本地运行"} · 固定指标 Binary F1 · 开发集轮次`;
        const legacyCount = summaries.filter(row => row.source === "legacy_latest_only").length;
        const skippedSuffix = skippedRuns.length ? `；另有 ${skippedRuns.length} 个无效运行被跳过` : "";
        document.getElementById("data-status").textContent = legacyCount
          ? `包含旧版运行可恢复的最后一轮；更早轮次没有足够记录，因此未被推测或补造${skippedSuffix}。`
          : `打开或刷新此页面时会读取统一的本地运行索引${skippedSuffix}。`;
        table.replaceChildren();
        summaries.forEach(row => {
          const tr = document.createElement("tr");
          [row.iteration, row.candidateScores.length, format(row.candidateMedian), format(row.candidateBest), format(row.archiveBest), row.source]
            .forEach(value => {
              const td = document.createElement("td");
              td.textContent = String(value);
              tr.appendChild(td);
            });
          table.appendChild(tr);
        });
        svg.replaceChildren();
        add("title", { id: "chart-title" }, "信息方案逐轮 Binary F1");
        add("desc", { id: "chart-description" }, "每轮候选散点、候选中位数和历史保留最优曲线。");
        if (!summaries.length) {
          add("text", { x: 520, y: 250, "text-anchor": "middle", class: "empty" }, "尚无已完成轮次；运行第一轮后这里会自动出现记录。 ");
          return;
        }
        const width = 1040, height = 520, left = 76, right = 28, top = 28, bottom = 66;
        const innerWidth = width - left - right, innerHeight = height - top - bottom;
        const iterations = summaries.map(row => row.iteration);
        const minRound = Math.min(...iterations), maxRound = Math.max(...iterations);
        const x = round => left + (maxRound === minRound ? innerWidth / 2 : (round - minRound) / (maxRound - minRound) * innerWidth);
        const y = value => top + (1 - Math.max(0, Math.min(1, value))) * innerHeight;
        for (let tick = 0; tick <= 5; tick += 1) {
          const value = tick / 5;
          add("line", { x1: left, y1: y(value), x2: width - right, y2: y(value), stroke: "var(--grid)", "stroke-width": 1 });
          add("text", { x: left - 12, y: y(value) + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 13 }, value.toFixed(1));
        }
        add("line", { x1: left, y1: top, x2: left, y2: height - bottom, stroke: "var(--border)", "stroke-width": 1 });
        add("line", { x1: left, y1: height - bottom, x2: width - right, y2: height - bottom, stroke: "var(--border)", "stroke-width": 1 });
        const tickStep = Math.max(1, Math.ceil(summaries.length / 12));
        summaries.forEach((row, index) => {
          if (index % tickStep !== 0 && index !== summaries.length - 1) return;
          add("text", { x: x(row.iteration), y: height - bottom + 27, "text-anchor": "middle", fill: "var(--muted)", "font-size": 13 }, String(row.iteration));
        });
        add("text", { x: width / 2, y: height - 13, "text-anchor": "middle", fill: "var(--muted)", "font-size": 14 }, "轮次");
        add("text", { x: 18, y: height / 2, transform: `rotate(-90 18 ${height / 2})`, "text-anchor": "middle", fill: "var(--muted)", "font-size": 14 }, "Binary F1");
        const path = (rows, key) => rows.filter(row => row[key] !== null).map((row, index) => `${index ? "L" : "M"}${x(row.iteration)},${y(row[key])}`).join(" ");
        const bestPath = path(summaries, "archiveBest");
        if (bestPath) add("path", { d: bestPath, fill: "none", stroke: "var(--best)", "stroke-width": 3, "stroke-linejoin": "round" });
        const medianPath = path(summaries, "candidateMedian");
        if (medianPath) add("path", { d: medianPath, fill: "none", stroke: "var(--median)", "stroke-width": 3, "stroke-linejoin": "round" });
        summaries.forEach(row => {
          row.candidates.forEach((candidate, index) => {
            const value = score(candidate);
            if (value === null) return;
            const spread = row.candidates.length > 1 ? (index / (row.candidates.length - 1) - 0.5) * 18 : 0;
            const circle = add("circle", {
              cx: x(row.iteration) + spread,
              cy: y(value),
              r: 5,
              fill: candidate.admitted ? "var(--candidate)" : "var(--surface)",
              stroke: "var(--candidate)",
              "stroke-width": 2
            });
            const title = document.createElementNS(ns, "title");
            title.textContent = `第 ${row.iteration} 轮 · ${candidate.genome_id} · F1 ${value.toFixed(3)} · ${candidate.admission_status}`;
            circle.appendChild(title);
          });
          if (row.candidateMedian !== null) add("circle", { cx: x(row.iteration), cy: y(row.candidateMedian), r: 5, fill: "var(--median)" });
          if (row.archiveBest !== null) add("rect", { x: x(row.iteration) - 4, y: y(row.archiveBest) - 4, width: 8, height: 8, fill: "var(--best)", transform: `rotate(45 ${x(row.iteration)} ${y(row.archiveBest)})` });
        });
      };
      runSelect.addEventListener("change", event => {
        const selected = histories[Number(event.target.value)];
        if (selected) render(selected);
      });
      render(histories[0] || { run_id: "本地运行", rounds: [] });
    })();
  </script>
</body>
</html>
"""

"""Drive k6 load rungs and parse the JSON summary for verdict numbers."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

K6_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "k6", "vector-search.js")


def parse_summary(summary: dict[str, Any], rung: dict[str, Any]) -> dict[str, Any]:
    """k6-summary -> rung result. Tolerant of k6 v1 (values-nested) and v2 (flat)."""

    def vals(name: str) -> dict[str, Any]:
        m = summary["metrics"].get(name, {})
        return m.get("values", m) if isinstance(m, dict) else {}

    offered = float(rung["rps"]) * _duration_s(str(rung.get("duration", "60s")))
    achieved = float(vals("http_reqs").get("count", 0))
    chk = vals("checks_failed") or vals("checks")
    failed = float(chk.get("fails", 0))
    total = float(chk.get("passes", 0)) + failed
    return {
        "offered": rung["rps"],
        "achieved": achieved,
        "achieved_pct": 100.0 * achieved / offered if offered else 0.0,
        "p50_ms": float(vals("http_req_duration").get("med", 0)),
        "p95_ms": float(vals("http_req_duration").get("p(95)", 0)),
        "p99_ms": float(vals("http_req_duration").get("p(99)", 0)),
        "error_rate": (failed / total) if total else 1.0,
    }


def run_rung(spec: dict[str, Any], rung: dict[str, Any], out_json: str) -> dict[str, Any]:
    base = os.environ[spec["target"]["url_env"]].rstrip("/")
    key = os.environ[spec["target"]["api_key_env"]]
    env = dict(
        os.environ,
        QDRANT_URL=base,
        QDRANT_API_KEY=key,
        COLLECTION=spec["collection"]["name"],
        RATE=str(rung["rps"]),
        DUR=str(rung.get("duration", "60s")),
        EF=str(rung.get("ef", 100)),
        TOPK=str(rung.get("top_k", 10)),
        TENANTS=str(spec["dataset"]["tenants"]),
        CORP=str(spec["dataset"].get("corpora_per_tenant", 1)),
        CORP_PICK=str(rung.get("corpus_pick", 2)),
        DIM=str(spec["collection"]["dim"]),
        FILTER_JSON=json.dumps(spec["filter"]),
    )
    print(
        f"rung {rung['rps']} RPS x {rung.get('duration', '60s')} "
        f"(ef={rung.get('ef', 100)} top_k={rung.get('top_k', 10)}) ...",
        flush=True,
    )
    # No --quiet: k6's live progress goes to the terminal; the JSON summary
    # is still exported for verdict parsing.
    try:
        subprocess.run(
            [
                "k6",
                "run",
                "--summary-mode",
                "full",
                "--summary-trend-stats",
                "avg,med,p(90),p(95),p(99),max",
                "--summary-export",
                out_json,
                K6_SCRIPT,
            ],
            env=env,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        # k6 exits 99 on threshold breach — the summary is still written, so
        # score the rung as FAIL with real numbers instead of a traceback.
        if os.path.exists(out_json):
            print(
                f"rung exited k6={e.returncode} (threshold breach) — scoring from summary",
                flush=True,
            )
        else:
            raise
    with open(out_json) as f:
        summary = json.load(f)
    return parse_summary(summary, rung)


def _duration_s(dur: str) -> float:
    dur = dur.strip()
    if dur.endswith("s"):
        return float(dur[:-1])
    if dur.endswith("m"):
        return float(dur[:-1]) * 60
    raise ValueError(f"unsupported duration: {dur}")

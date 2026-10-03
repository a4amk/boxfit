"""Drive k6 load rungs and parse the JSON summary for verdict numbers."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

K6_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "k6", "vector-search.js")


def _pct(summary: dict[str, Any], metric: str, field: str) -> float:
    return float(summary["metrics"][metric]["values"][field])


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
    subprocess.run(
        ["k6", "run", "--quiet", "--summary-export", out_json, K6_SCRIPT],
        env=env,
        check=True,
    )
    with open(out_json) as f:
        summary = json.load(f)
    metrics = summary["metrics"]
    offered = float(rung["rps"]) * _duration_s(str(rung.get("duration", "60s")))
    achieved = float(metrics["http_reqs"]["values"]["count"])
    failed = float(metrics.get("checks_failed", {}).get("values", {}).get("fails", 0))
    total = float(metrics.get("checks_failed", {}).get("values", {}).get("passes", 0)) + failed
    return {
        "offered": rung["rps"],
        "achieved": achieved,
        "achieved_pct": 100.0 * achieved / offered if offered else 0.0,
        "p50_ms": _pct(summary, "http_req_duration", "med"),
        "p95_ms": _pct(summary, "http_req_duration", "p(95)"),
        "p99_ms": _pct(summary, "http_req_duration", "p(99)"),
        "error_rate": (failed / total) if total else 1.0,
    }


def _duration_s(dur: str) -> float:
    dur = dur.strip()
    if dur.endswith("s"):
        return float(dur[:-1])
    if dur.endswith("m"):
        return float(dur[:-1]) * 60
    raise ValueError(f"unsupported duration: {dur}")

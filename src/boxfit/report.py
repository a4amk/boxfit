"""Markdown report + PASS/FAIL verdict against the spec SLO."""

from __future__ import annotations

from typing import Any


def verdict(results: list[dict[str, Any]], slo: dict[str, Any]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    ok = True
    for r in results:
        checks = [
            (r["p50_ms"] <= float(slo["p50_ms"]), f"p50 {r['p50_ms']:.1f}ms"),
            (r["p99_ms"] <= float(slo["p99_ms"]), f"p99 {r['p99_ms']:.1f}ms"),
            (r["error_rate"] <= float(slo["error_rate"]), f"errors {r['error_rate']:.4f}"),
            (
                r["achieved_pct"] >= float(slo["achieved_pct"]),
                f"achieved {r['achieved_pct']:.1f}%",
            ),
        ]
        for passed, label in checks:
            if not passed:
                ok = False
                notes.append(f"rung {r['offered']} RPS FAIL: {label}")
    return ok, notes


def rung_rows(results: list[dict[str, Any]]) -> list[str]:
    rows = [
        "| Offered | Achieved | Achieved % | p50 | p95 | p99 | Error rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        rows.append(
            f"| {r['offered']} | {r['achieved']:.0f} | {r['achieved_pct']:.1f}% "
            f"| {r['p50_ms']:.1f}ms | {r['p95_ms']:.1f}ms | {r['p99_ms']:.1f}ms "
            f"| {r['error_rate']:.4f} |"
        )
    return rows


def write_report(spec: dict[str, Any], results: list[dict[str, Any]], path: str) -> bool:
    ok, notes = verdict(results, spec["slo"])
    lines = [f"# boxfit verdict: {'PASS' if ok else 'FAIL'} — {spec['name']}", ""]
    lines += rung_rows(results)
    if notes:
        lines += ["", "## SLO breaches", *[f"- {n}" for n in notes]]
    lines += ["", f"SLO: {spec['slo']}", ""]
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"verdict: {'PASS' if ok else 'FAIL'} -> {path}")
    return ok


def write_combined(
    runs: list[tuple[str, bool, list[dict[str, Any]]]], path: str
) -> bool:
    """Combined verdict across workloads: (name, ok, results) per workload."""
    overall = all(ok for _, ok, _ in runs)
    lines = [
        f"# boxfit verdict: {'PASS' if overall else 'FAIL'} — {len(runs)} workloads",
        "",
        "| Workload | Verdict |",
        "|---|---|",
    ]
    for name, ok, _ in runs:
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")
    for name, _, results in runs:
        lines += ["", f"## {name}", ""] + rung_rows(results)
    lines += [""]
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"combined verdict: {'PASS' if overall else 'FAIL'} -> {path}")
    return overall

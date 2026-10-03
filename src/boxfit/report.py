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


def write_report(spec: dict[str, Any], results: list[dict[str, Any]], path: str) -> bool:
    ok, notes = verdict(results, spec["slo"])
    lines = [
        f"# boxfit verdict: {'PASS' if ok else 'FAIL'} — {spec['name']}",
        "",
        "| Offered | Achieved | Achieved % | p50 | p95 | p99 | Error rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['offered']} | {r['achieved']:.0f} | {r['achieved_pct']:.1f}% "
            f"| {r['p50_ms']:.1f}ms | {r['p95_ms']:.1f}ms | {r['p99_ms']:.1f}ms "
            f"| {r['error_rate']:.4f} |"
        )
    if notes:
        lines += ["", "## SLO breaches", *[f"- {n}" for n in notes]]
    lines += ["", f"SLO: {spec['slo']}", ""]
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"verdict: {'PASS' if ok else 'FAIL'} -> {path}")
    return ok

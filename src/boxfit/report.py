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
        "| Offered | Achieved | Achieved % | p50 | p95 | p99 | Errors | Qdrant CPU avg/max | Qdrant mem max |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        rows.append(
            f"| {r['offered']} | {r['achieved']:.0f} | {r['achieved_pct']:.1f}% "
            f"| {r['p50_ms']:.1f}ms | {r['p95_ms']:.1f}ms | {r['p99_ms']:.1f}ms "
            f"| {r['error_rate']:.4f} | {r.get('qdrant_cpu_avg')}% / {r.get('qdrant_cpu_max')}% "
            f"| {r.get('qdrant_mem_max_mib')} MiB |"
        )
    return rows


def context_block(context: dict[str, Any] | None) -> list[str]:
    if not context:
        return []
    host = context.get("host", {})
    coll = context.get("collection", {})
    lines = [
        "## Setup",
        "",
        f"Host: {host.get('nproc')} CPUs, {host.get('mem_gb')} GB RAM, "
        f"{host.get('disk_free_gb')} GB disk free (at report time).",
        f"Collection `{coll.get('name')}`: {coll.get('points')} points, "
        f"{coll.get('segments')} segments.",
    ]
    ceil = context.get("ceiling_rps")
    if ceil is not None:
        line = (
            f"Estimated hardware ceiling: ~{ceil:.0f} RPS (CPU-bound projection "
            f"to the {context.get('cpu_cap_pct')}% cap)"
        )
        if context.get("ceiling_note"):
            line += f" — {context['ceiling_note']}"
        lines.append(line + ".")
    elif context.get("ceiling_note"):
        lines.append(f"Ceiling: not projected ({context['ceiling_note']}).")
    return lines + [""]


def write_report(
    spec: dict[str, Any],
    results: list[dict[str, Any]],
    path: str,
    context: dict[str, Any] | None = None,
) -> bool:
    ok, notes = verdict(results, spec["slo"])
    lines = [f"# boxfit verdict: {'PASS' if ok else 'FAIL'} — {spec['name']}", ""]
    lines += rung_rows(results)
    if notes:
        lines += ["", "## SLO breaches", *[f"- {n}" for n in notes]]
    lines += ["", f"SLO: {spec['slo']}", ""]
    lines += context_block(context)
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"verdict: {'PASS' if ok else 'FAIL'} -> {path}")
    return ok


def write_combined(
    runs: list[tuple[str, bool, list[dict[str, Any]], dict[str, Any] | None]],
    path: str,
    context: dict[str, Any] | None = None,
) -> bool:
    """Combined verdict across workloads: (name, ok, results[, context]) each."""
    overall = all(ok for _, ok, *_ in runs)
    lines = [
        f"# boxfit verdict: {'PASS' if overall else 'FAIL'} — {len(runs)} workloads",
        "",
        "| Workload | Verdict |",
        "|---|---|",
    ]
    for name, ok, *_ in runs:
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")
    for run in runs:
        name, _, results = run[0], run[1], run[2]
        lines += ["", f"## {name}", ""] + rung_rows(results)
        ctx = run[3] if len(run) > 3 else None
        if ctx:
            lines += [""] + context_block(ctx)
    lines += [""]
    lines += context_block(context)
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"combined verdict: {'PASS' if overall else 'FAIL'} -> {path}")
    return overall

"""boxfit CLI: seed, ingest, gate, load, report. Exit 0 on PASS, 1 on FAIL.

Workload discovery: --spec FILE, else ./workload.yaml, else .workload/*.yaml
(alphabetical). Multi-workload runs get per-workload reports plus one combined
verdict; any FAIL fails the run.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import Any

from boxfit import load_spec
from boxfit.correctness import gate
from boxfit.dataset import dataset_path, generate
from boxfit.ingest import ingest
from boxfit.load import run_rung
from boxfit.ready import await_indexed, warm
from boxfit.report import verdict, write_combined, write_report
from boxfit.seed import seed
from boxfit.targets import make_target


def discover_specs(explicit: str | None) -> list[str]:
    if explicit:
        return [explicit]
    if os.path.exists("workload.yaml"):
        return ["workload.yaml"]
    found = sorted(glob.glob(os.path.join(".workload", "*.yaml")))
    found += sorted(glob.glob(os.path.join(".workload", "*.yml")))
    if not found:
        raise FileNotFoundError("no workload: pass --spec, or add ./workload.yaml or .workload/*.yaml")
    return found


def preflight(spec: dict[str, Any], stages: set[str], workdir: str) -> None:
    """Fail in seconds, not after 30 silent minutes. Every check is instant."""
    import shutil
    import urllib.request

    for var in (spec["target"]["url_env"], spec["target"]["api_key_env"]):
        if not os.environ.get(var):
            raise ValueError(f"env var {var} is not set (see .env.example)")
    base = os.environ[spec["target"]["url_env"]].rstrip("/")
    try:
        urllib.request.urlopen(base + "/", timeout=10).read()
    except Exception as e:
        raise ValueError(f"target unreachable at {base}: {e}")
    if "load" in stages and shutil.which("k6") is None:
        raise ValueError("k6 not found on PATH (load stage needs it)")
    if "ingest" in stages:
        vecs = os.path.join(workdir, "vecs.npy")
        if os.path.exists(vecs):
            import numpy as np

            have = len(np.load(vecs, mmap_mode="r"))
            want = int(spec["dataset"]["vectors"])
            if have != want:
                raise ValueError(f"stale dataset: {vecs} has {have}, spec wants {want}")
    if stages & {"ready", "gate", "load"}:
        key = os.environ[spec["target"]["api_key_env"]]
        try:
            make_target(spec, base, key).points_count(spec)
        except Exception as e:
            raise ValueError(f"collection not ready for {sorted(stages)}: {e}")
    print("preflight ok", flush=True)


def run_workload(spec: dict[str, Any], workdir: str, stages: set[str]) -> list[dict[str, Any]]:
    os.makedirs(workdir, exist_ok=True)
    base = os.environ[spec["target"]["url_env"]].rstrip("/")
    key = os.environ[spec["target"]["api_key_env"]]
    if "seed" in stages:
        seed(spec)
    if "ingest" in stages:
        if not os.path.exists(dataset_path(workdir)):
            generate(spec, workdir)
        ingest(spec, workdir)
    if "ready" in stages:
        target = make_target(spec, base, key)
        await_indexed(target, spec)
        warm(target, spec, workdir, n=int(spec.get("warmup_queries", 200)))
    if "gate" in stages:
        gate(spec)
    results = []
    if "load" in stages:
        for i, rung in enumerate(spec["load"]):
            out = os.path.join(workdir, f"k6-rung{i}.json")
            results.append(run_rung(spec, rung, out))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(prog="boxfit")
    ap.add_argument("--spec", default=None, help="workload YAML (default: ./workload.yaml, else .workload/*.yaml)")
    ap.add_argument("--workdir", default="./boxfit-work", help="dataset staging dir")
    ap.add_argument("--report", default="boxfit-report.md", help="verdict report path")
    ap.add_argument(
        "--stage",
        default="all",
        choices=("all", "seed", "ingest", "ready", "gate", "load"),
        help="run one stage or the full pipeline",
    )
    args = ap.parse_args()
    try:
        paths = discover_specs(args.spec)
    except FileNotFoundError as e:
        ap.error(str(e))
    stages = {"seed", "ingest", "ready", "gate", "load"} if args.stage == "all" else {args.stage}

    if len(paths) == 1 and args.stage == "all":
        spec = load_spec(paths[0])
        preflight(spec, stages, args.workdir)
        results = run_workload(spec, args.workdir, stages)
        return 0 if write_report(spec, results, args.report) else 1

    runs: list[tuple[str, bool, list[dict[str, Any]]]] = []
    for path in paths:
        spec = load_spec(path)
        subdir = os.path.join(args.workdir, spec["name"].replace(" ", "-"))
        preflight(spec, stages, subdir)
        if args.stage == "all":
            results = run_workload(spec, subdir, stages)
            ok, _ = verdict(results, spec["slo"])
            write_report(spec, results, f"boxfit-{spec['name']}.md")
            runs.append((spec["name"], ok, results))
        else:
            run_workload(spec, subdir, stages)
    if args.stage == "all":
        return 0 if write_combined(runs, args.report) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

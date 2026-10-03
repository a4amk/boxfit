"""boxfit CLI: seed, ingest, gate, load, report. Exit 0 on PASS, 1 on FAIL."""

from __future__ import annotations

import argparse
import os
import sys

from boxfit import load_spec
from boxfit.correctness import gate
from boxfit.dataset import generate
from boxfit.ingest import ingest
from boxfit.load import run_rung
from boxfit.report import write_report
from boxfit.seed import seed


def main() -> int:
    ap = argparse.ArgumentParser(prog="boxfit")
    ap.add_argument(
        "--spec",
        default="workload.yaml",
        help="workload YAML (default: ./workload.yaml — copy workload.example.yaml)",
    )
    ap.add_argument("--workdir", default="./boxfit-work", help="dataset staging dir")
    ap.add_argument("--report", default="boxfit-report.md", help="verdict report path")
    ap.add_argument(
        "--stage",
        default="all",
        choices=("all", "seed", "ingest", "gate", "load"),
        help="run one stage or the full pipeline",
    )
    args = ap.parse_args()
    if not os.path.exists(args.spec):
        ap.error(f"no workload file at {args.spec} — copy workload.example.yaml first")
    spec = load_spec(args.spec)
    os.makedirs(args.workdir, exist_ok=True)

    if args.stage in ("all", "seed"):
        seed(spec)
    if args.stage in ("all", "ingest"):
        if not os.path.exists(os.path.join(args.workdir, "vecs.npy")):
            generate(spec, args.workdir)
        ingest(spec, args.workdir)
    if args.stage in ("all", "gate"):
        gate(spec)
    results = []
    if args.stage in ("all", "load"):
        for i, rung in enumerate(spec["load"]):
            out = os.path.join(args.workdir, f"k6-rung{i}.json")
            results.append(run_rung(spec, rung, out))
    if args.stage == "all":
        return 0 if write_report(spec, results, args.report) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

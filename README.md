# boxfit

Workload acceptance for self-hosted vector databases. Spec in, PASS/FAIL verdict out.

boxfit is **not a benchmark** — it doesn't rank databases or test index science
(the vendors and the industry already do that). It answers one question:

> Will **this box** survive **my workload**?

You describe your schema, dataset, traffic, and SLO in a workload YAML.
boxfit seeds the schema, ingests the data, gates correctness (filter
predicates hold, no cross-tenant leaks), runs the load ladder with k6, and
reports PASS/FAIL with an exit code fit for CI.

## Requirements

- Python 3.10+, `pip install -e .` (needs `numpy`, `pyyaml`)
- k6 on PATH (load driver)
- A reachable Qdrant over REST (no gRPC needed, no client library needed)

## Quickstart

```bash
cp .env.example .env # fill in your values; .env is git-ignored, never commit it
set -a; source .env; set +a
export QDRANT_URL QDRANT_API_KEY

# full pipeline: seed -> ingest -> correctness gate -> load ladder -> verdict
# (no --spec: runs ./workload.yaml — copy workload.example.yaml first)
python -m boxfit

# one stage at a time (or point at a checked-in workload directly)
python -m boxfit --stage seed
python -m boxfit --spec workloads/saas-tenant-corpus.yaml

# multiple workloads: drop them in .workload/ (git-ignored), bare boxfit
# runs each in turn and writes one combined verdict (any FAIL fails all)
mkdir -p .workload && cp workloads/single-namespace.yaml .workload/
python -m boxfit
```

Exit code is 0 on PASS, 1 on FAIL. Report lands in `boxfit-report.md`.

## Workload spec

```yaml
name: saas-tenant-corpus-5M
target:
  url_env: QDRANT_URL # env var holding the base URL (secrets never in files)
  api_key_env: QDRANT_API_KEY
  engine: qdrant # the only shipped engine; add one in src/boxfit/targets.py
collection:
  name: boxfit_saas
  dim: 512
  datatype: uint8 # float32 | float16 | uint8
  distance: Cosine
  on_disk_payload: true
  hnsw: { m: 16, ef_construct: 128 }
  payload_indexes:
    - { field: tenant_id, kind: keyword, is_tenant: true }
    - { field: corpus_id, kind: keyword }
dataset:
  vectors: 5000000
  tenants: 500
  corpora_per_tenant: 5
  clusters_per_tenant: 2
  seed: 20250
filter: # SSOT: seed, ingest, k6, and the correctness gate render from here
  tenant: { field: tenant_id, match: value }
  corpus: { field: corpus_id, match: any } # multi-value match is `any`, never array-`value`
  # either clause may be null (absent); both null is a legitimate unfiltered
  # worst case. See workloads/single-namespace.yaml for a corpus-less shape.
load: # one rung per entry, run in order
  - { rps: 100, duration: 60s, ef: 100, top_k: 10, corpus_pick: 2 }
  - { rps: 250, duration: 120s, ef: 100, top_k: 10, corpus_pick: 2 }
slo: # every rung must meet all four
  { p50_ms: 10, p99_ms: 100, error_rate: 0.02, achieved_pct: 99 }
```

Dataset layout is derivable from the point id (tenant = id // per_tenant),
so ingest is resumable and idempotent: re-running a slice upserts identical
points, and every slice is gated on `visible == sent`.

## Example workloads

Start from a copy — never edit these in place for your own runs:
`cp workloads/minimal.yaml my-workload.yaml`, set your values, run it.

- `workloads/saas-tenant-corpus.yaml` — 5M vectors, 500 tenants × 5 corpora,
  tenant + 2-corpus IN-list filter. The full multi-tenant shape.
- `workloads/single-namespace.yaml` — 200k vectors, single `namespace` value
  filter, no corpus layer. Mid-size smoke for new boxes.
- `workloads/minimal.yaml` — 10k vectors, 128-dim, one 50 RPS rung. First run
  for contributors: exercises every stage in ~2 minutes.

## Notes

- Multi-value match uses Qdrant's `match: {any: [...]}` (array-`value` is a 400).
- Reference arrays stay mmap'd with per-block conversion — never `.astype()`
  a multi-million-row mmap (5M uint8 → 10GB float32 will OOM the harness).
- Warm the index after any restart (one recall pass) before measuring —
  first-run-cold numbers measure page cache, not capacity.

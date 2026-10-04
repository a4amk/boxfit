"""Index-readiness wait: don't measure an index that isn't built yet.

Bulk ingest returns long before HNSW indexing finishes. Measuring during that
window benchmarks full-scan fallback, not the index (we learned this the hard
way: 36s medians on an index that was 13% built). Polls until every point is
indexed, then warms the page cache: a freshly indexed collection is cold, and
the first rung would otherwise measure disk faults, not capacity.
"""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np

from boxfit.targets import Target


def await_indexed(target: Target, spec: dict[str, Any], timeout_s: float = 3600) -> None:
    if target.indexed_count is None:
        return
    deadline = time.time() + timeout_s
    waited = 0
    while True:
        total = target.points_count(spec)
        indexed = target.indexed_count(spec)
        if indexed is not None and indexed >= total > 0:
            print(f"index ready: points={total} indexed={indexed}")
            return
        if time.time() > deadline:
            raise TimeoutError(f"index not ready: points={total} indexed={indexed}")
        time.sleep(10)
        waited += 10
        if waited % 60 == 0:
            print(f"  waiting for index: points={total} indexed={indexed} ({waited}s)", flush=True)


def warm(target: Target, spec: dict[str, Any], workdir: str, n: int = 200) -> None:
    """N real filtered searches to fault the working set into page cache."""
    from boxfit.dataset import dataset_path  # local import: keeps ready.py light

    n_total = int(spec["dataset"]["vectors"])
    tenants = int(spec["dataset"]["tenants"])
    corpora = int(spec["dataset"].get("corpora_per_tenant", 1))
    per_tenant = n_total // tenants
    dim = int(spec["collection"]["dim"])
    tenant = spec["filter"].get("tenant")
    corpus = spec["filter"].get("corpus")
    vecs = np.load(dataset_path(workdir), mmap_mode="r")
    rng = np.random.default_rng(1)
    for qi in rng.choice(n_total, size=min(n, n_total), replace=False):
        idx = int(qi)
        t = idx // per_tenant
        tt = f"t-{t:03d}"
        must: list[dict[str, object]] = []
        if tenant is not None:
            must.append({"key": tenant["field"], "match": {"value": tt}})
        if corpus is not None:
            corps = [f"{tt}-c{(idx + k) % corpora}" for k in range(min(2, corpora))]
            must.append({"key": corpus["field"], "match": {"any": corps}})
        target.search(
            spec,
            {
                "vector": [int(x) for x in vecs[idx][:dim]],
                "limit": 10,
                "with_vector": False,
                "filter": {"must": must},
                "params": {"hnsw_ef": 100},
            },
        )
    print(f"warmup done ({min(n, n_total)} queries)")

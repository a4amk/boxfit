"""Clustered dataset generator: tenants x corpora x clusters, uint8 memmap.

Layout is derivable from the point index (no sidecar arrays):
  tenant = idx // per_tenant, corpus = (idx % per_tenant) % corpora_per_tenant.
"""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np


def dataset_path(workdir: str) -> str:
    return os.path.join(workdir, "vecs.npy")


def centroids_path(workdir: str) -> str:
    return os.path.join(workdir, "cent.npy")


def generate(spec: dict[str, Any], workdir: str) -> None:
    ds = spec["dataset"]
    n = int(ds["vectors"])
    tenants = int(ds["tenants"])
    corpora = int(ds.get("corpora_per_tenant", 1))
    clusters = int(ds.get("clusters_per_tenant", 2))
    per_tenant = n // tenants
    per_cluster = per_tenant // clusters
    assert per_cluster * clusters == per_tenant, "vectors must split evenly into clusters"
    os.makedirs(workdir, exist_ok=True)

    t0 = time.time()
    rng = np.random.default_rng(int(ds["seed"]))
    n_clu = tenants * clusters
    centers = rng.standard_normal((n_clu, int(spec["collection"]["dim"])))
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)
    np.save(centroids_path(workdir), centers.astype(np.float32))
    del centers
    saved = np.load(centroids_path(workdir)).astype(np.float64)

    out = np.lib.format.open_memmap(
        dataset_path(workdir),
        mode="w+",
        dtype=np.uint8,
        shape=(n, int(spec["collection"]["dim"])),
    )
    r = np.random.default_rng(int(ds["seed"]) + 1)
    for t in range(tenants):
        base = t * per_tenant
        for c in range(clusters):
            m = saved[t * clusters + c] + r.standard_normal((per_cluster, int(spec["collection"]["dim"]))) * 0.2
            m /= np.linalg.norm(m, axis=1, keepdims=True)
            out[base + c * per_cluster : base + (c + 1) * per_cluster] = np.round(
                (np.clip(m, -1, 1) + 1) / 2 * 255
            ).astype(np.uint8)
            del m
        if (t + 1) % 50 == 0:
            out.flush()
            print(f"tenants {t + 1}/{tenants} elapsed={time.time() - t0:.0f}s", flush=True)
    out.flush()
    del out
    print(f"dataset saved ({n} vectors) elapsed={time.time() - t0:.0f}s")

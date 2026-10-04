"""Chunked, resumable, visibility-gated bulk ingest (engine via targets.py)."""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np

from boxfit.dataset import dataset_path
from boxfit.targets import make_target

BATCH = 1000


def tenant_of(idx: int, per_tenant: int) -> int:
    return idx // per_tenant


def ingest(spec: dict[str, Any], workdir: str, slice_vectors: int = 500000) -> None:
    base = os.environ[spec["target"]["url_env"]].rstrip("/")
    key = os.environ[spec["target"]["api_key_env"]]
    target = make_target(spec, base, key)
    n = int(spec["dataset"]["vectors"])
    tenants = int(spec["dataset"]["tenants"])
    corpora = int(spec["dataset"].get("corpora_per_tenant", 1))
    per_tenant = n // tenants
    tenant = spec["filter"].get("tenant")
    corpus = spec["filter"].get("corpus")
    vecs = np.load(dataset_path(workdir), mmap_mode="r")
    for lo in range(0, n, slice_vectors):
        hi = min(lo + slice_vectors, n)
        before = target.points_count(spec)
        t0 = time.time()
        sent = 0
        last_beat = t0
        for b in range(lo, hi, BATCH):
            e = min(b + BATCH, hi)
            pts = []
            for i in range(b, e):
                tt = tenant_of(i, per_tenant)
                payload: dict[str, object] = {"chunk_id": int(i), "vid": f"boxfit-{i:07d}"}
                if tenant is not None:
                    payload[tenant["field"]] = f"t-{tt:03d}"
                if corpus is not None:
                    payload[corpus["field"]] = f"t-{tt:03d}-c{(i % per_tenant) % corpora}"
                pts.append({"id": int(i), "vector": [int(x) for x in vecs[i]], "payload": payload})
            target.upsert(spec, pts)
            sent += len(pts)
            if time.time() - last_beat >= 60:
                el = time.time() - t0
                print(f"  slice [{lo},{hi}) heartbeat: sent={sent} elapsed={el:.0f}s", flush=True)
                last_beat = time.time()
        after = before
        for _ in range(60):
            time.sleep(5)
            after = target.points_count(spec)
            if after == before + sent:
                break
        dt = time.time() - t0
        print(f"slice [{lo},{hi}) sent={sent} visible={after} secs={dt:.1f} rps={sent / dt:.0f}")
        if after != before + sent:
            raise RuntimeError(f"visibility mismatch in slice [{lo},{hi})")

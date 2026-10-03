"""Setup-correctness gate: filter predicates hold, no cross-tenant leakage.

This validates YOUR schema and data loading — not Qdrant's index science.
Small, fast, runs before the load ladder.
"""

from __future__ import annotations

import os
from typing import Any

from boxfit.targets import make_target


def gate(spec: dict[str, Any], probes: int = 10) -> None:
    base = os.environ[spec["target"]["url_env"]].rstrip("/")
    key = os.environ[spec["target"]["api_key_env"]]
    target = make_target(spec, base, key)
    dim = int(spec["collection"]["dim"])
    tenants = int(spec["dataset"]["tenants"])
    corpora = int(spec["dataset"].get("corpora_per_tenant", 1))
    tenant = spec["filter"].get("tenant")
    corpus = spec["filter"].get("corpus")
    for p in range(probes):
        t = (p * 37) % tenants  # deterministic spread, no RNG state
        tt = f"t-{t:03d}"
        must: list[dict[str, object]] = []
        corps: list[str] = []
        if tenant is not None:
            must.append({"key": tenant["field"], "match": {"value": tt}})
        if corpus is not None:
            corps = [f"{tt}-c{(p + k) % corpora}" for k in range(min(2, corpora))]
            must.append({"key": corpus["field"], "match": {"any": corps}})
        include = [part["field"] for part in (tenant, corpus) if part is not None]
        res = target.search(
            spec,
            {
                "vector": [128] * dim,
                "limit": 10,
                "with_vector": False,
                "with_payload": {"include": include},
                "filter": {"must": must},
                "params": {"hnsw_ef": 100},
            },
        )
        assert res, f"probe {p}: empty result for {tt}"
        for hit in res:
            payload = hit["payload"]
            if tenant is not None:
                assert payload[tenant["field"]] == tt, f"probe {p}: tenant leak {payload}"
            if corpus is not None:
                assert payload[corpus["field"]] in corps, f"probe {p}: corpus leak {payload}"
    print(f"correctness gate passed ({probes} probes, no leaks)")

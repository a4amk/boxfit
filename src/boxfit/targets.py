"""Engine seam: all Qdrant specifics live here, behind the Target protocol.

boxfit is Qdrant-first by design (depth over breadth — cross-engine comparison
is VectorDBBench's job). A second engine means adding one module implementing
Target plus its filter builder; the pipeline (seed/ingest/gate/load/report)
does not change.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Protocol


class Target(Protocol):
    name: str

    def seed(self, spec: dict[str, Any]) -> None: ...
    def upsert(self, spec: dict[str, Any], points: list[dict[str, Any]]) -> None: ...
    def search(self, spec: dict[str, Any], body: dict[str, Any]) -> list[Any]: ...
    def points_count(self, spec: dict[str, Any]) -> int: ...
    def indexed_count(self, spec: dict[str, Any]) -> int | None:
        """Points covered by the index. None = engine can't report; skip the wait."""
        return None


def _req(base: str, key: str, method: str, path: str, body: Any = None) -> Any:
    headers = {"api-key": key, "content-type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else None


class QdrantTarget:
    """Qdrant over plain REST (no client dep, no gRPC)."""

    name = "qdrant"

    def __init__(self, base: str, key: str) -> None:
        self.base = base.rstrip("/")
        self.key = key

    def seed(self, spec: dict[str, Any]) -> None:
        coll = spec["collection"]
        name = coll["name"]
        try:
            _req(self.base, self.key, "DELETE", f"/collections/{name}")
        except Exception:
            pass
        _req(
            self.base,
            self.key,
            "PUT",
            f"/collections/{name}",
            {
                "vectors": {
                    "size": coll["dim"],
                    "distance": coll["distance"],
                    "datatype": coll["datatype"],
                },
                "shard_number": 1,
                "replication_factor": 1,
                "on_disk_payload": coll.get("on_disk_payload", True),
                "hnsw_config": {
                    "m": coll.get("hnsw", {}).get("m", 16),
                    "ef_construct": coll.get("hnsw", {}).get("ef_construct", 128),
                    "full_scan_threshold": 10000,
                    "max_indexing_threads": 2,
                },
                "optimizers_config": {
                    "default_segment_number": 2,
                    "max_segment_size": 500000,
                    "indexing_threshold": 20000,
                    "flush_interval_sec": 5,
                    "max_optimization_threads": 1,
                },
            },
        )
        for idx in coll.get("payload_indexes", []):
            schema: Any = {"type": idx["kind"]}
            if idx.get("is_tenant"):
                schema = {"type": idx["kind"], "is_tenant": True}
            _req(
                self.base,
                self.key,
                "PUT",
                f"/collections/{name}/index",
                {"field_name": idx["field"], "field_schema": schema},
            )
        print(f"seeded collection {name}")

    def upsert(self, spec: dict[str, Any], points: list[dict[str, Any]]) -> None:
        name = spec["collection"]["name"]
        _req(
            self.base,
            self.key,
            "PUT",
            f"/collections/{name}/points?wait=false",
            {"points": points},
        )

    def search(self, spec: dict[str, Any], body: dict[str, Any]) -> list[Any]:
        name = spec["collection"]["name"]
        return _req(self.base, self.key, "POST", f"/collections/{name}/points/search", body)[
            "result"
        ]

    def points_count(self, spec: dict[str, Any]) -> int:
        name = spec["collection"]["name"]
        return _req(self.base, self.key, "GET", f"/collections/{name}")["result"]["points_count"]

    def indexed_count(self, spec: dict[str, Any]) -> int | None:
        name = spec["collection"]["name"]
        return _req(self.base, self.key, "GET", f"/collections/{name}")["result"].get(
            "indexed_vectors_count"
        )


def make_target(spec: dict[str, Any], base: str, key: str) -> Target:
    engine = spec.get("target", {}).get("engine", "qdrant")
    if engine == "qdrant":
        return QdrantTarget(base, key)
    raise ValueError(f"unknown engine: {engine} (boxfit ships qdrant only)")

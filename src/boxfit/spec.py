"""Workload spec loading and validation (stdlib + PyYAML only)."""

from __future__ import annotations

from typing import Any

import yaml

REQUIRED_TOP = ("name", "target", "collection", "dataset", "filter", "load", "slo")


def load_spec(path: str) -> dict[str, Any]:
    with open(path) as f:
        spec = yaml.safe_load(f)
    if not isinstance(spec, dict):
        raise ValueError("spec must be a YAML mapping")
    for key in REQUIRED_TOP:
        if key not in spec:
            raise ValueError(f"spec missing required key: {key}")
    _validate_target(spec["target"])
    _validate_collection(spec["collection"])
    _validate_dataset(spec["dataset"])
    _validate_filter(spec["filter"], spec["collection"])
    if not isinstance(spec["load"], list) or not spec["load"]:
        raise ValueError("spec.load must be a non-empty list of rungs")
    for rung in spec["load"]:
        _validate_rung(rung)
    _validate_slo(spec["slo"])
    return spec


def _validate_target(t: Any) -> None:
    if not isinstance(t, dict) or "url_env" not in t or "api_key_env" not in t:
        raise ValueError("spec.target needs url_env and api_key_env")
    if t.get("engine", "qdrant") != "qdrant":
        raise ValueError("boxfit ships the qdrant engine only (see targets.py to add one)")


def _validate_collection(c: Any) -> None:
    if not isinstance(c, dict):
        raise ValueError("spec.collection must be a mapping")
    for key in ("name", "dim", "datatype", "distance"):
        if key not in c:
            raise ValueError(f"spec.collection missing: {key}")
    if not isinstance(c.get("payload_indexes", []), list):
        raise ValueError("spec.collection.payload_indexes must be a list")


def _validate_filter(f: Any, coll: Any) -> None:
    """The filter model is the single source of truth: ingest, load, and the
    correctness gate all render from here. Each of tenant/corpus may be null
    (absent clause); both null is a legitimate unfiltered worst case.
    Present filter fields must be indexed — unindexed filtered search at
    scale is a footgun, so that's an error."""
    if not isinstance(f, dict):
        raise ValueError("spec.filter must be a mapping")
    for key in ("tenant", "corpus"):
        part = f.get(key)
        if part is None:
            continue
        if not isinstance(part, dict) or "field" not in part or "match" not in part:
            raise ValueError(f"spec.filter.{key} needs field and match")
        if part["match"] not in ("value", "any"):
            raise ValueError("filter match must be 'value' or 'any'")
    indexed = {idx["field"] for idx in coll.get("payload_indexes", [])}
    for key in ("tenant", "corpus"):
        part = f.get(key)
        if part is not None and part["field"] not in indexed:
            raise ValueError(f"spec.filter.{key}.field is not an indexed payload field")


def _validate_dataset(d: Any) -> None:
    if not isinstance(d, dict):
        raise ValueError("spec.dataset must be a mapping")
    for key in ("vectors", "tenants", "corpora_per_tenant", "seed"):
        if key not in d:
            raise ValueError(f"spec.dataset missing: {key}")
    if d["vectors"] % d["tenants"] != 0:
        raise ValueError("spec.dataset.vectors must divide evenly by tenants")


def _validate_rung(r: Any) -> None:
    if not isinstance(r, dict):
        raise ValueError("load rungs must be mappings")
    for key in ("rps", "duration", "ef", "top_k"):
        if key not in r:
            raise ValueError(f"load rung missing: {key}")


def _validate_slo(s: Any) -> None:
    if not isinstance(s, dict):
        raise ValueError("spec.slo must be a mapping")
    for key in ("p50_ms", "p99_ms", "error_rate", "achieved_pct"):
        if key not in s:
            raise ValueError(f"spec.slo missing: {key}")

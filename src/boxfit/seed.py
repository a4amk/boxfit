"""Seed engine schema from a workload spec (engine details in targets.py)."""

from __future__ import annotations

import os
from typing import Any

from boxfit.targets import make_target


def seed(spec: dict[str, Any], recreate: bool = True) -> None:
    base = os.environ[spec["target"]["url_env"]].rstrip("/")
    key = os.environ[spec["target"]["api_key_env"]]
    make_target(spec, base, key).seed(spec)
    _ = recreate  # recreate semantics live in the target (DELETE + create)

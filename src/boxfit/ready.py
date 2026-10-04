"""Index-readiness wait: don't measure an index that isn't built yet.

Bulk ingest returns long before HNSW indexing finishes. Measuring during that
window benchmarks full-scan fallback, not the index (we learned this the hard
way: 36s medians on an index that was 13% built). Polls until every point is
indexed, then returns.
"""

from __future__ import annotations

import time
from typing import Any

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

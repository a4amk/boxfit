"""boxfit: workload acceptance for self-hosted vector databases.

Spec in, PASS/FAIL verdict out. Answers "will this box survive my workload" —
it does not rank databases or test index science. Qdrant over plain REST.
"""

from boxfit.spec import load_spec

__all__ = ["load_spec"]

"""Spec validation tests (stdlib only)."""

import os
import unittest

from boxfit.spec import load_spec

EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "workloads", "saas-tenant-corpus.yaml")
EXAMPLE_NS = os.path.join(os.path.dirname(__file__), "..", "workloads", "single-namespace.yaml")


class TestSpec(unittest.TestCase):
    def test_example_loads(self) -> None:
        spec = load_spec(EXAMPLE)
        self.assertEqual(spec["name"], "saas-tenant-corpus-5M")
        self.assertEqual(len(spec["load"]), 3)

    def test_missing_key_rejected(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("name: broken\n")
            path = f.name
        try:
            with self.assertRaises(ValueError):
                load_spec(path)
        finally:
            os.unlink(path)

    def test_unindexed_filter_field_rejected(self) -> None:
        import copy
        import tempfile

        import yaml

        spec = load_spec(EXAMPLE)
        bad = copy.deepcopy(spec)
        bad["filter"]["corpus"]["field"] = "nope"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump(bad, f)
            path = f.name
        try:
            with self.assertRaises(ValueError):
                load_spec(path)
        finally:
            os.unlink(path)

    def test_nullable_corpus_clause(self) -> None:
        spec = load_spec(EXAMPLE_NS)
        self.assertIsNone(spec["filter"]["corpus"])
        self.assertEqual(spec["filter"]["tenant"]["field"], "namespace")

    def test_minimal_smoke_loads(self) -> None:
        path = os.path.join(os.path.dirname(__file__), "..", "workloads", "minimal.yaml")
        spec = load_spec(path)
        self.assertEqual(spec["collection"]["dim"], 128)

    def test_root_example_loads(self) -> None:
        path = os.path.join(os.path.dirname(__file__), "..", "workload.example.yaml")
        spec = load_spec(path)
        self.assertEqual(spec["name"], "minimal-smoke-10k")


if __name__ == "__main__":
    unittest.main()

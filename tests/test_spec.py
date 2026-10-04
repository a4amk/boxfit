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

    def test_discover_specs(self) -> None:
        import tempfile

        from boxfit.__main__ import discover_specs

        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            try:
                os.chdir(d)
                with self.assertRaises(FileNotFoundError):
                    discover_specs(None)
                os.mkdir(".workload")
                for name in ("b.yaml", "a.yaml"):
                    with open(os.path.join(".workload", name), "w") as f:
                        f.write("name: x\n")
                self.assertEqual(
                    discover_specs(None),
                    [os.path.join(".workload", "a.yaml"), os.path.join(".workload", "b.yaml")],
                )
                with open("workload.yaml", "w") as f:
                    f.write("name: x\n")
                self.assertEqual(discover_specs(None), ["workload.yaml"])
                self.assertEqual(discover_specs("custom.yaml"), ["custom.yaml"])
            finally:
                os.chdir(cwd)

    def test_combined_verdict(self) -> None:
        from boxfit.report import write_combined

        import tempfile

        ok_results = [{"offered": 100, "achieved": 6000, "achieved_pct": 100.0,
                       "p50_ms": 2.0, "p95_ms": 3.0, "p99_ms": 5.0, "error_rate": 0.0}]
        bad_results = [dict(ok_results[0], p99_ms=5000.0)]
        slo = {"p50_ms": 10, "p99_ms": 100, "error_rate": 0.02, "achieved_pct": 99}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.md")
            self.assertTrue(write_combined([("a", True, ok_results)], path))
            self.assertFalse(
                write_combined([("a", True, ok_results), ("b", False, bad_results)], path)
            )
            text = open(path).read()
            self.assertIn("## b", text)

    def test_await_indexed_stub(self) -> None:
        from boxfit.ready import await_indexed

        class Stub:
            name = "stub"

            def __init__(self) -> None:
                self.calls = 0

            def seed(self, spec): ...
            def upsert(self, spec, points): ...
            def search(self, spec, body): ...
            def points_count(self, spec):
                return 10

            def indexed_count(self, spec):
                self.calls += 1
                return 10 if self.calls > 1 else 4

        await_indexed(Stub(), {}, timeout_s=60)  # type: ignore[arg-type]
        with self.assertRaises(TimeoutError):
            await_indexed(Stub(), {}, timeout_s=0)  # type: ignore[arg-type]

    def test_preflight_missing_env(self) -> None:
        from boxfit.__main__ import preflight

        with self.assertRaises(ValueError):
            preflight(
                {"target": {"url_env": "BOXFIT_NOPE_URL", "api_key_env": "BOXFIT_NOPE_KEY"}},
                {"load"},
                "/tmp",
            )


    def test_warm_stub(self) -> None:
        import tempfile

        import numpy as np

        from boxfit.ready import warm

        spec = load_spec(EXAMPLE_NS)  # tenant-only filter shape

        class Stub:
            name = "stub"
            seen: list

            def __init__(self) -> None:
                self.seen = []

            def seed(self, spec): ...
            def upsert(self, spec, points): ...
            def search(self, spec, body):
                self.seen.append(body)
                return []

            def points_count(self, spec):
                return 0

            def indexed_count(self, spec):
                return 0

        with tempfile.TemporaryDirectory() as d:
            np.save(
                f"{d}/vecs.npy",
                np.zeros((20, int(spec["collection"]["dim"])), dtype=np.uint8),
            )
            # minimal spec expects 200000 vectors; shrink via a copy
            import copy

            small = copy.deepcopy(spec)
            small["dataset"]["vectors"] = 20
            small["dataset"]["tenants"] = 2
            stub = Stub()
            warm(stub, small, d, n=3)
            self.assertEqual(len(stub.seen), 3)
            for body in stub.seen:
                keys = [c["key"] for c in body["filter"]["must"]]
                self.assertEqual(keys, ["namespace"])  # tenant-only shape


if __name__ == "__main__":
    unittest.main()

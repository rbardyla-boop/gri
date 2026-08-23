from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.forge.forge import Case, Chain, Forge, Grinder, Mutation, Registry, SearchConfig, Tool


class ForgeTests(unittest.TestCase):
    def registry(self) -> Registry:
        reg = Registry()
        reg.register(Tool("inc", "int", "int", 1, lambda x: x + 1))
        reg.register(Tool("double", "int", "int", 1, lambda x: x * 2))
        reg.register(Tool("square", "int", "int", 2, lambda x: x * x))
        reg.register(Tool("to_text", "int", "text", 1, lambda x: str(x)))
        reg.register(Tool("bang", "text", "text", 1, lambda x: x + "!"))
        return reg

    def test_toolsmith_only_builds_type_compatible_bounded_chains(self):
        forge = Forge(self.registry())
        config = SearchConfig("int", "text", max_depth=3, max_cost=3)
        chains = forge.toolsmith.enumerate(config)
        self.assertTrue(chains)
        for chain in chains:
            self.assertLessEqual(len(chain.tools), 3)
            self.assertLessEqual(chain.cost, 3)
            self.assertEqual(chain.input_kind, "int")
            self.assertEqual(chain.output_kind, "text")
            forge.run_chain(chain, 2)

    def test_search_uses_dev_only_and_prefers_simple_equal_score_chain(self):
        reg = Registry()
        reg.register(Tool("plus_two", "int", "int", 1, lambda x: x + 2))
        reg.register(Tool("plus_one", "int", "int", 1, lambda x: x + 1))
        forge = Forge(reg)
        dev = [Case("d1", 1, 3), Case("d2", 2, 4)]
        ranked = forge.search(SearchConfig("int", "int", max_depth=2, max_cost=2), dev)
        self.assertEqual(ranked[0].score, 1.0)
        self.assertEqual(ranked[0].chain.tools, ("plus_two",))

    def test_holdout_is_one_shot_and_receipt_is_content_bound(self):
        reg = Registry()
        reg.register(Tool("plus_two", "int", "int", 1, lambda x: x + 2))
        forge = Forge(reg)
        champion = Chain(("plus_two",), "int", "int", 1)
        holdout = [Case("h1", 10, 12), Case("h2", 20, 22)]
        with tempfile.TemporaryDirectory() as td:
            receipt = forge.evaluate_holdout_once(champion, holdout, Path(td) / "receipt.json")
            self.assertEqual(receipt.score, 1.0)
            self.assertEqual(len(receipt.receipt_sha256), 64)
            with self.assertRaisesRegex(RuntimeError, "FORGE_HOLDOUT_ALREADY_CONSUMED"):
                forge.evaluate_holdout_once(champion, holdout)

    def test_grinder_finds_counterexample_without_modifying_chain(self):
        reg = Registry()
        reg.register(Tool("absolute", "int", "int", 1, abs))
        forge = Forge(reg)
        chain = Chain(("absolute",), "int", "int", 1)
        base = [Case("base", 2, 2)]

        def sign_sensitive(case: Case):
            yield Case(case.case_id + "-neg", -case.input, -case.expected)

        grinder = Grinder(forge, [Mutation("sign_flip", sign_sensitive)])
        failures = grinder.grind(chain, base)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].mutation, "sign_flip")
        self.assertEqual(chain.tools, ("absolute",))

    def test_chain_ids_are_deterministic(self):
        a = Chain(("inc", "double"), "int", "int", 2)
        b = Chain(("inc", "double"), "int", "int", 2)
        self.assertEqual(a.chain_id, b.chain_id)


if __name__ == "__main__":
    unittest.main()

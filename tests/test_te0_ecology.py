from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.forge.ecology import (
    Ablator,
    Composer,
    DeclarativeToolFactory,
    FailureClass,
    Judge,
    JudgeVerdict,
    Ledger,
    NullSmith,
    ToolBlueprint,
    ToolSmith,
    classify_failure,
    promote_skill,
)
from experiments.forge.forge import Case, Chain, Forge, Registry, SearchConfig, Tool


class TE0EcologyTests(unittest.TestCase):
    def test_failure_classifier_separates_resource_from_science(self):
        diagnosis = classify_failure({"oom": True, "model_wrong_after_controls": True})
        self.assertEqual(diagnosis.failure_class, FailureClass.RESOURCE)
        self.assertIn("do not interpret as science", diagnosis.recommended_action)

    def test_tool_factory_rejects_arbitrary_operation(self):
        factory = DeclarativeToolFactory()
        bp = ToolBlueprint("bad", "exec_python", "text", "text", 1, {}, FailureClass.TOOL)
        with self.assertRaisesRegex(ValueError, "FORGE_TOOL_OP_FORBIDDEN"):
            factory.compile(bp)

    def test_toolsmith_uses_build_only_and_proposes_transparent_tools(self):
        build = [Case("b1", "PASS", "PASS"), Case("b2", "FAIL", "FAIL")]
        smith = ToolSmith()
        diagnosis = classify_failure({"label_collision": True})
        proposals = smith.propose(diagnosis, build, "text", "label")
        names = {p.name for p in proposals}
        self.assertIn("ts_strip", names)
        self.assertIn("ts_lower", names)
        self.assertIn("ts_build_lookup", names)

    def test_composer_penalizes_complex_equal_score_recipe(self):
        reg = Registry()
        reg.register(Tool("plus_two", "int", "int", 1, lambda x: x + 2))
        reg.register(Tool("plus_one", "int", "int", 1, lambda x: x + 1))
        reg.register(Tool("identity", "int", "int", 1, lambda x: x))
        forge = Forge(reg)
        dev = [Case("d1", 1, 3), Case("d2", 2, 4), Case("d3", 3, 5)]
        ranked = Composer(forge).search(dev, SearchConfig("int", "int", max_depth=3, max_cost=3))
        self.assertEqual(ranked[0].chain.tools, ("plus_two",))
        self.assertEqual(ranked[0].dev_score, 1.0)

    def test_nullsmith_makes_simple_baselines_explicit(self):
        cases = [Case("a", 1, 0), Case("b", 2, 0), Case("c", 3, 1)]
        nulls = NullSmith.constant_null(cases)
        self.assertEqual(nulls[0].score, 2 / 3)
        self.assertEqual(NullSmith.identity_null(cases).score, 0.0)

    def test_ablator_removes_credit_when_component_is_unnecessary(self):
        reg = Registry()
        reg.register(Tool("plus_two", "int", "int", 1, lambda x: x + 2))
        reg.register(Tool("identity", "int", "int", 1, lambda x: x))
        forge = Forge(reg)
        cases = [Case("d1", 1, 3), Case("d2", 2, 4)]
        chain = Chain(("identity", "plus_two"), "int", "int", 2)
        results = Ablator(forge).single_tool_ablations(chain, cases)
        by_tool = {r.removed_tool: r for r in results}
        self.assertTrue(by_tool["identity"].valid)
        self.assertEqual(by_tool["identity"].delta_from_full, 0.0)
        self.assertTrue(by_tool["plus_two"].valid)
        self.assertGreater(by_tool["plus_two"].delta_from_full, 0.0)

    def test_judge_is_one_shot_and_only_pass_can_promote(self):
        reg = Registry()
        reg.register(Tool("plus_two", "int", "int", 1, lambda x: x + 2))
        forge = Forge(reg)
        chain = Chain(("plus_two",), "int", "int", 1)
        vault = [Case("v1", 10, 12), Case("v2", 20, 22), Case("v3", 30, 32)]
        receipt = Judge(forge).evaluate_once(chain, vault, threshold=1.0, min_margin_over_null=0.5)
        self.assertEqual(receipt.verdict, JudgeVerdict.PASS)
        packet = promote_skill(chain, receipt)
        self.assertTrue(packet.authority)
        self.assertEqual(packet.chain_id, chain.chain_id)
        with self.assertRaisesRegex(RuntimeError, "FORGE_HOLDOUT_ALREADY_CONSUMED"):
            Judge(forge).evaluate_once(chain, vault, threshold=1.0)

    def test_failed_judge_cannot_promote(self):
        reg = Registry()
        reg.register(Tool("identity", "int", "int", 1, lambda x: x))
        forge = Forge(reg)
        chain = Chain(("identity",), "int", "int", 1)
        vault = [Case("v1", 1, 2), Case("v2", 2, 3)]
        receipt = Judge(forge).evaluate_once(chain, vault, threshold=0.9)
        self.assertEqual(receipt.verdict, JudgeVerdict.FAIL)
        with self.assertRaisesRegex(ValueError, "FORGE_PROMOTION_REQUIRES_JUDGE_PASS"):
            promote_skill(chain, receipt)

    def test_ledger_is_append_only_and_hash_chained(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ledger.jsonl"
            ledger = Ledger(path)
            r1 = ledger.append({"experiment": "TE0-0001", "authority": False})
            r2 = ledger.append({"experiment": "TE0-0002", "authority": False})
            self.assertEqual(r2["prev_sha256"], r1["record_sha256"])
            self.assertTrue(ledger.verify())
            rows = [json.loads(x) for x in path.read_text().splitlines()]
            rows[0]["authority"] = True
            path.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
            self.assertFalse(ledger.verify())


if __name__ == "__main__":
    unittest.main()

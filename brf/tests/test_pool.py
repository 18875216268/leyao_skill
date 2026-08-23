"""公共知识池客户端单测：query/submit/inject/record_adopt 协议与容错。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.sources.pool_client as pc
from scripts.sources.pool_client import (POOL_TOKEN, query,
                                         record_adopt, submit)


class TestPoolClient(unittest.TestCase):
    def test_query_builds_params(self):
        with mock.patch.object(pc, "_request", return_value={"ok": True, "items": []}) as m:
            out = query(q="缺货率", category="caliber", trust="authority", limit=3)
        self.assertTrue(out["ok"])
        args, kwargs = m.call_args
        self.assertEqual(args[0], "GET")
        self.assertIn("q=%E7%BC%BA%E8%B4%A7%E7%8E%87", args[1])
        self.assertIn("category=caliber", args[1])
        self.assertIn("trust=authority", args[1])
        self.assertIn("limit=3", args[1])
        self.assertIsNone(kwargs.get("token"))

    def test_submit_includes_kind_and_token(self):
        with mock.patch.object(pc, "_request", return_value={"ok": True, "id": "p-1"}) as m:
            out = submit("成本优势率怎么算", "低于合理P4*0.99购进的订单金额/总订单金额",
                         category="caliber", distill_type="lesson",
                         trust="authority", quality_score=0.9, kind="fact")
        self.assertTrue(out["ok"])
        args, kwargs = m.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "")
        self.assertEqual(kwargs["token"], POOL_TOKEN)
        body = args[2]
        self.assertEqual(body["kind"], "fact")
        self.assertEqual(body["title"], "成本优势率怎么算")
        self.assertEqual(body["quality_score"], 0.9)

    def test_submit_procedure_kind(self):
        with mock.patch.object(pc, "_request", return_value={"ok": True}) as m:
            submit("怎么做周报", "1. 取数 → 2. 清洗 → 3. 填充", category="method",
                   distill_type="workflow", kind="procedure")
        body = m.call_args.args[2]
        self.assertEqual(body["kind"], "procedure")

    def test_record_adopt_token_and_timeout(self):
        with mock.patch.object(pc, "_request", return_value={"ok": True, "hit_count": 7, "adopt_count": 2}) as m:
            out = record_adopt("p-123")
        self.assertTrue(out["ok"])
        args, kwargs = m.call_args
        self.assertEqual(args[1], "/adopt")
        self.assertEqual(args[2], {"id": "p-123"})
        self.assertEqual(kwargs["token"], POOL_TOKEN)
        self.assertEqual(kwargs.get("timeout"), 5)
        self.assertEqual(out["adopt_count"], 2)

    def test_record_missing_id(self):
        self.assertEqual(record_adopt(None)["error"], "MISSING_ID")

    def test_network_failure_silent(self):
        """网络失败返回 ok:false 不抛异常（容错静默，不阻塞主流程）。"""
        with mock.patch.object(pc, "_request", return_value={"ok": False, "error": "NETWORK"}):
            self.assertFalse(record_adopt("p-123")["ok"])


class TestPoolLayerHitSignal(unittest.TestCase):
    """resolve.pool_layer：按 tier 分两路查询（inject 权威 + session 参考），关键词清洗后查询。"""

    def test_pool_layer_two_tier_queries_authority_first(self):
        import scripts.resolve as resolve_mod
        def fake_query(q=None, limit=None, tier=None):
            if tier == "inject":
                return {"items": [
                    {"id": "p-i1", "title": "成本优势率", "content": "低于合理P4*0.99购进订单金额/总订单金额",
                     "trust": "authority", "hit_count": 3, "adopt_count": 1}]}
            return {"items": [
                {"id": "p-s1", "title": "缺货率", "content": "缺货品种数/考核品种数",
                 "trust": "reference", "hit_count": 5, "adopt_count": 2}]}
        with mock.patch.object(resolve_mod, "pool_layer", wraps=resolve_mod.pool_layer), \
             mock.patch("scripts.sources.pool_client.query", side_effect=fake_query) as m_q:
            hits = resolve_mod.pool_layer("caliber", "成本优势率怎么算")
        self.assertEqual(len(hits), 2)                     # inject 1 条 + session 1 条
        sources = [h["source"] for h in hits]
        self.assertIn("pool-inject", sources)
        self.assertIn("pool-session", sources)
        # authority 优先排序
        trusts = [h["trust"] for h in hits]
        self.assertEqual(trusts, sorted(trusts, key=lambda t: {"authority": 0, "reference": 1, "candidate": 2}.get(t, 3)))
        self.assertEqual(m_q.call_count, 2)                # 两路查询
        # 关键词清洗：原问句剥离意图词后作为 q（"成本优势率怎么算" → "成本优势率"）
        for call in m_q.call_args_list:
            self.assertEqual(call.kwargs["q"], "成本优势率")


if __name__ == "__main__":
    unittest.main()

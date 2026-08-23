"""pool_adapter 单测：tier/kind/category 映射 + 关键词提取 + 口径只查注入库。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.adapters.pool_adapter import PoolAdapter, extract_keyword


class TestPoolAdapter(unittest.TestCase):
    def setUp(self):
        self.ad = PoolAdapter()
        self.asset = {"asset_id": "ops-metrics", "adapter": "pool", "mode": "pool",
                      "source": "https://lyzsk.cfdaili.top/api/pool"}

    def test_extract_keyword_strips_intent_words(self):
        self.assertEqual(extract_keyword("成本优势率怎么算"), "成本优势率")
        self.assertEqual(extract_keyword("缺货率是什么"), "缺货率")
        self.assertEqual(extract_keyword("帝豪公司是哪里的"), "帝豪公司")

    def test_match_pool_adapter(self):
        self.assertTrue(self.ad.match({"adapter": "pool"}))
        self.assertTrue(self.ad.match({"mode": "pool"}))
        self.assertFalse(self.ad.match({"adapter": "api"}))

    def test_caliber_queries_inject_tier_only(self):
        """口径诉求 → tier=inject（authority 权威），不查 session。"""
        with mock.patch.object(self.ad, "query", wraps=self.ad.query), \
             mock.patch("scripts.adapters.pool_adapter._fetch",
                        return_value={"ok": True, "items": [
                            {"id": "p1", "title": "成本优势率", "content": "低于合理P4*0.99购进订单金额/总订单金额",
                             "trust": "authority", "tier": "inject"}]}) as m_fetch:
            out = self.ad.query(self.asset, "caliber", "成本优势率怎么算")
        self.assertTrue(out["ok"])
        url = m_fetch.call_args.args[0]
        self.assertIn("tier=inject", url)      # 口径只查注入库
        self.assertIn("category=caliber", url)
        self.assertIn("kind=fact", url)
        self.assertIn("q=", url)               # 关键词已提取
        self.assertNotIn("%E6%80%8E%E4%B9%88%E7%AE%97", url)  # 不含"怎么算"

    def test_process_queries_session_procedure(self):
        """流程诉求 → tier=session + kind=procedure（程序环）。"""
        with mock.patch("scripts.adapters.pool_adapter._fetch",
                        return_value={"ok": True, "items": [
                            {"id": "p2", "title": "怎么做周报", "content": "1.取数→2.清洗→3.填充",
                             "trust": "reference", "tier": "session"}]}) as m_fetch:
            out = self.ad.query({"adapter": "pool"}, "process", "怎么做周报")
        self.assertTrue(out["ok"])
        url = m_fetch.call_args.args[0]
        self.assertIn("tier=session", url)
        self.assertIn("kind=procedure", url)

    def test_asset_pool_tier_overrides_default(self):
        """资产声明的 pool_tier 优先于 need_type 默认映射（如 ops-companies 权威 → inject）。"""
        asset = {"adapter": "pool", "pool_tier": "inject"}
        with mock.patch("scripts.adapters.pool_adapter._fetch",
                        return_value={"ok": True, "items": [
                            {"id": "p3", "title": "子公司：帝豪", "content": "帝豪公司",
                             "trust": "authority", "tier": "inject"}]}) as m_fetch:
            out = self.ad.query(asset, "term", "帝豪公司是哪里的")
        self.assertTrue(out["ok"])
        url = m_fetch.call_args.args[0]
        self.assertIn("tier=inject", url)      # 资产声明覆盖（term 默认 session → inject）
        self.assertIn("category=term", url)

    def test_no_match_returns_false(self):
        with mock.patch("scripts.adapters.pool_adapter._fetch", return_value={"ok": True, "items": []}):
            out = self.ad.query(self.asset, "caliber", "zzz不存在的词")
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "no_match")

    def test_network_failure_silent(self):
        with mock.patch("scripts.adapters.pool_adapter._fetch", return_value=None):
            out = self.ad.query(self.asset, "caliber", "成本优势率")
        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main()

"""ask() 端到端单测：注册表 → 路由 → 适配器 → 结构化响应。

pool 资产走 mock（离线确定）；云智库测试为真实网络（不可达时跳过）。
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.registry import load_registry
from scripts.ask import ask

ROOT = Path(__file__).resolve().parent.parent


class TestAsk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = load_registry(ROOT / "registry.json")
        cls.tmp = Path(tempfile.mkdtemp())

    def setUp(self):
        """统一 mock 外部依赖：避免真实网络（pool 资产在用例内 mock 分流）。"""
        pass

    def tearDown(self):
        mock.patch.stopall()

    def test_ask_term_end_to_end(self):
        # pool_layer 统一查池 → 命中后知识域跳过 pool 资产（不重复云端 GET）
        import scripts.resolve as resolve_mod
        from scripts.adapters import pool_adapter
        fake_hits = [{"ok": True, "need_type": "term", "layer": "K2.5", "source": "pool-inject",
                      "answer": "[公共知识池·authority] 缺货率：缺货品种数/考核品种数",
                      "trust": "authority", "confidence": 0.9, "pool_id": "p-t1", "tier": "inject"}]
        with mock.patch.object(resolve_mod, "pool_layer", return_value=fake_hits) as m_pool, \
             mock.patch.object(pool_adapter, "_fetch") as m_fetch:
            out = ask(self.reg, "term", "缺货率 的定义")
        self.assertTrue(out["ok"], msg=str(out))
        self.assertEqual(out["possibilities"][0]["source"], "pool-inject")
        self.assertIn("answer", out["possibilities"][0])
        m_pool.assert_called_once()
        m_fetch.assert_not_called()                  # 池命中后知识域跳过 pool 资产

    def test_ask_caliber_end_to_end(self):
        # 计算门口径仍 authority（注入库权威，pool_layer 统一查询）
        import scripts.resolve as resolve_mod
        fake_hits = [{"ok": True, "need_type": "caliber", "layer": "K2.5", "source": "pool-inject",
                      "answer": "[公共知识池·authority] 成本优势率：低于合理P4*0.99购进的订单金额/总订单金额",
                      "trust": "authority", "confidence": 0.9, "pool_id": "p-m1", "tier": "inject"}]
        with mock.patch.object(resolve_mod, "pool_layer", return_value=fake_hits):
            out = ask(self.reg, "caliber", "成本优势率怎么算")
        self.assertTrue(out["ok"], msg=str(out))
        self.assertEqual(out["possibilities"][0]["trust"], "authority")

    def test_ask_tool_returns_hub(self):
        import urllib.error
        import urllib.request
        from pathlib import Path
        token_file = ROOT / "scripts" / "sources" / "leyou" / "leyou_token.json"
        if not token_file.exists():
            self.skipTest("云智库凭证未配置（leyou_token.json 缺失），跳过（环境敏感）")
        try:
            urllib.request.urlopen("https://api-get.helplook.net", timeout=8)
        except (urllib.error.URLError, TimeoutError, OSError):
            self.skipTest("云智库网络不可用，跳过（真实网络测试）")
        out = ask(self.reg, "tool", "查制度")
        self.assertTrue(out["ok"], msg=str(out))
        # 工具域命中（leyou-search 在候选集中；池权威数据可能排序更前，属设计使然）
        self.assertIn("leyou-search", [p.get("source") for p in out["possibilities"]])

    def test_ask_unknown_need_type(self):
        out = ask(self.reg, "unknown", "x")
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "unknown_need_type")

    def test_ask_template_returns_listing(self):
        # 自构造临时模板目录（不依赖挂载环境，离线确定）
        tdir = Path(tempfile.mkdtemp())
        (tdir / "task.template.json").write_text("{}", encoding="utf-8")
        asset = {"asset_id": "ops-templates", "category": "template", "adapter": "template",
                 "source": str(tdir), "trust": "reference"}
        from scripts.adapters import get_adapter
        out = get_adapter(asset).query(asset, "template", "zzz不存在模板")
        self.assertTrue(out["ok"], msg=str(out))  # 模板适配器已实现：返回模板清单
        self.assertIn("可用模板", out["answer"])


if __name__ == "__main__":
    unittest.main()

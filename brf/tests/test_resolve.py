"""resolve 多可能性内核单测（P1）+ K1 层接入（P2）。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.registry import load_registry
import scripts.resolve as resolve_mod
from scripts.resolve import resolve


def _mini_registry(tmpdir: Path):
    """夹具资产：pool 适配器（注入 authority + 会话 reference），_fetch 在 _ctx 中 mock（离线确定）。"""
    d1 = {"asset_id": "t-authority", "category": "knowledge", "sub_category": "term",
          "adapter": "pool", "pool_tier": "inject", "trust": "authority",
          "source": "https://test/api/pool", "covers_need": ["term"]}
    d2 = {"asset_id": "t-reference", "category": "knowledge", "sub_category": "entity",
          "adapter": "pool", "pool_tier": "session", "trust": "reference",
          "source": "https://test/api/pool", "covers_need": ["term"]}
    return {"registry_version": "test", "assets": [d1, d2]}


class TestResolve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        reg = _mini_registry(cls.tmp)
        p = cls.tmp / "registry.json"
        p.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        cls.reg = load_registry(str(p))

    def setUp(self):
        """统一 mock 外部依赖：避免真实网络干扰 resolve 逻辑测试。"""
        pass

    def tearDown(self):
        mock.patch.stopall()

    def _ctx(self):
        """统一 mock 外部依赖：K1 记忆、公共池层与池适配器网络（避免真实网络/记忆干扰 resolve 逻辑测试）。

        pool_adapter._fetch 按查询参数分流：tier=inject+q 含缺货率 → 权威条目；
        tier=session+q 含帝豪 → 参考条目；其余空（模拟云端 LIKE 相关性）。
        """
        import urllib.parse as up

        def fake_fetch(url):
            pr = up.parse_qs(up.urlparse(url).query)
            q = pr.get("q", [""])[0]
            tier = pr.get("tier", [""])[0]
            if tier == "inject" and "缺货率" in q:
                return {"ok": True, "items": [{"id": "p1", "title": "缺货率",
                                               "content": "缺货品种数/考核品种数",
                                               "trust": "authority", "tier": "inject"}]}
            if tier == "session" and "帝豪" in q:
                return {"ok": True, "items": [{"id": "p2", "title": "帝豪公司",
                                               "content": "广东帝豪药业有限公司",
                                               "trust": "reference", "tier": "session"}]}
            return {"ok": True, "items": []}

        return mock.patch.object(resolve_mod, "k1_layer", return_value=[]), \
               mock.patch.object(resolve_mod, "pool_layer", return_value=[]), \
               mock.patch("scripts.adapters.pool_adapter._fetch", side_effect=fake_fetch)

    def test_collect_multiple_possibilities(self):
        """多可能性：知识域多资产命中 → 收集多个候选（注入权威 + 会话参考）。"""
        with self._ctx()[0], self._ctx()[1], self._ctx()[2]:
            out = resolve(self.reg, "缺货率 帝豪", need_type="term")
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["possibilities"]), 2)
        sources = [p["source"] for p in out["possibilities"]]
        self.assertIn("pool-inject", sources)                # 权威注入库命中
        self.assertIn("pool-session", sources)               # 参考会话库命中
        self.assertEqual(out["possibilities"][0]["trust"], "authority")  # best 排序 authority 优先
        self.assertEqual(out["best"]["source"], "pool-inject")

    def test_single_possibility(self):
        with self._ctx()[0], self._ctx()[1], self._ctx()[2]:
            out = resolve(self.reg, "缺货率", need_type="term")
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["possibilities"]), 1)
        self.assertEqual(out["possibilities"][0]["source"], "pool-inject")

    def test_k1_layer_in_path_and_collected(self):
        """K1 记忆/缓存命中 → path K1 ok=true 且候选进入 possibilities。"""
        k1_hit = [{"ok": True, "need_type": "term", "layer": "K1", "source": "cache",
                   "answer": "缺货率：缺货品种数/考核品种数", "trust": "authority", "confidence": 0.98}]
        with mock.patch.object(resolve_mod, "k1_layer", return_value=k1_hit), \
             mock.patch.object(resolve_mod, "pool_layer", return_value=[]):
            out = resolve(self.reg, "缺货率", need_type="term")
        self.assertTrue(out["ok"])
        self.assertEqual(out["path"][0]["layer"], "K1")
        self.assertTrue(out["path"][0]["ok"])
        self.assertEqual(out["possibilities"][0]["layer"], "K1")
        self.assertEqual(out["best"]["source"], "cache")

    def test_unresolved_without_network(self):
        with mock.patch.object(resolve_mod, "k1_layer", return_value=[]), \
             mock.patch.object(resolve_mod, "pool_layer", return_value=[]):
            out = resolve(self.reg, "zzzqqq不存在词", need_type="term")
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "unresolved")
        self.assertEqual(out["possibilities"], [])
        self.assertEqual(len(out["path"]), 4)  # 阶段1 K1 / 阶段2 pool / knowledge / tool（pool 为固定阶段条目）

    def test_network_required_with_allow(self):
        with mock.patch.object(resolve_mod, "k1_layer", return_value=[]), \
             mock.patch.object(resolve_mod, "pool_layer", return_value=[]):
            out = resolve(self.reg, "zzzqqq不存在词", need_type="term", allow_network=True)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "network_required")
        self.assertEqual(out["path"][-1]["layer"], "network")
        self.assertEqual(out["guidance_doc"], "references/network-guidance.md")
        self.assertIn("自助规划", out["hint"])

    # ── 三阶段调度新测试 ──

    def test_cache_hit_early_stop(self):
        """阶段1：cache 命中 → 早停（不触发阶段 2，省时省成本）。"""
        cache_hit = [{"ok": True, "need_type": "term", "layer": "K1", "source": "cache",
                      "answer": "缺货率：缺货品种数/考核品种数", "trust": "authority",
                      "confidence": 0.98}]
        with mock.patch.object(resolve_mod, "k1_layer", return_value=cache_hit), \
             mock.patch.object(resolve_mod, "knowledge_layer", return_value=[]) as m_know, \
             mock.patch.object(resolve_mod, "pool_layer", return_value=[]) as m_pool:
            out = resolve(self.reg, "缺货率是什么", need_type="term")
        self.assertTrue(out["ok"])
        self.assertTrue(out.get("early_stop"))
        self.assertEqual(out["best"]["source"], "cache")
        layers = [p["layer"] for p in out["path"]]
        self.assertIn("early_stop", layers)
        m_know.assert_not_called()   # 早停：阶段 2 未执行
        m_pool.assert_not_called()

    def test_expand_skips_early_stop(self):
        """--expand：cache 命中仍全收集（不早停），阶段 2 照常执行。"""
        cache_hit = [{"ok": True, "need_type": "term", "layer": "K1", "source": "cache",
                      "answer": "缺货率：缺货品种数/考核品种数", "trust": "authority",
                      "confidence": 0.98}]
        with mock.patch.object(resolve_mod, "k1_layer", return_value=cache_hit), \
             mock.patch.object(resolve_mod, "pool_layer", return_value=[]) as m_pool:
            out = resolve(self.reg, "缺货率是什么", need_type="term", expand=True)
        self.assertTrue(out["ok"])
        self.assertNotIn("early_stop", [p["layer"] for p in out["path"]])
        m_pool.assert_called_once()   # 阶段 2 已执行

    def test_stage2_parallel_fault_tolerance(self):
        """阶段2 并行：单路抛异常不影响其它路（公域挂 → 知识/工具仍出结果）。"""
        khit = [{"ok": True, "need_type": "term", "layer": "knowledge", "source": "t-authority",
                 "answer": "缺货率：缺货品种数/考核品种数", "trust": "authority", "confidence": 0.9}]
        def boom():
            raise ConnectionError("pool down")
        with mock.patch.object(resolve_mod, "k1_layer", return_value=[]), \
             mock.patch.object(resolve_mod, "pool_layer", side_effect=boom), \
             mock.patch.object(resolve_mod, "knowledge_layer", return_value=khit):
            out = resolve(self.reg, "缺货率是什么", need_type="term")
        self.assertTrue(out["ok"])                       # 公域异常未阻塞
        self.assertEqual(out["best"]["source"], "t-authority")
        pool_entry = next(p for p in out["path"] if p["layer"] == "pool")
        self.assertFalse(pool_entry["ok"])               # pool 降级记录

    def test_prefetch_network_attached(self):
        """--prefetch-network：弱命中时附带网络引导（不阻塞主返回）。"""
        khit = [{"ok": True, "need_type": "term", "layer": "knowledge", "source": "t-authority",
                 "answer": "缺货率：缺货品种数/考核品种数", "trust": "authority", "confidence": 0.9}]
        with mock.patch.object(resolve_mod, "k1_layer", return_value=[]), \
             mock.patch.object(resolve_mod, "pool_layer", return_value=[]), \
             mock.patch.object(resolve_mod, "knowledge_layer", return_value=khit):
            out = resolve(self.reg, "缺货率是什么", need_type="term", prefetch_network=True)
        self.assertTrue(out["ok"])
        self.assertEqual(out["best"]["source"], "t-authority")
        self.assertIn("guidance_doc", out)
        self.assertIn("自助规划", out.get("hint", ""))

    # ── 隐式不满信号（用户反馈交互）测试 ──

    def test_dissatisfied_skips_early_stop(self):
        """不满信号：cache 命中但近期同指纹重复提问 → 跳过早停重新解决。"""
        cache_hit = [{"ok": True, "need_type": "term", "layer": "K1", "source": "cache",
                      "answer": "缺货率：旧答案", "trust": "authority", "confidence": 0.98}]
        with mock.patch.object(resolve_mod, "k1_layer", return_value=cache_hit), \
             mock.patch.object(resolve_mod, "_dissatisfied", return_value=True), \
             mock.patch.object(resolve_mod, "pool_layer", return_value=[]):
            out = resolve(self.reg, "缺货率是什么", need_type="term")
        self.assertTrue(out["ok"])
        self.assertNotIn("early_stop", [p["layer"] for p in out["path"]])   # 未早停
        self.assertTrue(any("dissatisfied" in p.get("note", "") for p in out["path"]))

    def test_no_dissatisfied_early_stops(self):
        """无不满信号：cache 命中 → 正常早停。"""
        cache_hit = [{"ok": True, "need_type": "term", "layer": "K1", "source": "cache",
                      "answer": "缺货率：缺货品种数/考核品种数", "trust": "authority", "confidence": 0.98}]
        with mock.patch.object(resolve_mod, "k1_layer", return_value=cache_hit), \
             mock.patch.object(resolve_mod, "_dissatisfied", return_value=False):
            out = resolve(self.reg, "缺货率是什么", need_type="term")
        self.assertTrue(out["ok"])
        self.assertTrue(out.get("early_stop"))

    def test_dissatisfied_offline_returns_false(self):
        """无 work-dir（离线/单测）：不满判定静默 False，不阻塞。"""
        self.assertFalse(resolve_mod._dissatisfied("缺货率是什么", "term", None))

    def test_dissatisfied_counts_ask_log(self):
        """不满判定：ask-log 同指纹 ≥2 条 → True；1 条/无 → False。"""
        import datetime as dt
        wd = Path(tempfile.mkdtemp())
        brf_dir = wd / "brf"
        brf_dir.mkdir(parents=True, exist_ok=True)
        now = dt.datetime.now().astimezone().isoformat()
        log = brf_dir / "ask-log.jsonl"
        log.write_text(
            json.dumps({"ts": now, "fingerprint": "缺货率", "problem": "缺货率是什么"}, ensure_ascii=False) + "\n" +
            json.dumps({"ts": now, "fingerprint": "缺货率", "problem": "缺货率定义"}, ensure_ascii=False) + "\n" +
            json.dumps({"ts": now, "fingerprint": "促销毛利", "problem": "促销毛利怎么查"}, ensure_ascii=False) + "\n",
            encoding="utf-8")
        self.assertTrue(resolve_mod._dissatisfied("缺货率是什么", "term", str(wd)))       # 同指纹 2 条
        self.assertFalse(resolve_mod._dissatisfied("促销毛利怎么查", "data", str(wd)))    # 1 条
        self.assertFalse(resolve_mod._dissatisfied("zzz不存在的词", "term", str(wd)))     # 无记录
        # 历史过期（>7 天）不计
        old = (dt.datetime.now().astimezone() - dt.timedelta(days=30)).isoformat()
        (brf_dir / "ask-log.jsonl").write_text(
            json.dumps({"ts": old, "fingerprint": "旧问题", "problem": "旧问题"}, ensure_ascii=False) + "\n" +
            json.dumps({"ts": old, "fingerprint": "旧问题", "problem": "旧问题"}, ensure_ascii=False) + "\n",
            encoding="utf-8")
        self.assertFalse(resolve_mod._dissatisfied("旧问题", "term", str(wd)))


if __name__ == "__main__":
    unittest.main()

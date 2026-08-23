import json
import tempfile
import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import index


def _seed(root: Path) -> None:
    """构造 semantic/core/cache 源数据。"""
    sem_dir = root / "memory" / "semantic"
    sem_dir.mkdir(parents=True)
    (sem_dir / "knowledge-hub.json").write_text(json.dumps({
        "entries": [
            {"key": "缺货率", "value": {"answer": "缺货品种数/考核品种数", "kind": "fact", "score": {"total": 0.9}},
             "kind": "fact", "created_at": "2026-08-01T00:00:00Z"},
            {"key": "怎么做周报", "value": {"answer": "1. 取数 → 2. 清洗 → 3. 填充模板", "kind": "procedure"},
             "kind": "procedure", "created_at": "2026-08-02T00:00:00Z"},
        ]
    }, ensure_ascii=False), encoding="utf-8")
    core_dir = root / "memory" / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "knowledge-hub.json").write_text(json.dumps({
        "entries": [
            {"key": "preference:格式", "value": {"rule": "表格优先"}, "kind": "fact", "created_at": "2026-08-01T00:00:00Z"},
        ]
    }, ensure_ascii=False), encoding="utf-8")


class TestIndex(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="dr-idx-"))
        _seed(self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_build_and_status(self):
        out = index.build(self.root)
        self.assertTrue(out["ok"])
        self.assertEqual(out["entries"], 3)
        st = index.status(self.root)
        self.assertEqual(st["entries"], 3)
        self.assertEqual(st["by_scope"], {"semantic": 2, "core": 1})
        self.assertFalse(st["stale"])

    def test_search_chinese_trigram(self):
        index.build(self.root)
        r = index.search(self.root, "缺货率")
        self.assertTrue(r["ok"])
        self.assertTrue(any(h["key"] == "缺货率" for h in r["hits"]), r["hits"])

    def test_search_kind_filter(self):
        index.build(self.root)
        r = index.search(self.root, "周报", kind="procedure")
        self.assertTrue(r["ok"])
        self.assertTrue(all(h["kind"] == "procedure" for h in r["hits"]))
        self.assertTrue(any("怎么做周报" in h["key"] for h in r["hits"]))

    def test_search_short_query_like(self):
        index.build(self.root)
        r = index.search(self.root, "格式")
        self.assertTrue(r["ok"])
        self.assertTrue(any("preference:格式" in h["key"] for h in r["hits"]))

    def test_stale_auto_rebuild(self):
        index.build(self.root)
        sem = self.root / "memory" / "semantic" / "knowledge-hub.json"
        doc = json.loads(sem.read_text(encoding="utf-8"))
        doc["entries"].append({"key": "成本优势率", "value": {"answer": "低于合理P4*0.99购进的订单金额/总订单金额"},
                               "kind": "fact", "created_at": "2026-08-03T00:00:00Z"})
        sem.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        r = index.search(self.root, "成本优势率")  # 源变陈旧 → search 自动重建
        self.assertTrue(r["ok"])
        self.assertTrue(any(h["key"] == "成本优势率" for h in r["hits"]), r["hits"])
        self.assertEqual(index.status(self.root)["entries"], 4)

    def test_search_no_index_builds(self):
        # 未 build 直接 search：自动构建
        r = index.search(self.root, "缺货率")
        self.assertTrue(r["ok"])
        self.assertTrue(any(h["key"] == "缺货率" for h in r["hits"]))


if __name__ == "__main__":
    unittest.main()

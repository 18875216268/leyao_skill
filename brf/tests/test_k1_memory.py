"""K1 本地知识层单测：三维检索评分排序 / 注入防护围栏 / kind 过滤。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent          # brf/tests
BRF_ROOT = HERE.parent                          # brf/
SKILL_ROOT = BRF_ROOT.parent                    # 包根（skill 根目录）
sys.path.insert(0, str(BRF_ROOT))

from scripts.sources.k1_memory import k1_inject, k1_layer  # noqa: E402

PY = sys.executable
MEM = SKILL_ROOT / "scripts" / "memory.py"
SUP = SKILL_ROOT / "scripts" / "supervisor.py"


def _put(root, scope, key, value, kind="fact", note="seed"):
    ev = json.loads(subprocess.run(
        [PY, str(SUP), "record", "--work-dir", root, "--profile", "knowledge-hub",
         "--type", "caliber", "--note", note], capture_output=True, text=True).stdout)
    p = json.loads(subprocess.run(
        [PY, str(SUP), "propose", "--work-dir", root, "--profile", "knowledge-hub",
         "--target", f"{scope}:knowledge-hub", "--change", key, "--risk", "low",
         "--evidence", ev["event_id"]], capture_output=True, text=True).stdout)
    subprocess.run([PY, str(SUP), "approve", "--work-dir", root, p["proposal_id"], "--who", "auto"],
                   capture_output=True, text=True)
    subprocess.run([PY, str(MEM), "put", "--work-dir", root, "--scope", scope,
                    "--scope-id", "knowledge-hub", "--key", key, "--value", json.dumps(value, ensure_ascii=False),
                    "--source", "seed", "--evidence", ev["event_id"],
                    "--proposal-id", p["proposal_id"], "--kind", kind], capture_output=True, text=True)


class TestK1Memory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="dr-k1-")
        _put(cls._tmp, "semantic", "缺货率", {"answer": "缺货品种数/考核品种数", "score": {"total": 0.80}}, "fact", "v1")
        _put(cls._tmp, "semantic", "缺货率", {"answer": "缺货品种数/考核品种数（含在途）", "score": {"total": 0.95}}, "fact", "v2")
        _put(cls._tmp, "semantic", "怎么做周报", {"answer": "1. 取数 → 2. 清洗 → 3. 填充模板"}, "procedure")

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_three_dim_score_ranks_newer_better_first(self):
        # 三维评分：同主题多版本 → 蒸馏分更高的排前（relevance/recency 相同时 importance 区分）
        hits = k1_layer("term", "缺货率", self._tmp)
        self.assertEqual(hits[0]["source"], "memory")
        self.assertIn("score", hits[0])
        self.assertIn("dims", hits[0])
        self.assertIn("（含在途）", hits[0]["answer"])  # 高分版在前
        self.assertGreaterEqual(hits[0]["score"], hits[1]["score"])

    def test_kind_filter(self):
        # kind=procedure 只返回怎么做类
        hits = k1_layer("process", "怎么做周报", self._tmp, kind="procedure")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["kind"], "procedure")

    def test_inject_fence_and_recall(self):
        # 防护围栏：顶层 fence 标注 + 条目 recall 来源标注
        inj = k1_inject("proactive", self._tmp)
        self.assertIn("fence", inj)
        self.assertIn("回忆", inj["fence"])
        procs = inj.get("procedures") or []
        self.assertTrue(procs)
        self.assertTrue(all(p.get("recall") == "semantic" for p in procs))


if __name__ == "__main__":
    unittest.main()

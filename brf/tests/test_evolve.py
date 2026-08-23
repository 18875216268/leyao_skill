"""进化引擎 KnowledgeGovernor 单测：蒸馏/评分/验证/帕累托/处置/分流。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.evolve import (classify_scope, distill, disposition, evolve, generalizability,
                            norm_key, pareto, quality_score, score, verify)


class TestEvolve(unittest.TestCase):
    def test_distill_three_types(self):
        d = distill("成本优势率怎么算", "低于合理P4*0.99购进的订单金额/总订单金额", "ops-metrics", "caliber")
        self.assertEqual(d["distill_type"], "lesson")   # 口径 → 教训类
        self.assertEqual(d["category"], "caliber")
        w = distill("怎么做周报", "先取数后分析再填充模板", "ask", "process")
        self.assertEqual(w["distill_type"], "workflow")  # 流程 → 工作流类
        t = distill("查一下毛利制度", "调云智库搜索", "leyou", "tool")
        self.assertEqual(t["distill_type"], "skill")     # 工具 → 技能类
        self.assertEqual(norm_key("成本优势率怎么算"), "成本优势率")

    def test_score_five_dims(self):
        c = distill("缺货率", "缺货品种数/考核品种数", "ops-glossary", "term")
        s = score(c, "authority", hit_count=5, adopt_count=3)
        self.assertIn("total", s)
        for d in ("quality", "value", "freshness", "source", "general"):
            self.assertGreaterEqual(s[d], 0)
        self.assertLessEqual(s["total"], 1.0)
        # authority 来源分高于 reference
        self.assertGreater(s["source"], score(c, "candidate")["source"])
        # 命中越多价值分越高
        self.assertGreater(score(c, "authority", hit_count=10)["value"],
                           score(c, "authority", hit_count=0)["value"])

    def test_classify_scope(self):
        # 个人行为模式 → personal（只进本地）
        self.assertEqual(classify_scope("怎么安排每天工作", "我习惯周一先看缺货率再看出库", "process"), "personal")
        self.assertEqual(classify_scope("这件事怎么处理", "我个人偏好先沟通再执行", "method"), "personal")
        # 一次性事件 → personal
        self.assertEqual(classify_scope("客户情况", "昨天A客户退换货复盘", "experience"), "personal")
        # 术语/口径/方法/模板/流程 → shared（公共经验）
        self.assertEqual(classify_scope("缺货率是什么", "缺货品种数/考核品种数", "term"), "shared")
        self.assertEqual(classify_scope("成本优势率怎么算", "低于合理P4*0.99购进的订单金额/总订单金额", "caliber"), "shared")
        # 无个体语境的业务经验 → shared（默认）
        self.assertEqual(classify_scope("退换货怎么处理", "高发品类按库存周转优先级处理", "experience"), "shared")

    def test_generalizability(self):
        # 通用类型（term/caliber/method...）→ 高分（可迁移）
        gen = generalizability({"content": "缺货率是什么 → 缺货品种数/考核品种数"}, "term")
        self.assertGreaterEqual(gen, 0.9)
        # 个体/事件语境 → 低分（不可迁移）
        low = generalizability({"content": "怎么安排每天工作 → 我习惯周一先看缺货率"}, "process")
        self.assertLessEqual(low, 0.2)

    def test_evolve_scope_wired(self):
        # evolve 返回带 scope 与 general（learn 据此决定是否上传池）
        out = evolve("成本优势率怎么算", "低于合理P4*0.99购进的订单金额/总订单金额",
                     "ops-metrics", "caliber", "authority")
        self.assertEqual(out["scope"], "shared")
        self.assertGreaterEqual(out["general"], 0.9)
        pers = evolve("怎么安排每天工作", "我习惯周一先看缺货率", "ask", "process", "reference")
        self.assertEqual(pers["scope"], "personal")
        self.assertLessEqual(pers["general"], 0.2)

    def test_quality_score(self):
        self.assertGreater(quality_score({"content": "长内容" * 30}), quality_score({"content": "短"}))

    def test_verify_gate(self):
        ok, msg = verify({"content": "太短"}, "reference")
        self.assertFalse(ok)
        ok, msg = verify({"content": "这是一条足够长且可执行的经验内容演示"}, "authority")
        self.assertTrue(ok)
        ok, _ = verify({"content": "足够长的内容测试验证门禁逻辑是否正常"}, "candidate")
        self.assertFalse(ok)  # candidate 信任级不足

    def test_pareto_decisions(self):
        # 无现有 → accept
        self.assertEqual(pareto({"quality": .8, "value": .5, "freshness": .9, "source": .7, "general": .8}, []), "accept")
        # 新条目全维度被压制 → reject（去劣）
        existing = [{"quality": .9, "value": .9, "freshness": .95, "source": .9, "general": .9}]
        self.assertEqual(pareto({"quality": .5, "value": .4, "freshness": .5, "source": .4, "general": .5}, existing), "reject")
        # 新条目全维度更优 → accept（上位）
        self.assertEqual(pareto({"quality": .99, "value": .99, "freshness": .99, "source": .99, "general": .99}, existing), "accept")
        # 互有胜负 → merge（整合）
        mixed = [{"quality": .9, "value": .1, "freshness": .9, "source": .9, "general": .9}]
        self.assertEqual(pareto({"quality": .5, "value": .9, "freshness": .5, "source": .5, "general": .5}, mixed), "merge")

    def test_disposition_never_delete(self):
        self.assertEqual(disposition("accept")["status"], "active")
        d = disposition("merge", version=1)
        self.assertEqual(d["status"], "active")
        self.assertEqual(d["version"], 2)
        # 知识绝不真删：reject 仅标记 deprecated（保留历史）
        self.assertEqual(disposition("reject")["status"], "deprecated")

    def test_evolve_pipeline(self):
        out = evolve("成本优势率怎么算", "低于合理P4*0.99购进的订单金额/总订单金额",
                     "ops-metrics", "caliber", "authority")
        self.assertTrue(out["ok"])
        self.assertEqual(out["decision"], "accept")
        self.assertIn("score", out)
        # 验证失败路径
        bad = evolve("x", "太短", "ask", "term", "reference")
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["reason"], "verify_failed")

    def test_distill_refined(self):
        # L0 快速通道：无 distilled → 轨迹快照 + refined=False（向后兼容）
        d0 = distill("怎么做周报", "先取数再分析再填充模板", "ask", "process")
        self.assertFalse(d0["refined"])
        self.assertIn("先取数再分析再填充模板", d0["content"])
        # L1 深度蒸馏：提供 distilled → 提炼版 content + refined=True
        d1 = distill("怎么做周报", "先取数再分析再填充模板", "ask", "process",
                     distilled="1. 取数（多源）→ 2. 清洗校验 → 3. 按模板填充 → 4. 待复核")
        self.assertTrue(d1["refined"])
        self.assertIn("1. 取数（多源）", d1["content"])
        self.assertNotIn("先取数再分析再填充模板", d1["content"])

    def test_quality_refined_bonus(self):
        # 提炼过 → 质量分更高（同内容基础上）
        raw = {"content": "怎么做周报 → 取数、分析、填充、复核"}
        ref = {"content": "怎么做周报 → 取数、分析、填充、复核", "refined": True}
        self.assertGreater(quality_score(ref), quality_score(raw))

    def test_verify_structure_l1(self):
        # L1 workflow：refined 但无步骤序列 → 结构不完整
        w_bad = {"content": "怎么做周报 → 先取数再分析再填充模板", "refined": True, "verified": False}
        ok, msg = verify(w_bad, "authority", "process")
        self.assertFalse(ok)
        self.assertIn("结构不完整", msg)
        # 有步骤序列 → 通过
        w_ok = {"content": "怎么做周报 → 1. 取数 → 2. 清洗 → 3. 填充模板", "refined": True, "verified": False}
        ok, _ = verify(w_ok, "authority", "process")
        self.assertTrue(ok)
        # L1 skill：refined 但无执行痕迹 → 结构不完整
        s_bad = {"content": "查毛利制度 → 搜索云智库资料库", "refined": True, "verified": False}
        ok, msg = verify(s_bad, "authority", "tool")
        self.assertFalse(ok)
        # verified=True（AI 已自验证）→ 跳过结构检查
        s_ver = {"content": "查毛利制度 → 搜索云智库资料库", "refined": True, "verified": True}
        ok, _ = verify(s_ver, "authority", "tool")
        self.assertTrue(ok)
        # L0：无 refined → 结构检查不启用（原行为，向后兼容）
        l0 = {"content": "怎么做周报 → 先取数再分析再填充模板", "refined": False}
        ok, _ = verify(l0, "authority", "process")
        self.assertTrue(ok)

    def test_evolve_refined_wired(self):
        # evolve 透传 distilled/verified → 返回 refined 标志
        out = evolve("怎么做周报", "先取数再分析再填充模板", "ask", "process", "reference",
                     distilled="1. 取数 → 2. 清洗 → 3. 填充 → 4. 待复核")
        self.assertTrue(out["ok"])
        self.assertTrue(out["refined"])
        self.assertIn("refined", out["candidate"])
        # 结构不完整的提炼 → verify_failed
        bad = evolve("怎么做周报", "先取数再分析再填充模板", "ask", "process", "reference",
                     distilled="就是按流程做")
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["reason"], "verify_failed")


if __name__ == "__main__":
    unittest.main()

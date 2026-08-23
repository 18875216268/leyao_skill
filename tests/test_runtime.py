import tempfile
import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import workspace, orchestrator, run_state, capabilities, memory, supervisor

class RuntimeArchitectureTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def task_run(self):
        workspace.init_task(self.root,"project-progress","项目进度")
        state=workspace.new_run(self.root,"project-progress",1,1)
        return state["run_id"]
    def test_inspect_is_read_only(self):
        (self.root/"工作记录").mkdir(); (self.root/"工作记录"/"data.xlsx").write_bytes(b"x")
        before=sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        result=workspace.inspect(self.root)
        after=sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        self.assertEqual(before,after); self.assertTrue(result["materials"])
    def test_work_order_and_runtime_checkpoint(self):
        workspace.init_order(self.root,"weekly-review","完成周报")
        workspace.build_package(self.root,"weekly-review")
        rid=self.task_run(); run_state.update(self.root,rid,"running","acquire-data")
        source=self.root/"source.csv";source.write_text("a,b\n1,2\n",encoding="utf-8")
        run_state.checkpoint(self.root,rid,"k5",{"stage":"data"},[str(source)])
        self.assertFalse(run_state.resume(self.root,rid,"k5")["stale"])
        source.write_text("a,b\n1,3\n",encoding="utf-8")
        self.assertTrue(run_state.resume(self.root,rid,"k5")["stale"])
    def test_high_deviation_blocks(self):
        rid=self.task_run();run_state.update(self.root,rid,"running")
        run_state.deviation(self.root,rid,"add",category="scope-drift",severity="high",expected="A区",actual="全量")
        self.assertEqual(run_state.load(self.root,rid)[1]["status"],"blocked")
    def test_dag_cycle_prevention(self):
        workspace.init_order(self.root,"weekly-review","完成周报")
        orchestrator.add_node(self.root,"weekly-review","task-a","task");orchestrator.add_node(self.root,"weekly-review","task-b","task")
        orchestrator.add_edge(self.root,"weekly-review","task-a","task-b","dependency")
        with self.assertRaises(ValueError):orchestrator.add_edge(self.root,"weekly-review","task-b","task-a","dependency")
    def test_capability_selection_is_explicit(self):
        capabilities.register(self.root,{"id":"reader","purpose":"read","capabilities":["inspect"],"inputs":["xlsx"],"outputs":["json"],"accuracy_score":.9,"speed_score":.8,"format_fidelity_score":.8,"auditability_score":.9,"side_effects":["read"]})
        result=capabilities.select(self.root,"inspect","xlsx","run-1","step-1")
        self.assertEqual(result["selected"],"reader");self.assertEqual(result["approval"],"none")
    def test_long_term_memory_requires_proposal(self):
        with self.assertRaises(ValueError):memory.put(self.root,"core","default","x",1,"test")
        event=supervisor.record(self.root,"default","memory","evidence","day","","",True,"task-a")
        proposal=supervisor.propose(self.root,"default","core:default","x","low",[event["event_id"]])
        supervisor.decide(self.root,proposal["proposal_id"],True,"user")
        value=memory.put(self.root,"core","default","x",1,"test",[event["event_id"]],proposal["proposal_id"])
        self.assertEqual(value["scope"],"core")
    def test_supervisor_event_and_proposal(self):
        event=supervisor.record(self.root,"default","template-fill","修正E列","week","E列累计","run-1")
        proposal=supervisor.propose(self.root,"default","template-map","E列累计","high",[event["event_id"]])
        self.assertEqual(supervisor.decide(self.root,proposal["proposal_id"],True,"user")["status"],"approved")

    def test_memory_profile_partitions(self):
        # core Profile 用户卡片：按前缀分区聚合（habit/preference/caliber/tool/misc）
        ev=supervisor.record(self.root,"default","memory","p","day","","",True,"t")
        for k in ("habit:report","preference:格式","caliber:缺货率","tool:BI","其他键"):
            p=supervisor.propose(self.root,"default","core:default",k,"low",[ev["event_id"]])
            supervisor.decide(self.root,p["proposal_id"],True,"auto")
            memory.put(self.root,"core","default",k,{"rule":"x"},"t",[ev["event_id"]],p["proposal_id"])
        prof=memory.profile(self.root,"default")
        parts=prof["partitions"]
        self.assertEqual([i["key"] for i in parts["habits"]],["habit:report"])
        self.assertEqual([i["key"] for i in parts["preferences"]],["preference:格式"])
        self.assertEqual([i["key"] for i in parts["calibers"]],["caliber:缺货率"])
        self.assertEqual([i["key"] for i in parts["tools"]],["tool:BI"])
        self.assertIn("其他键",[i["key"] for i in parts["misc"]])

    def test_supervisor_assess_report(self):
        # assess 评估报告：事件统计/成功率/质量信号
        for i in range(3):
            supervisor.record(self.root,"default","report",f"n{i}","day","用户偏好两位小数")
        ass=supervisor.assess(self.root,"default")
        self.assertEqual(ass["event_count"],3)
        self.assertEqual(ass["success_rate"],1.0)
        types=ass["quality_signals"]
        self.assertTrue(any(s["type"]=="high_frequency" for s in types))
        self.assertTrue(any(s["type"]=="correction" for s in types))

if __name__=="__main__":unittest.main()

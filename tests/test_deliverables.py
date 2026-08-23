import tempfile
import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import workspace, deliverables

class DeliverableLifecycleTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def confirmed_task(self,tid):
        workspace.init_task(self.root,tid,tid)
        result=self.root/"tasks"/tid/"result"/"confirmed"/f"{tid}.md"; result.write_text("ok",encoding="utf-8")
    def spec(self,ident,kind="report",typ="weekly"):
        return {"id":ident,"name":ident,"kind":kind,"type":typ,"status":"draft","bindings":[{"binding_id":"a","task_id":"task-a","role":"source","required":True,"selector":{"policy":"period_match","allowed_states":["confirmed","delivered"]}}],"outputs":[{"output_id":"main","format":"markdown","destination":"pending-review"}],"required_gates":["intent","data","calculation","delivery"]}
    def test_empty_stage_cannot_confirm(self):
        self.confirmed_task("task-a"); deliverables.register(self.root,self.spec("weekly-report")); run=deliverables.create_run(self.root,"weekly-report")
        for gate in ("intent","data","calculation","delivery"): deliverables.mutate(self.root,run["run_id"],"gate",gate=gate,status="passed")
        with self.assertRaises(ValueError): deliverables.mutate(self.root,run["run_id"],"confirm")
    def test_confirmed_filter_and_gated_delivery(self):
        self.confirmed_task("task-a"); deliverables.register(self.root,self.spec("weekly-report")); run=deliverables.create_run(self.root,"weekly-report")
        source=self.root/"tasks"/"task-a"/"result"/"confirmed"/"task-a.md"; deliverables.mutate(self.root,run["run_id"],"stage",str(source))
        with self.assertRaises(ValueError): deliverables.mutate(self.root,run["run_id"],"confirm")
        for gate in ("intent","data","calculation","delivery"): deliverables.mutate(self.root,run["run_id"],"gate",gate=gate,status="passed")
        run=deliverables.mutate(self.root,run["run_id"],"confirm"); self.assertEqual(run["status"],"confirmed")
        self.assertTrue(Path(run["outputs"][0]["confirmed_path"]).exists())
        run=deliverables.mutate(self.root,run["run_id"],"deliver"); self.assertEqual(run["status"],"delivered")
        self.assertTrue(Path(run["outputs"][0]["delivered_path"]).exists())
    def test_multibinding_reverse(self):
        self.confirmed_task("task-a"); self.confirmed_task("task-b")
        first=self.spec("weekly-report"); first["bindings"].append({"binding_id":"b","task_id":"task-b","role":"risk","required":True,"selector":{"policy":"latest","allowed_states":["confirmed"]}}); deliverables.register(self.root,first)
        second=self.spec("special-review","retrospective","special"); deliverables.register(self.root,second)
        self.assertEqual(set(deliverables.reverse(self.root,"task-a")),{"weekly-report","special-review"})
if __name__=="__main__":unittest.main()

import tempfile
import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import workspace, memory, supervisor

class SupervisionTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def test_working_requires_real_run_and_preserves_fields(self):
        with self.assertRaises(FileNotFoundError): memory.put(self.root,"working","run-missing","x",1,"user")
        workspace.init_task(self.root,"task-a","Task A"); run=workspace.new_run(self.root,"task-a",1,1)
        value=memory.put(self.root,"working",run["run_id"],"x",1,"user")
        self.assertIn("confirmed",value);self.assertIn("decisions",value)
    def test_long_term_proposal_and_target(self):
        event=supervisor.record(self.root,"default","template","mapping","week","E累计","run-1",True,"task-a")
        proposal=supervisor.propose(self.root,"default","core:default","E累计","low",[event["event_id"]])
        with self.assertRaises(ValueError): memory.put(self.root,"core","default","x",1,"user",[event["event_id"]],proposal["proposal_id"])
        supervisor.decide(self.root,proposal["proposal_id"],True,"user")
        value=memory.put(self.root,"core","default","E累计","confirmed", "user",[event["event_id"]],proposal["proposal_id"])
        self.assertEqual(value["scope"],"core")
    def test_profile_isolation_and_dry_summary(self):
        supervisor.record(self.root,"alice","x","a","day")
        supervisor.record(self.root,"bob","x","b","day")
        self.assertEqual(len(supervisor.events(self.root,"alice")),1);self.assertEqual(len(supervisor.events(self.root,"bob")),1)
        before=sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        value=supervisor.summarize(self.root,"alice",True)
        after=sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        self.assertEqual(before,after);self.assertEqual(value["event_count"],1)
if __name__=="__main__":unittest.main()

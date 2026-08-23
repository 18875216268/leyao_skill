import tempfile
import unittest
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import deliverables

class DeliverableContractTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def spec(self,kind,typ):
        return {"id":f"{kind}-{typ}","name":"测试交付物","kind":kind,"type":typ,"status":"draft","bindings":[],"outputs":[{"output_id":"main","format":"markdown","destination":"pending-review"}],"required_gates":["intent","data","calculation","delivery"]}
    def test_four_deliverable_categories(self):
        for kind,typ in (("report","daily"),("retrospective","special"),("template","spreadsheet"),("other","custom")):
            value=self.spec(kind,typ); deliverables.validate(value)
    def test_invalid_kind_and_duplicate_binding_fail(self):
        value=self.spec("report","daily"); value["type"]="custom"
        with self.assertRaises(ValueError): deliverables.validate(value)
        value=self.spec("report","daily"); value["bindings"]=[{"binding_id":"x"},{"binding_id":"x"}]
        with self.assertRaises(ValueError): deliverables.validate(value)

if __name__=="__main__": unittest.main()

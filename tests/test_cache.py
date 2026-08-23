import tempfile
import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import cache, cache_governor, context_pack

class CacheTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def test_key_hit_and_content_change_miss(self):
        source=self.root/"input.txt";source.write_text("abcd",encoding="utf-8")
        ref={"path":"input.txt","checksum":cache.checksum(source)}
        key=cache.make_key("analysis","engine-v1",[ref],{"scope":"week"})
        stored=cache.store(self.root,"analysis",key,"engine-v1",[ref],{"scope":"week"},{"result":1})
        self.assertEqual(stored["status"],"stored")
        self.assertEqual(cache.lookup(self.root,key)["status"],"hit")
        source.write_text("wxyz",encoding="utf-8")
        changed={"path":"input.txt","checksum":cache.checksum(source)}
        other=cache.make_key("analysis","engine-v1",[changed],{"scope":"week"})
        self.assertNotEqual(key,other);self.assertEqual(cache.lookup(self.root,other)["status"],"miss")
    def test_sensitive_and_force_refresh_bypass_without_write(self):
        key=cache.make_key("analysis","engine-v1",[],{})
        before=list(self.root.rglob("*"))
        result=cache.store(self.root,"analysis",key,"engine-v1",[],{}, {"x":1},sensitivity="sensitive")
        self.assertEqual(result["status"],"bypass");self.assertEqual(before,list(self.root.rglob("*")))
        result=cache.lookup(self.root,key,force_refresh=True);self.assertEqual(result["reason"],"force_refresh")
    def test_context_budget_and_stable_hash(self):
        items=[{"id":"user","priority":0,"text":"user-goal","source":"request"},{"id":"history","priority":5,"text":"x"*20,"source":"event"},{"id":"rule","priority":1,"text":"rule","source":"memory"}]
        # Build only requires runtime run state; create the minimal canonical fixture.
        (self.root/"runtime"/"runs"/"run-one").mkdir(parents=True)
        (self.root/"runtime"/"runs"/"run-one"/"state.json").write_text("{}",encoding="utf-8")
        one=context_pack.build(self.root,"run-one",budget=12,items=items)
        two=context_pack.build(self.root,"run-one",budget=12,items=items)
        self.assertEqual(one["pack_hash"],two["pack_hash"]);self.assertLessEqual(one["used"],12+len("user-goal"))
        self.assertTrue(any(x["id"]=="history" for x in one["truncated"]))
    def test_governor_keeps_pinned_and_dry_prune(self):
        key=cache.make_key("plan","planner-v1",[],{})
        cache.store(self.root,"plan",key,"planner-v1",[],{}, {"plan":1})
        entry=cache.lookup(self.root,key)["entry"];entry_path=cache.entry_path(self.root,key);entry["pinned_reason"]="active-run";cache.atomic_write_json(entry_path,entry)
        result=cache_governor.prune(self.root,apply=False)
        self.assertEqual(result["actions"],[])
        self.assertTrue(cache.payload_path(self.root,key).exists())

if __name__=="__main__":unittest.main()

#!/usr/bin/env python3
"""Build deterministic run-local context packs within a character budget."""
from __future__ import annotations
import argparse,json,sys
from runtime_core import atomic_write_json,object_meta,semantic_hash,read_json,runtime_path,safe_id,work_dir

def build(root,run_id,budget=12000,items=None):
 run_id=safe_id(run_id,"run-id");base=runtime_path(root,"runtime","runs",run_id,create_parent=False)
 if not (base/"state.json").exists():raise FileNotFoundError(run_id)
 candidates=items or []
 # Lower number = stronger priority; priority 0 entries cannot be omitted.
 ordered=sorted(candidates,key=lambda x:(x.get("priority",5),x.get("id","") ))
 chosen=[];truncated=[];used=0
 for item in ordered:
  text=item.get("text","");size=len(text)
  if item.get("priority",5)==0 or used+size<=budget:
   chosen.append({"id":item.get("id"),"priority":item.get("priority",5),"text":text,"source":item.get("source")});used+=size
  else:truncated.append({"id":item.get("id"),"reason":"budget"})
 pack_hash=semantic_hash({"run_id":run_id,"budget":budget,"items":chosen,"policy":"context-pack-v1"})
 pack={**object_meta("context_pack",safe_id("pack-"+pack_hash.removeprefix("sha256:")[:24],"pack-id")),"pack_hash":pack_hash,"run_id":run_id,"budget":budget,"used":used,"items":chosen,"sources":[x.get("source") for x in chosen if x.get("source")],"truncated":truncated,"policy_version":"1"}
 return pack
def attach(root,pack,dry_run=False):
 if dry_run:return {"status":"dry-run","pack_hash":pack["pack_hash"],"used":pack["used"]}
 target=runtime_path(root,"runtime","runs",pack["run_id"],"context","pack.json",create_parent=True);atomic_write_json(target,pack);return {"status":"attached","path":str(target),"pack_hash":pack["pack_hash"]}
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
 a=s.add_parser("build");a.add_argument("--work-dir");a.add_argument("--run-id",required=True);a.add_argument("--budget",type=int,default=12000);a.add_argument("--items",default="[]");a.add_argument("--dry-run",action="store_true")
 a=s.add_parser("show");a.add_argument("--work-dir");a.add_argument("--run-id",required=True)
 a=p.parse_args(argv)
 try:
  root=work_dir(a.work_dir,create=a.cmd=="build" and not a.dry_run)
  if a.cmd=="build":
   if a.budget<1:raise ValueError("budget must be positive")
   pack=build(root,a.run_id,a.budget,json.loads(a.items));out=attach(root,pack,a.dry_run)
  else:out=read_json(runtime_path(root,"runtime","runs",safe_id(a.run_id,"run-id"),"context","pack.json",create_parent=False))
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

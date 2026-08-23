#!/usr/bin/env python3
"""Cache self-maintenance: score entries, tier them, and prune only evictable payloads."""
from __future__ import annotations
import argparse,json,sys
from runtime_core import append_event,atomic_write_json,object_meta,read_json,runtime_path,utc_now,work_dir

def cache_root(root):return runtime_path(root,"runtime","cache",create_parent=True)
def entries(root):
 d=cache_root(root)/"entries";return [(p,read_json(p)) for p in sorted(d.glob("*.json"))] if d.is_dir() else []
def score(entry,now=None):
 uses=int(entry.get("usage_count",0));pinned=bool(entry.get("pinned_reason"));fresh=entry.get("status")=="ready";cost={"template":3,"artifact":3,"analysis":2,"workspace":2,"plan":1,"tool-plan":1,"context":1,"supervision":1}.get(entry.get("namespace"),1)
 importance=2 if entry.get("lineage_required") else 0
 total=uses*2+cost+importance+(5 if pinned else 0)+(2 if fresh else -3)
 tier="pinned" if pinned or entry.get("active_reference") else "warm" if total>=4 else "cold"
 return {"score":total,"tier":tier,"decision":"pinned" if tier=="pinned" else "keep" if tier=="warm" else "evictable","reason":"active/pinned" if tier=="pinned" else "frequent_or_costly" if tier=="warm" else "low_usage_rebuildable"}
def review(root):
 out=[];gov=cache_root(root)/"governance";gov.mkdir(parents=True,exist_ok=True)
 for p,e in entries(root):
  result=score(e);record={**object_meta("cache_governance_record",e["id"]),"cache_key":e["cache_key"],"usage_count":e.get("usage_count",0),"last_accessed":e.get("last_accessed_at"),**result}
  atomic_write_json(gov/(p.stem+".json"),record);out.append(record)
 return out
def prune(root,apply=False):
 reviewed=review(root);actions=[]
 for record in reviewed:
  if record["decision"]!="evictable":continue
  key=record["cache_key"];entry_path=cache_root(root)/"entries"/(key.removeprefix("sha256:")+".json");entry=read_json(entry_path)
  if not entry.get("evictable",True) or entry.get("lineage_required") or entry.get("active_reference"):continue
  payload=cache_root(root)/entry["payload"]["path"].split("runtime/cache/",1)[-1] if "runtime/cache/" in entry["payload"]["path"] else cache_root(root)/"payloads"/(key.removeprefix("sha256:")+".json")
  actions.append({"cache_key":key,"payload":str(payload),"action":"evict"})
  if apply:
   entry["status"]="evicted";entry["evicted_at"]=utc_now();entry["evicted_reason"]=record["reason"];atomic_write_json(entry_path,entry)
   if payload.exists():payload.unlink()
   append_event(root,"cache",{"op":"evict","cache_key":key,"reason":record["reason"]})
 return {"dry_run":not apply,"actions":actions}
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
 for cmd in ("review","status"):
  a=s.add_parser(cmd);a.add_argument("--work-dir")
 a=s.add_parser("prune");a.add_argument("--work-dir");a.add_argument("--apply",action="store_true")
 a=p.parse_args(argv)
 try:
  root=work_dir(a.work_dir,create=True);out=review(root) if a.cmd=="review" else prune(root,a.apply) if a.cmd=="prune" else [{"cache_key":e["cache_key"],"status":e["status"],"usage_count":e.get("usage_count",0)} for _,e in entries(root)]
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

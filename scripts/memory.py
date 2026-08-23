#!/usr/bin/env python3
"""Memory with run-local working state and proposal-gated long-term writes."""
from __future__ import annotations
import argparse,json,sys
from runtime_core import append_event,atomic_write_json,object_meta,read_json,runtime_path,safe_id,utc_now,work_dir
LONG_TERM={"semantic","core"}
def scope_path(root,scope,sid):
 sid=safe_id(sid,"scope-id",profile=scope=="core")
 if scope=="working":return runtime_path(root,"runtime","runs",safe_id(sid,"run-id"),"memory","working.json")
 if scope in LONG_TERM:return runtime_path(root,"memory",scope,sid+".json",create_parent=True)
 if scope=="episodic":return runtime_path(root,"reflections","events",sid+".json",create_parent=True)
 raise ValueError("scope must be working, episodic, semantic, or core")
def get(root,scope,sid):
 p=scope_path(root,scope,sid);return read_json(p) if p.exists() else {"object_type":"memory","scope":scope,"scope_id":sid,"entries":[]}
def put(root,scope,sid,key,value,source,evidence=None,proposal_id=None,kind="fact"):
 if scope=="working":
  run_root=runtime_path(root,"runtime","runs",safe_id(sid,"run-id"),create_parent=False)
  if not (run_root/"state.json").exists():raise FileNotFoundError(f"run not found: {sid}")
  state=read_json(run_root/"state.json")
  if state.get("status") in {"completed","failed","cancelled"}:raise ValueError("terminal run working memory is immutable")
 if scope in LONG_TERM:
  if not proposal_id or not evidence:raise ValueError("long-term memory requires proposal_id and evidence")
  proposal=read_json(runtime_path(root,"proposals",safe_id(proposal_id,"proposal-id")+".json"))
  if proposal.get("status")!="approved":raise ValueError("approved proposal required")
  expected=f"{scope}:{sid}"
  if proposal.get("target")!=expected or proposal.get("change")!=key:raise ValueError("proposal target or key does not match memory write")
  known={p.name.removesuffix(".json") for p in runtime_path(root,"reflections","events",create_parent=False).glob("*.json")} if runtime_path(root,"reflections","events",create_parent=False).is_dir() else set()
  if not set(evidence).issubset(known):raise ValueError("memory evidence is not a known event")
 p=scope_path(root,scope,sid)
 if scope=="working":
  old=read_json(p)
  old.setdefault("confirmed",{});old.setdefault("assumptions",[]);old.setdefault("decisions",[])
  old["confirmed"][key]={"value":value,"source":source}
  atomic_write_json(p,old);append_event(root,"memory",{"op":"put_working","scope_id":sid,"key":key});return old
 old=read_json(p) if p.exists() else {"entries":[]};version=len(old.get("entries",[]))+1
 entry={"key":key,"value":value,"source":source,"evidence":evidence or [],"proposal_id":proposal_id,"approved":True,"version":version,"created_at":utc_now(),"kind":kind if kind in ("fact","procedure") else "fact"}
 data={**object_meta("memory",f"{scope}-{sid}",version),"scope":scope,"scope_id":sid,"entries":old.get("entries",[])+[entry]};atomic_write_json(p,data);append_event(root,"memory",{"op":"put","scope":scope,"scope_id":sid,"key":key,"kind":entry["kind"]});return data
def effective(root,core_id=None,semantic_ids=None,working_run_id=None):
 merged={};kinds={};sources=[]
 if core_id:
  for e in get(root,"core",core_id).get("entries",[]):merged[e["key"]]=e["value"];kinds[e["key"]]=e.get("kind","fact")
  sources.append(f"core:{core_id}")
 for sid in semantic_ids or []:
  for e in get(root,"semantic",sid).get("entries",[]):merged[e["key"]]=e["value"];kinds[e["key"]]=e.get("kind","fact")
  sources.append(f"semantic:{sid}")
 if working_run_id:
  working=get(root,"working",working_run_id)
  for k,v in working.get("confirmed",{}).items():merged[k]=v.get("value",v)
  sources.append(f"working:{working_run_id}")
 return {"values":merged,"kinds":kinds,"sources":sources}

CORE_PARTITIONS = (("habit:", "habits"), ("preference:", "preferences"),
                   ("caliber:", "calibers"), ("tool:", "tools"))

def profile(root,sid):
 """core 用户卡片（Profile 结构化）：core entries 按前缀分区聚合，供 AI 快速理解用户画像。
 分区：habit:(习惯) / preference:(偏好) / caliber:(口径) / tool:(工具) / misc(其它)。
 只读视图，不新增存储——core 仍按 key 前缀分区写入，本命令提供聚合读。
 """
 sid=safe_id(sid,"scope-id",profile=True)
 entries=get(root,"core",sid).get("entries",[])
 parts={"habits":[],"preferences":[],"calibers":[],"tools":[],"misc":[]}
 for e in entries:
  k=e.get("key","");item={"key":k,"value":e.get("value"),"source":e.get("source"),
                          "created_at":e.get("created_at"),"kind":e.get("kind","fact")}
  for prefix,field in CORE_PARTITIONS:
   if k.startswith(prefix):
    parts[field].append(item);break
  else:
   parts["misc"].append(item)
 return {**object_meta("core_profile",sid),"profile_id":sid,"partitions":parts,"generated_at":utc_now()}

def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
 a=s.add_parser("get");a.add_argument("--work-dir");a.add_argument("--scope",required=True);a.add_argument("--scope-id",required=True)
 a=s.add_parser("put");a.add_argument("--work-dir");a.add_argument("--scope",required=True);a.add_argument("--scope-id",required=True);a.add_argument("--key",required=True);a.add_argument("--value",required=True);a.add_argument("--source",required=True);a.add_argument("--evidence",action="append",default=[]);a.add_argument("--proposal-id");a.add_argument("--kind",default="fact",choices=["fact","procedure"])
 a=s.add_parser("effective");a.add_argument("--work-dir");a.add_argument("--core-id");a.add_argument("--semantic-id",action="append",default=[]);a.add_argument("--working-run-id")
 a=s.add_parser("profile");a.add_argument("--work-dir");a.add_argument("--scope-id",required=True)
 a=p.parse_args(argv)
 try:
  root=work_dir(a.work_dir,create=True)
  if a.cmd=="get":out=get(root,a.scope,a.scope_id)
  elif a.cmd=="put":out=put(root,a.scope,a.scope_id,a.key,json.loads(a.value),a.source,a.evidence,a.proposal_id,a.kind)
  elif a.cmd=="effective":out=effective(root,a.core_id,a.semantic_id,a.working_run_id)
  else:out=profile(root,a.scope_id)
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

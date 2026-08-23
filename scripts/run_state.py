#!/usr/bin/env python3
"""Canonical runtime state, quality gates, checkpoints and deviations."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from runtime_core import append_event,atomic_write_json,checksum,read_json,runtime_path,safe_id,utc_now,work_dir
TERMINAL={"completed","failed","cancelled"};GATES={"intent","data","calculation","delivery"}
ALLOWED={"created":{"running","waiting_dependency","cancelled"},"waiting_dependency":{"running","blocked","cancelled"},"running":{"waiting_review","needs_user_input","needs_review","blocked","failed","partial","completed","cancelled"},"waiting_review":{"running","needs_review","completed","cancelled"},"needs_user_input":{"running","cancelled"},"needs_review":{"running","completed","cancelled"},"blocked":{"running","cancelled"},"partial":{"running","completed","cancelled"},"failed":set(),"completed":set(),"cancelled":set()}
def base(root,rid):return runtime_path(root,"runtime","runs",safe_id(rid,"run-id"))
def load(root,rid):
 p=base(root,rid)/"state.json"
 if not p.exists():raise FileNotFoundError(rid)
 return p,read_json(p)
def update(root,rid,status=None,step=None,gate=None,gate_status=None):
 p,s=load(root,rid)
 if s["status"] in TERMINAL:raise ValueError("terminal run is immutable")
 if gate_status and not gate:raise ValueError("gate required")
 if gate and (gate not in GATES or gate_status not in {"passed","failed","pending"}):raise ValueError("invalid gate")
 if status and status!=s["status"] and status not in ALLOWED.get(s["status"],set()):raise ValueError(f"invalid transition {s['status']}->{status}")
 if status=="completed":
  if not all(s["gates"].get(g)=="passed" for g in GATES):raise ValueError("all quality gates must pass")
  manifest=read_json(p.parent/"manifest.json")
  if not manifest.get("outputs") and not s.get("outputs"):raise ValueError("completed run requires outputs")
 if gate:s["gates"][gate]=gate_status
 if step:s["current_step"]=step
 if status:s["status"]=status
 s.setdefault("history",[]).append({"at":utc_now(),"status":status,"step":step,"gate":gate,"gate_status":gate_status});atomic_write_json(p,s);append_event(root,"runtime",{"op":"update","run_id":rid,"status":s["status"]});return s
def checkpoint(root,rid,name,payload,inputs):
 p,s=load(root,rid)
 if s["status"] in TERMINAL:raise ValueError("terminal run is immutable")
 name=safe_id(name.lower(),"checkpoint-name");target=p.parent/"checkpoints"/(name+".json")
 if target.exists():raise FileExistsError(name)
 refs=[]
 for item in inputs:
  f=Path(item).resolve()
  if not f.exists():raise FileNotFoundError(f)
  refs.append({"path":str(f),"checksum":checksum(f)})
 data={"object_type":"checkpoint","schema_version":1,"id":name,"version":1,"created_at":utc_now(),"updated_at":utc_now(),"run_id":rid,"payload":payload,"inputs":refs}
 atomic_write_json(target,data,overwrite=False);s["last_checkpoint"]=name;s["stale"]=False;atomic_write_json(p,s);return data
def resume(root,rid,name):
 p,s=load(root,rid)
 if s["status"] in TERMINAL:raise ValueError("terminal run cannot resume")
 cp=read_json(p.parent/"checkpoints"/(safe_id(name.lower(),"checkpoint-name")+".json"));stale=any(not Path(x["path"]).exists() or checksum(Path(x["path"]))!=x["checksum"] for x in cp["inputs"])
 s["stale"]=stale;s["resume_from"]=name;s["status"]="needs_review" if stale else "running";atomic_write_json(p,s);return s
def deviation(root,rid,action,**kw):
 p,s=load(root,rid);d=p.parent/"deviations.json";log=read_json(d);items=log["items"]
 if action=="add":
  item={"id":f"dev-{len(items)+1}","run_id":rid,"category":kw["category"],"severity":kw["severity"],"expected":kw["expected"],"actual":kw["actual"],"action":kw.get("response","pause"),"status":"open"};items.append(item)
  if kw["severity"]=="high":s["status"]="blocked"
  elif kw["severity"]=="medium":s["status"]="needs_user_input"
 elif action=="resolve":
  item=next((x for x in items if x["id"]==kw["deviation_id"]),None)
  if not item:raise ValueError("deviation not found")
  item["status"]="resolved";item["resolution"]=kw.get("resolution","")
 else:return log
 atomic_write_json(d,log);atomic_write_json(p,s);return item
def record_output(root,rid,output_path):
 p,s=load(root,rid)
 if s["status"] in TERMINAL:raise ValueError("terminal run is immutable")
 source=Path(output_path).resolve();root_resolved=root.resolve()
 try:source.relative_to(root_resolved)
 except ValueError as exc:raise ValueError("output path escapes work-dir") from exc
 if not source.is_file():raise FileNotFoundError(source)
 item={"path":str(source),"checksum":checksum(source)}
 if item not in s["outputs"]:s["outputs"].append(item)
 manifest_path=p.parent/"manifest.json";manifest=read_json(manifest_path)
 if item not in manifest["outputs"]:manifest["outputs"].append(item)
 atomic_write_json(manifest_path,manifest);atomic_write_json(p,s);return s

def confirm_output(root,rid,output_path):
 p,s=load(root,rid)
 if s["status"]!="completed":raise ValueError("task run must be completed before confirming output")
 source=Path(output_path).resolve();root_resolved=root.resolve()
 try:source.relative_to(root_resolved)
 except ValueError as exc:raise ValueError("output path escapes work-dir") from exc
 if not source.is_file():raise FileNotFoundError(source)
 item={"path":str(source),"checksum":checksum(source)}
 manifest=read_json(p.parent/"manifest.json")
 if item not in s.get("outputs",[]) or item not in manifest.get("outputs",[]):
  raise ValueError("output must be recorded before task completion")
 destination=runtime_path(root,"tasks",s["task_id"],"result","confirmed",source.name,create_parent=True)
 if destination.exists():raise FileExistsError(destination)
 destination.write_bytes(source.read_bytes())
 append_event(root,"runtime",{"op":"confirm_output","run_id":rid,"task_id":s["task_id"],"path":str(destination),"checksum":checksum(destination)})
 return {"task_id":s["task_id"],"confirmed_path":str(destination),"checksum":checksum(destination)}

def main(argv=None):
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
 a=sub.add_parser("update");a.add_argument("--work-dir");a.add_argument("--run-id",required=True);a.add_argument("--status");a.add_argument("--step");a.add_argument("--gate");a.add_argument("--gate-status")
 a=sub.add_parser("complete");a.add_argument("--work-dir");a.add_argument("--run-id",required=True)
 a=sub.add_parser("checkpoint");a.add_argument("--work-dir");a.add_argument("--run-id",required=True);a.add_argument("--name",required=True);a.add_argument("--payload",default="{}");a.add_argument("--input",action="append",default=[])
 a=sub.add_parser("record-output");a.add_argument("--work-dir");a.add_argument("--run-id",required=True);a.add_argument("--path",required=True)
 a=sub.add_parser("confirm-output");a.add_argument("--work-dir");a.add_argument("--run-id",required=True);a.add_argument("--path",required=True)
 a=sub.add_parser("resume");a.add_argument("--work-dir");a.add_argument("--run-id",required=True);a.add_argument("--checkpoint",required=True)
 a=sub.add_parser("deviation");ss=a.add_subparsers(dest="sub",required=True)
 b=ss.add_parser("add");b.add_argument("--work-dir");b.add_argument("--run-id",required=True);b.add_argument("--category",required=True);b.add_argument("--severity",required=True);b.add_argument("--expected",required=True);b.add_argument("--actual",required=True)
 b=ss.add_parser("resolve");b.add_argument("--work-dir");b.add_argument("--run-id",required=True);b.add_argument("--deviation-id",required=True);b.add_argument("--resolution",required=True)
 b=ss.add_parser("list");b.add_argument("--work-dir");b.add_argument("--run-id",required=True)
 a=p.parse_args(argv)
 try:
  root=work_dir(a.work_dir,create=True)
  if a.cmd=="update":out=update(root,a.run_id,a.status,a.step,a.gate,a.gate_status)
  elif a.cmd=="complete":out=update(root,a.run_id,"completed")
  elif a.cmd=="checkpoint":out=checkpoint(root,a.run_id,a.name,json.loads(a.payload),a.input)
  elif a.cmd=="record-output":out=record_output(root,a.run_id,a.path)
  elif a.cmd=="confirm-output":out=confirm_output(root,a.run_id,a.path)
  elif a.cmd=="resume":out=resume(root,a.run_id,a.checkpoint)
  elif a.sub=="add":out=deviation(root,a.run_id,"add",category=a.category,severity=a.severity,expected=a.expected,actual=a.actual)
  elif a.sub=="resolve":out=deviation(root,a.run_id,"resolve",deviation_id=a.deviation_id,resolution=a.resolution)
  else:out=deviation(root,a.run_id,"list")
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

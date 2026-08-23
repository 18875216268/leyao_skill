#!/usr/bin/env python3
"""DeliverableSpec registry and gated deliverable lifecycle."""
from __future__ import annotations
import argparse,json,sys,uuid
from pathlib import Path
from runtime_core import append_event,atomic_write_json,checksum,contained,object_meta,read_json,runtime_path,safe_id,work_dir
KINDS={"report":{"daily","weekly","monthly","quarterly","yearly"},"retrospective":{"product","customer","special"},"template":{"spreadsheet","notebook","word","ppt","email"},"other":{"temporary-analysis","executive-brief","data-summary","topic-statistics","custom"}}
def spec_path(root,did):return runtime_path(root,"deliverables",safe_id(did,"deliverable-id"),"spec.json")
def validate(spec):
 for key in ("id","name","kind","type","bindings","outputs","required_gates"):
  if key not in spec:raise ValueError(f"missing {key}")
 if spec["kind"] not in KINDS or spec["type"] not in KINDS[spec["kind"]]:raise ValueError("invalid deliverable kind/type")
 ids=[x.get("binding_id") for x in spec["bindings"]]
 if len(ids)!=len(set(ids)) or not all(ids):raise ValueError("binding_id must be unique")
 if set(spec["required_gates"])!={"intent","data","calculation","delivery"}:raise ValueError("all four gates required")
def register(root,spec):
 validate(spec);did=safe_id(spec["id"],"deliverable-id");path=spec_path(root,did)
 if path.exists():raise FileExistsError(did)
 value={**object_meta("deliverable_spec",did,int(spec.get("version",1))),**spec,"id":did};value.setdefault("status","draft")
 for x in (path.parent,"result/pending-review","result/confirmed","result/delivered","runs","archive"):(path.parent/x if isinstance(x,str) else x).mkdir(parents=True,exist_ok=True)
 atomic_write_json(path,value,overwrite=False);append_event(root,"deliverable",{"op":"register","deliverable_id":did});return value
def list_specs(root):
 d=runtime_path(root,"deliverables",create_parent=False);return [read_json(p) for p in sorted(d.glob("*/spec.json"))] if d.is_dir() else []
def reverse(root,task):return [s["id"] for s in list_specs(root) if any(b.get("task_id")==task for b in s.get("bindings",[]))]
def task_outputs(root,task_id):
 base=runtime_path(root,"tasks",safe_id(task_id,"task-id"),"result",create_parent=False);out=[]
 for status in ("confirmed","delivered"):
  d=base/status
  if d.is_dir():
   for p in d.iterdir():
    if p.is_file():out.append({"task_id":task_id,"status":status,"path":str(p),"checksum":checksum(p)})
 return out
def create_run(root,did):
 spec=read_json(spec_path(root,did));inputs=[]
 for b in spec["bindings"]:
  found=task_outputs(root,b["task_id"])
  if b["required"] and not found:raise ValueError(f"binding has no confirmed input: {b['binding_id']}")
  inputs.extend({"binding_id":b["binding_id"],**x} for x in found)
 rid="deliverable-run-"+uuid.uuid4().hex;base=spec_path(root,did).parent/"runs"/rid;base.mkdir(parents=True)
 run={**object_meta("deliverable_run",rid),"run_id":rid,"deliverable_id":did,"spec_version":spec["version"],"status":"created","inputs":inputs,"outputs":[],"gates":{g:"pending" for g in spec["required_gates"]},"lineage":inputs}
 atomic_write_json(base/"run.json",run,overwrite=False);return run
def locate(root,rid):
 d=runtime_path(root,"deliverables",create_parent=False);matches=list(d.glob(f"*/runs/{safe_id(rid,'run-id')}/run.json")) if d.is_dir() else []
 if len(matches)!=1:raise FileNotFoundError(rid)
 return matches[0]
def mutate(root,rid,action,output=None,gate=None,status=None):
 p=locate(root,rid);run=read_json(p)
 if run["status"] in {"delivered","cancelled"}:raise ValueError("terminal deliverable run")
 if action=="stage":
  if not output:raise ValueError("--output required")
  src=Path(output).resolve();contained(root,src,must_exist=True);dest=p.parents[2]/"result"/"pending-review"/src.name
  if dest.exists():raise FileExistsError(dest)
  dest.write_bytes(src.read_bytes());run["outputs"].append({"path":str(dest),"checksum":checksum(dest),"status":"pending-review"});run["status"]="pending-review"
 elif action=="gate":
  if gate not in run["gates"] or status not in {"passed","failed"}:raise ValueError("invalid gate")
  run["gates"][gate]=status
 elif action=="confirm":
  if not run["outputs"]:raise ValueError("deliverable run requires staged outputs")
  if not all(v=="passed" for v in run["gates"].values()):raise ValueError("all gates must pass")
  for item in run["outputs"]:
   source=Path(item["path"])
   if not source.is_file() or checksum(source)!=item["checksum"]:raise ValueError("staged output is missing or changed")
   target=p.parents[2]/"result"/"confirmed"/source.name
   if target.exists():raise FileExistsError(target)
   target.write_bytes(source.read_bytes())
   item.update({"confirmed_path":str(target),"confirmed_checksum":checksum(target),"status":"confirmed"})
  run["status"]="confirmed"
 elif action=="deliver":
  if run["status"]!="confirmed":raise ValueError("confirm first")
  if not run["outputs"]:raise ValueError("deliverable run requires confirmed outputs")
  for item in run["outputs"]:
   source=Path(item.get("confirmed_path", ""))
   if not source.is_file() or checksum(source)!=item.get("confirmed_checksum"):raise ValueError("confirmed output is missing or changed")
   dest=p.parents[2]/"result"/"delivered"/source.name
   if dest.exists():raise FileExistsError(dest)
   dest.write_bytes(source.read_bytes())
   item.update({"delivered_path":str(dest),"delivered_checksum":checksum(dest),"status":"delivered"})
  run["status"]="delivered"
  atomic_write_json(p.parent/"manifest.json",{**object_meta("deliverable_manifest",run["run_id"],1),"run_id":run["run_id"],"deliverable_id":run["deliverable_id"],"inputs":run["inputs"],"outputs":run["outputs"],"lineage":run["lineage"]})
 atomic_write_json(p,run);append_event(root,"deliverable",{"op":action,"run_id":rid});return run
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
 a=s.add_parser("register");a.add_argument("--work-dir");a.add_argument("--file",required=True)
 a=s.add_parser("list");a.add_argument("--work-dir")
 a=s.add_parser("show");a.add_argument("--work-dir");a.add_argument("--deliverable-id",required=True)
 a=s.add_parser("reverse");a.add_argument("--work-dir");a.add_argument("--task-id",required=True)
 a=s.add_parser("create-run");a.add_argument("--work-dir");a.add_argument("--deliverable-id",required=True)
 for cmd in ("stage","confirm","deliver"):
  a=s.add_parser(cmd);a.add_argument("--work-dir");a.add_argument("--run-id",required=True)
  if cmd=="stage":a.add_argument("--output",required=True)
 a=s.add_parser("gate");a.add_argument("--work-dir");a.add_argument("--run-id",required=True);a.add_argument("--gate",required=True);a.add_argument("--status",required=True)
 a=p.parse_args(argv)
 try:
  root=work_dir(a.work_dir,create=True)
  out=register(root,json.loads(Path(a.file).read_text(encoding="utf-8"))) if a.cmd=="register" else list_specs(root) if a.cmd=="list" else read_json(spec_path(root,a.deliverable_id)) if a.cmd=="show" else reverse(root,a.task_id) if a.cmd=="reverse" else create_run(root,a.deliverable_id) if a.cmd=="create-run" else mutate(root,a.run_id,a.cmd,getattr(a,"output",None),getattr(a,"gate",None),getattr(a,"status",None))
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

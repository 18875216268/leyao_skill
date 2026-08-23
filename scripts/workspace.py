#!/usr/bin/env python3
"""Work package inspection and canonical v2 runtime initialization."""
from __future__ import annotations
import argparse,json,os,sys,uuid
from pathlib import Path
from runtime_core import append_event,atomic_write_json,content_hash,object_meta,read_json,runtime_path,safe_id,work_dir
MANAGED={"work-orders","tasks","deliverables","runtime","memory","capabilities","scheduler","proposals","audit_log","archive","reflections"}
def task_dir(root,tid):return runtime_path(root,"tasks",safe_id(tid,"task-id"))
def order_dir(root,wid):return runtime_path(root,"work-orders",safe_id(wid,"work-order-id"))
def run_dir(root,rid):return runtime_path(root,"runtime","runs",safe_id(rid,"run-id"))
def inspect(root,max_depth=3):
 if not root.exists():raise FileNotFoundError(root)
 folders=[];materials=[];unknown=[];base=len(root.parts)
 for cur,dirs,files in os.walk(root,followlinks=False):
  p=Path(cur);depth=len(p.parts)-base;dirs[:]=sorted(d for d in dirs if d not in MANAGED and not d.startswith("."))
  if depth>max_depth:dirs[:]=[];continue
  for f in sorted(files):
   q=p/f
   if q.is_symlink():continue
   low=f.lower();role="unknown";confidence=0
   if any(x in low for x in ("config","配置","说明","交接")):role,confidence="control_file",.9
   elif any(x in low for x in ("模板","template","待填")):role,confidence="output_template",.88
   elif any(x in low for x in ("导出","export","下载","raw","源数据")):role,confidence="raw_data",.78
   elif any(x in low for x in ("日报","周报","月报","复盘","report")):role,confidence="historical_example",.7
   elif q.suffix.lower() in {".py",".ps1",".sh"}:role,confidence="script",.95
   item={"path":q.relative_to(root).as_posix(),"type":q.suffix.lower().lstrip("."),"role":role,"confidence":confidence,"size":q.stat().st_size}
   materials.append(item)
   if role=="unknown":unknown.append(item["path"])
  if p!=root:folders.append({"path":p.relative_to(root).as_posix()})
 return {**object_meta("workspace_inspection","inspection"),"root":str(root),"folders":folders,"materials":materials,"unclassified_files":unknown,"fingerprint":content_hash(materials),"write_behavior":"read_only"}
def init_task(root,tid,name,kind="recurring"):
 tid=safe_id(tid,"task-id");base=task_dir(root,tid);path=base/"process"/"task.json"
 if path.exists():raise FileExistsError(tid)
 for x in ("process","result/pending-review","result/confirmed","result/delivered","archive"): (base/x).mkdir(parents=True,exist_ok=True)
 value={**object_meta("task",tid),"name":name,"kind":kind,"lifecycle":{"status":"draft"},"scope":{},"sources":[],"metrics":[],"workflow":{"version":1,"steps":[]},"outputs":[{"type":"unspecified","path":"result/pending-review"}],"validation":["Define validation before activation"],"dependencies":[],"schedule":None}
 atomic_write_json(path,value,overwrite=False);return value
def init_order(root,wid,request):
 wid=safe_id(wid,"work-order-id");base=order_dir(root,wid)
 if base.exists():raise FileExistsError(wid)
 base.mkdir(parents=True);common={"task_ids":[],"deliverable_ids":[]}
 files={"work-order.json":{**object_meta("work_order",wid),"request":request,"status":"received",**common},"requirement.json":{**object_meta("requirement",wid),"raw_request":request,"objectives":[],"constraints":[],"unresolved_items":[]},"workspace-package.json":{**object_meta("workspace_package",wid),"root":str(root),"folders":[],"materials":[],"relationships":[],"uncertainties":[],"handoffs":[]},"dependency-graph.json":{**object_meta("dependency_graph",wid),"nodes":[],"edges":[]},"orchestration-state.json":{**object_meta("orchestration_state",wid),"status":"received","nodes":{},"ready":[],"waiting":[],"blocked":[],"completed":[]},"intent-anchor.json":{**object_meta("intent_anchor",wid),"objectives":[],"scope":{},"deliverables":[],"constraints":[],"acceptance":[],"priorities":{},"sign_off":"unconfirmed"}}
 for n,v in files.items():atomic_write_json(base/n,v,overwrite=False)
 return files["work-order.json"]
def build_package(root,wid):
 base=order_dir(root,wid);req=read_json(base/"requirement.json");inv=inspect(root);out={**object_meta("workspace_package",safe_id(wid,"work-order-id")),"work_order_id":wid,"root":str(root),"request":req["raw_request"],"folders":inv["folders"],"materials":inv["materials"],"relationships":[],"control_files":[x["path"] for x in inv["materials"] if x["role"]=="control_file"],"uncertainties":[{"item":"No template detected","severity":"medium"}] if not any(x["role"]=="output_template" for x in inv["materials"]) else [],"handoffs":[],"fingerprint":inv["fingerprint"]}
 atomic_write_json(base/"workspace-package.json",out);return out
def new_run(root,tid,task_version,workflow_version,work_order_id=None):
 if task_version<1 or workflow_version<1:raise ValueError("versions must be >=1")
 tid=safe_id(tid,"task-id");
 if not (task_dir(root,tid)/"process"/"task.json").exists():raise FileNotFoundError(tid)
 rid="run-"+uuid.uuid4().hex;base=run_dir(root,rid)
 for x in ("checkpoints","input","raw","clean","analysis","scripts","temp","memory","tool-logs"): (base/x).mkdir(parents=True,exist_ok=False)
 common={"run_id":rid,"task_id":tid,"task_version":task_version,"workflow_version":workflow_version,"work_order_id":work_order_id}
 state={**object_meta("run_state",rid),**common,"status":"created","current_step":None,"steps":[],"inputs":[],"outputs":[],"gates":{"intent":"pending","data":"pending","calculation":"pending","delivery":"pending"},"last_checkpoint":None,"stale":False,"history":[]}
 manifest={**object_meta("run_manifest",rid),**common,"inputs":[],"outputs":[],"lineage":[]}
 anchor={**object_meta("intent_anchor",rid),**common,"objectives":[],"scope":{},"deliverables":[],"constraints":[],"acceptance":[],"priorities":{},"sign_off":"unconfirmed"}
 files={
  "index.json":{**object_meta("run_index",rid),**common,"storage_layout":"runtime-v2","storage_root":str(base)},
  "state.json":state,
  "manifest.json":manifest,
  "intent-anchor.json":anchor,
  "deviations.json":{**object_meta("deviation_log",rid),"items":[]},
  "memory/working.json":{**object_meta("working_memory",rid),"confirmed":{},"assumptions":[],"decisions":[]},
 }
 for n,v in files.items(): atomic_write_json(base/n,v,overwrite=False)
 append_event(root,"run",{"op":"create","run_id":rid,"task_id":tid});return state
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
 for n in ("inspect","init-work-order","build-package","init-task","new-run"):
  a=s.add_parser(n);a.add_argument("--work-dir")
  if n=="inspect":a.add_argument("--max-depth",type=int,default=3)
  if n=="init-work-order":a.add_argument("--work-order-id",required=True);a.add_argument("--request",required=True)
  if n=="build-package":a.add_argument("--work-order-id",required=True)
  if n=="init-task":a.add_argument("--task-id",required=True);a.add_argument("--name",required=True);a.add_argument("--kind",default="recurring")
  if n=="new-run":a.add_argument("--task-id",required=True);a.add_argument("--task-version",type=int,required=True);a.add_argument("--workflow-version",type=int,required=True);a.add_argument("--work-order-id")
 a=p.parse_args(argv)
 try:
  root=work_dir(a.work_dir,create=a.cmd!="inspect")
  out=inspect(root,a.max_depth) if a.cmd=="inspect" else init_order(root,a.work_order_id,a.request) if a.cmd=="init-work-order" else build_package(root,a.work_order_id) if a.cmd=="build-package" else init_task(root,a.task_id,a.name,a.kind) if a.cmd=="init-task" else new_run(root,a.task_id,a.task_version,a.workflow_version,a.work_order_id)
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError) as e:print(f"error: {e}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

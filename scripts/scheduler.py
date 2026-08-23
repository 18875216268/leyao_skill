#!/usr/bin/env python3
"""Declarative schedules and dispatch history; no daemon is started here."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from runtime_core import append_event,atomic_write_json,object_meta,read_json,runtime_path,safe_id,utc_now,work_dir

def sched_dir(root:Path)->Path:return runtime_path(root,"scheduler","schedules",create_parent=True)
def save(root:Path,schedule:dict)->dict:
 sid=safe_id(schedule["id"],"schedule-id");path=sched_dir(root)/(sid+".json")
 if path.exists():raise FileExistsError(f"schedule exists: {sid}")
 if not schedule.get("target"):raise ValueError("schedule target is required")
 value={**object_meta("schedule",sid,int(schedule.get("version",1))),**schedule};atomic_write_json(path,value,overwrite=False);append_event(root,"scheduler",{"op":"register","schedule_id":sid});return value
def dispatch_plan(root:Path,sid:str)->dict:
 path=sched_dir(root)/(safe_id(sid,"schedule-id")+".json");value=read_json(path)
 result={"schedule_id":sid,"target":value["target"],"dispatch_id":f"dispatch-{sid}-{utc_now().replace(':','').replace('-','')}","status":"ready","created_at":utc_now()}
 hist=runtime_path(root,"scheduler","dispatch-history.jsonl",create_parent=True)
 with hist.open("a",encoding="utf-8") as h:h.write(json.dumps(result,ensure_ascii=False)+"\n")
 append_event(root,"scheduler",{"op":"dispatch_plan","schedule_id":sid});return result
def main(argv=None)->int:
 p=argparse.ArgumentParser(description="Schedule definitions and dispatch plans");s=p.add_subparsers(dest="cmd",required=True)
 a=s.add_parser("register");a.add_argument("--work-dir");a.add_argument("--file",required=True)
 a=s.add_parser("dispatch");a.add_argument("--work-dir");a.add_argument("--schedule-id",required=True)
 a=s.add_parser("list");a.add_argument("--work-dir")
 args=p.parse_args(argv)
 try:
  root=work_dir(args.work_dir,create=True)
  if args.cmd=="register":out=save(root,json.loads(Path(args.file).read_text(encoding="utf-8")))
  elif args.cmd=="dispatch":out=dispatch_plan(root,args.schedule_id)
  else:out=[read_json(p) for p in sorted(sched_dir(root).glob("*.json"))]
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError,json.JSONDecodeError) as exc:print(f"error: {exc}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

#!/usr/bin/env python3
"""Capability registry with conservative approval requirements."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from runtime_core import append_event,atomic_write_json,object_meta,read_json,runtime_path,safe_id,work_dir
RISKY={"delete","overwrite","external_send","login","network","write_original","move"}
def directory(root):return runtime_path(root,"capabilities",create_parent=True)
def register(root,data):
 for k in ("id","purpose","capabilities","inputs","outputs"): 
  if k not in data:raise ValueError(f"missing {k}")
 cid=safe_id(data["id"],"capability-id");path=directory(root)/(cid+".json")
 if path.exists():raise FileExistsError(cid)
 value={**object_meta("capability",cid,int(data.get("version",1))),**data,"id":cid};atomic_write_json(path,value,overwrite=False);return value
def select(root,capability,input_type=None,run_id=None,step_id=None):
 candidates=[]
 for p in sorted(directory(root).glob("*.json")):
  x=read_json(p)
  if capability not in x.get("capabilities",[]) or input_type and input_type not in x.get("inputs",[]):continue
  score=sum(float(x.get(k,.5))*w for k,w in (("accuracy_score",.3),("speed_score",.15),("format_fidelity_score",.2),("auditability_score",.2)))
  candidates.append((round(score,3),x))
 candidates.sort(key=lambda z:(-z[0],z[1]["id"]));selected=candidates[0][1] if candidates else None
 effects=set(selected.get("side_effects",[])) if selected else set();approval="required" if selected and (selected.get("network_required") or not effects.issubset({"read"}) or bool(effects&RISKY)) else "none"
 out={"capability":capability,"input_type":input_type,"run_id":run_id,"step_id":step_id,"selected":selected["id"] if selected else None,"candidates":[{"id":x["id"],"score":s} for s,x in candidates],"fallback":[x["id"] for _,x in candidates[1:3]],"approval":approval,"validation":selected.get("verification",[]) if selected else []}
 append_event(root,"capability",{"op":"select",**out});return out
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
 a=s.add_parser("register");a.add_argument("--work-dir");a.add_argument("--file",required=True)
 a=s.add_parser("list");a.add_argument("--work-dir")
 a=s.add_parser("select");a.add_argument("--work-dir");a.add_argument("--capability",required=True);a.add_argument("--input-type");a.add_argument("--run-id");a.add_argument("--step-id")
 a=p.parse_args(argv)
 try:
  root=work_dir(a.work_dir,create=True);out=register(root,json.loads(Path(a.file).read_text(encoding="utf-8"))) if a.cmd=="register" else [read_json(x) for x in sorted(directory(root).glob("*.json"))] if a.cmd=="list" else select(root,a.capability,a.input_type,a.run_id,a.step_id)
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

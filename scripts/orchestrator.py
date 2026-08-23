#!/usr/bin/env python3
"""Work-order DAG planner for task and deliverable nodes."""
from __future__ import annotations
import argparse,json,sys
from runtime_core import atomic_write_json,read_json,safe_id,utc_now,work_dir

def base(root,wid):return root/"work-orders"/safe_id(wid,"work-order-id")
def load(root,wid):
 b=base(root,wid)
 if not b.exists():raise FileNotFoundError(wid)
 return b,read_json(b/"dependency-graph.json"),read_json(b/"orchestration-state.json")
def add_node(root,wid,nid,kind):
 b,g,s=load(root,wid);nid=safe_id(nid,"node-id")
 if any(x["id"]==nid for x in g["nodes"]):raise FileExistsError(nid)
 g["nodes"].append({"id":nid,"kind":kind,"status":"pending"});s["nodes"][nid]={"status":"pending","kind":kind};atomic_write_json(b/"dependency-graph.json",g);atomic_write_json(b/"orchestration-state.json",s);return g
def cycle(g):
 adj={x["id"]:[] for x in g["nodes"]}
 for e in g["edges"]:
  if e.get("relation") in {"dependency","aggregation","conditional"}:adj[e["from"]].append(e["to"])
 seen=set();active=set()
 def visit(n):
  if n in active:return True
  if n in seen:return False
  active.add(n)
  if any(visit(x) for x in adj.get(n,[])):return True
  active.remove(n);seen.add(n);return False
 return any(visit(n) for n in adj)
def add_edge(root,wid,source,target,relation,condition=None):
 b,g,s=load(root,wid);ids={x["id"] for x in g["nodes"]}
 if source not in ids or target not in ids:raise ValueError("unknown node")
 if relation=="independent":return g
 edge={"from":source,"to":target,"relation":relation}
 if condition:edge["condition"]=condition
 g["edges"].append(edge)
 if cycle(g):g["edges"].pop();raise ValueError("dependency cycle")
 atomic_write_json(b/"dependency-graph.json",g);return g
def plan(root,wid):
 b,g,s=load(root,wid);states={n:s["nodes"].get(n,{"status":"pending"}).get("status","pending") for n in (x["id"] for x in g["nodes"])};incoming={n:[] for n in states}
 for e in g["edges"]:
  if e.get("relation")!="independent":incoming[e["to"]].append(e)
 ready=[];waiting=[];blocked=[];completed=[]
 for n,st in states.items():
  if st in {"completed","skipped"}:completed.append(n);continue
  deps=incoming[n]
  if any(states.get(e["from"]) in {"failed","blocked","cancelled"} for e in deps if e.get("relation")!="conditional"):blocked.append(n)
  elif any(e.get("relation")=="conditional" and not e.get("condition") for e in deps):waiting.append(n)
  elif all(states.get(e["from"]) in {"completed","skipped"} for e in deps if e.get("relation")!="conditional"):ready.append(n)
  else:waiting.append(n)
 s.update({"updated_at":utc_now(),"ready":ready,"waiting":waiting,"blocked":blocked,"completed":completed,"status":"completed" if states and len(completed)==len(states) else "running"});atomic_write_json(b/"orchestration-state.json",s);return {"ready":ready,"waiting":waiting,"blocked":blocked,"completed":completed}
def complete(root,wid,nid,status,run_id=None):
 b,g,s=load(root,wid)
 if nid not in s["nodes"]:raise ValueError("unknown node")
 if status=="completed" and run_id:
  # Task run completion is validated by runtime/run_state before orchestration receives it.
  state_path=root/"runtime"/"runs"/safe_id(run_id,"run-id")/"state.json"
  if not state_path.exists() or read_json(state_path).get("status")!="completed":raise ValueError("node run is not completed")
 s["nodes"][nid].update({"status":status,"run_id":run_id,"updated_at":utc_now()});atomic_write_json(b/"orchestration-state.json",s);return plan(root,wid)
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
 def c(x):x.add_argument("--work-dir")
 a=s.add_parser("add-node");c(a);a.add_argument("--work-order-id",required=True);a.add_argument("--node-id",required=True);a.add_argument("--kind",choices=["task","deliverable"],default="task")
 a=s.add_parser("add-edge");c(a);a.add_argument("--work-order-id",required=True);a.add_argument("--from",dest="source",required=True);a.add_argument("--to",dest="target",required=True);a.add_argument("--relation",choices=["independent","dependency","aggregation","conditional"],required=True);a.add_argument("--condition")
 a=s.add_parser("plan");c(a);a.add_argument("--work-order-id",required=True)
 a=s.add_parser("complete");c(a);a.add_argument("--work-order-id",required=True);a.add_argument("--node-id",required=True);a.add_argument("--status",default="completed");a.add_argument("--run-id")
 a=s.add_parser("dispatch");c(a);a.add_argument("--work-order-id",required=True)
 a=p.parse_args(argv)
 try:
  root=work_dir(a.work_dir,create=True)
  if a.cmd=="add-node":out=add_node(root,a.work_order_id,a.node_id,a.kind)
  elif a.cmd=="add-edge":out=add_edge(root,a.work_order_id,a.source,a.target,a.relation,a.condition)
  elif a.cmd=="plan":out=plan(root,a.work_order_id)
  elif a.cmd=="complete":out=complete(root,a.work_order_id,a.node_id,a.status,a.run_id)
  else:out={"work_order_id":a.work_order_id,"plan":plan(root,a.work_order_id),"dispatch":"host_scheduler_or_executor_required"}
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

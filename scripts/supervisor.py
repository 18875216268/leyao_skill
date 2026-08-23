#!/usr/bin/env python3
"""Cross-run supervisor: immutable events, proposals with cooldown, decision sidecars and summaries.

域分区（各司其职，见 references/memory-and-supervision.md 职责边界）：
- 监督域：propose / approve / decide —— 审批裁决（semantic/core 写入唯一审批权）
- 记忆工具域：record（写 episodic 事件）/ summary（记忆摘要）/ consolidate（固化）
两域共享事件存储结构（模式共用），裁决权与记录权不混（实例分开）。
"""
from __future__ import annotations
import argparse,hashlib,json,sys
from datetime import datetime,timedelta,timezone
from runtime_core import append_event,atomic_write_json,object_meta,read_json,runtime_path,safe_id,utc_now,work_dir

def event_dir(root,create=True):return runtime_path(root,"reflections","events",create_parent=create)
def proposal_dir(root):return runtime_path(root,"proposals",create_parent=True)
def _parse(value):return datetime.strptime(value,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

def record(root,profile,task_type,note,period="day",correction="",run_id="",success=True,task_id=""):
 profile=safe_id(profile,"profile-id",profile=True)
 stable={"profile":profile,"task_type":task_type,"note":note,"period":period,"correction":correction,"run_id":run_id,"success":success,"task_id":task_id}
 eid="e-"+hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest()[:16];p=event_dir(root)/(eid+".json")
 if p.exists():return read_json(p)
 value={**object_meta("reflection_event",eid),"event_id":eid,"profile_id":profile,"task_type":task_type,"period":period,"note":note,"correction":correction,"run_id":run_id,"success":success,"task_id":task_id}
 atomic_write_json(p,value,overwrite=False);append_event(root,"supervisor",{"op":"record","event_id":eid});return value

def events(root,profile=None,task_type=None):
 out=[]
 for p in sorted(event_dir(root,create=False).glob("e-*.json")) if event_dir(root,create=False).is_dir() else []:
  x=read_json(p)
  if (not profile or x.get("profile_id")==profile) and (not task_type or x.get("task_type")==task_type):out.append(x)
 return out

def propose(root,profile,target,change,risk,evidence):
 profile=safe_id(profile,"profile-id",profile=True)
 data={"profile_id":profile,"target":target,"change":change,"risk":risk,"evidence":evidence}
 pid="p-"+hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()[:16];p=proposal_dir(root)/(pid+".json")
 if p.exists():
  old=read_json(p)
  if old.get("status")=="rejected" and old.get("cooldown_until") and _parse(old["cooldown_until"])>datetime.now(timezone.utc):
   raise ValueError(f"proposal in cooldown until {old['cooldown_until']}")
  return old
 value={**object_meta("proposal",pid),**data,"proposal_id":pid,"status":"proposed","cooldown_until":None}
 atomic_write_json(p,value,overwrite=False);append_event(root,"supervisor",{"op":"propose","proposal_id":pid});return value

def decide(root,pid,approve,who,cooldown_days=30):
    p=proposal_dir(root)/(safe_id(pid,"proposal-id")+".json");x=read_json(p)
    if x["status"]!="proposed":raise ValueError("proposal not pending")
    # Evidence stays immutable in the proposal file; each decision is an appended versioned sidecar.
    x["status"]="approved" if approve else "rejected";x["decided_at"]=utc_now();x["decided_by"]=who
    if not approve:x["cooldown_until"]=(datetime.now(timezone.utc)+timedelta(days=cooldown_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    atomic_write_json(p,x)
    d=p.parent/"decisions";d.mkdir(exist_ok=True)
    sidecar={"proposal_id":pid,"status":x["status"],"decided_at":x["decided_at"],"decided_by":who,"version":x["version"]}
    atomic_write_json(d/f"{pid}-v{x['version']}.json",sidecar,overwrite=False)
    append_event(root,"supervisor",{"op":"approve" if approve else "reject","proposal_id":pid})
    out=x
    if who=="auto" and approve:
        # O3 自动审批审计：统计 work-dir 内 auto 批准总数，超阈值建议人工抽查（防自动审批权滥用）
        cnt=0
        for sp in d.glob("*-v*.json"):
            sx=read_json(sp)
            if sx.get("decided_by")=="auto" and sx.get("status")=="approved":cnt+=1
        out={**x,"auto_count":cnt,"suggest_review":cnt>=10}
    return out

def summarize(root,profile,dry=False):
 ev=events(root,profile);counts={}
 for x in ev:counts[x.get("task_type","unknown")]=counts.get(x.get("task_type","unknown"),0)+1
 out={**object_meta("memory_summary",safe_id(profile,"profile-id",profile=True),1),"profile_id":profile,"event_count":len(ev),"task_type_counts":counts,"generated_at":utc_now()}
 if not dry:
  target=runtime_path(root,"memory","core",safe_id(profile,"profile-id",profile=True)+".summary.json",create_parent=True)
  version=int(read_json(target).get("version",0))+1 if target.exists() else 1;out["version"]=version
  atomic_write_json(target,out);append_event(root,"supervisor",{"op":"summary","profile_id":profile,"version":version})
 return out

def consolidate(root,profile,dry=False,propose_habits=False):
 """固化（记忆工具域 · P0）：episodic 聚合 + semantic 衰减/冲突检测 → 固化报告。

 确定性规则（无 LLM，可审计）：
  习惯候选 = 高频 task_type（>=3 次）；--propose-habits 时 >=5 次的生成 L1/L2 提案（复用 propose+审批）。
 时间衰减/冲突基于 semantic 条目 created_at（memory.py put 已带时间戳）。
 """
 from collections import Counter
 profile=safe_id(profile,"profile-id",profile=True)
 ev=events(root,profile);types=Counter(x.get("task_type","unknown") for x in ev)
 corrections=[x.get("correction") for x in ev if x.get("correction")]
 now=datetime.now(timezone.utc);stale=[];conflicts=[];by_key={}
 sem_p=runtime_path(root,"memory","semantic",profile+".json",create_parent=False)
 if sem_p.exists():
  for e in read_json(sem_p).get("entries",[]):
   ts=_parse(e.get("created_at")) if e.get("created_at") else None
   if ts and (now-ts).days>180:stale.append({"key":e.get("key"),"age_days":(now-ts).days})
   by_key.setdefault(e.get("key"),[]).append(e.get("value"))
 conflicts=[{"key":k,"variants":len(v)} for k,v in by_key.items() if len(v)>1]
 habits=[];corr_by_type=Counter(x.get("task_type","unknown") for x in ev if x.get("correction"))
 for t,c in types.most_common(8):
  if c>=3 or corr_by_type.get(t,0)>=2:
   habits.append({"task_type":t,"count":c,"priority":"high" if corr_by_type.get(t,0)>=2 else "normal"})
 out={**object_meta("memory_consolidation",profile,1),"profile_id":profile,"event_count":len(ev),
      "task_type_counts":dict(types),"corrections":len(corrections),"correction_driven":len(corr_by_type),
      "stale_candidates":stale[:10],"conflicts":conflicts[:10],"habit_candidates":habits,
      "proposals":[],"generated_at":utc_now()}
 if propose_habits:
  for h in habits:
   if h["count"]>=5 or h["priority"]=="high":
    # 习惯 = 用户稳定偏好 → core 分区（habit: 前缀属 core，与 semantic 区分）；target 必须匹配写入 scope
    pid=propose(root,profile,f"core:{profile}",f"habit:{h['task_type']}","low",[])["proposal_id"]
    out["proposals"].append({"task_type":h["task_type"],"proposal_id":pid,"risk":"low","priority":h["priority"]})
 if not dry:
  target=runtime_path(root,"memory","core",profile+".consolidation.json",create_parent=True)
  version=int(read_json(target).get("version",0))+1 if target.exists() else 1;out["version"]=version
  atomic_write_json(target,out);append_event(root,"supervisor",{"op":"consolidate","profile_id":profile,"version":version})
 return out

def assess(root,profile):
 """评估报告（记忆工具域）：聚合 events + consolidation → 结构化评估基础。

 评估本身仍由 AI 执行（监督评估环），本命令提供结构化输入：
 事件统计 / 成功率 / 质量信号（高频、纠正、失败）/ 诊断候选（冲突、陈旧）。
 """
 from collections import Counter
 profile=safe_id(profile,"profile-id",profile=True)
 evs=events(root,profile)
 types=Counter(x.get("task_type","unknown") for x in evs)
 corr=[x for x in evs if x.get("correction")]
 fails=[x for x in evs if not x.get("success")]
 corr_types=Counter(x.get("task_type","unknown") for x in corr)
 signals=[]
 for t,c in types.most_common(6):
  if c>=3 or corr_types.get(t,0)>=2:
   signals.append({"type":"high_frequency","task_type":t,"count":c,"corrections":corr_types.get(t,0)})
 for x in corr[:8]:
  signals.append({"type":"correction","task_type":x.get("task_type"),"correction":x.get("correction")})
 for x in fails[:8]:
  signals.append({"type":"failure","task_type":x.get("task_type"),"note":x.get("note")})
 con_p=runtime_path(root,"memory","core",profile+".consolidation.json",create_parent=False)
 con=read_json(con_p) if con_p.exists() else None
 diag=[]
 if con and con.get("conflicts"):
  for c in con["conflicts"][:5]:diag.append({"type":"conflict","key":c["key"],"variants":c["variants"]})
 if con and con.get("stale_candidates"):
  diag.append({"type":"stale","count":len(con["stale_candidates"])})
 out={**object_meta("assess_report",profile,1),"profile_id":profile,"event_count":len(evs),
      "success_rate":round(sum(1 for x in evs if x.get("success"))/len(evs),3) if evs else None,
      "task_type_counts":dict(types),"corrections":len(corr),"fails":len(fails),
      "quality_signals":signals[:12],"diag_candidates":diag[:8],"generated_at":utc_now()}
 return out

def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
 a=s.add_parser("record");a.add_argument("--work-dir");a.add_argument("--profile",default="default");a.add_argument("--type",required=True);a.add_argument("--note",required=True);a.add_argument("--period",default="day");a.add_argument("--correction",default="");a.add_argument("--run-id",default="");a.add_argument("--task-id",default="");a.add_argument("--fail",action="store_true")
 a=s.add_parser("propose");a.add_argument("--work-dir");a.add_argument("--profile",default="default");a.add_argument("--target",required=True);a.add_argument("--change",required=True);a.add_argument("--risk",choices=["low","medium","high"],required=True);a.add_argument("--evidence",action="append",default=[])
 for cmd in ("approve","reject"):
  a=s.add_parser(cmd);a.add_argument("--work-dir");a.add_argument("proposal_id");a.add_argument("--who",default="user");a.add_argument("--cooldown-days",type=int,default=30)
 a=s.add_parser("summary");a.add_argument("--work-dir");a.add_argument("--profile",default="default");a.add_argument("--dry-run",action="store_true")
 a=s.add_parser("events");a.add_argument("--work-dir");a.add_argument("--profile",default=None);a.add_argument("--task-type",default=None)
 a=s.add_parser("consolidate");a.add_argument("--work-dir");a.add_argument("--profile",default="default");a.add_argument("--dry-run",action="store_true");a.add_argument("--propose-habits",action="store_true",help="高频习惯候选生成 L1/L2 提案（审批后 memory.put）")
 a=s.add_parser("assess");a.add_argument("--work-dir");a.add_argument("--profile",default="default");a.add_argument("--task-type",default=None)
 a=p.parse_args(argv)
 try:
  root=work_dir(a.work_dir,create=True)
  if a.cmd=="record":out=record(root,a.profile,a.type,a.note,a.period,a.correction,a.run_id,not a.fail,a.task_id)
  elif a.cmd=="propose":out=propose(root,a.profile,a.target,a.change,a.risk,a.evidence)
  elif a.cmd in {"approve","reject"}:out=decide(root,a.proposal_id,a.cmd=="approve",a.who,a.cooldown_days)
  elif a.cmd=="consolidate":out=consolidate(root,a.profile,a.dry_run,a.propose_habits)
  elif a.cmd=="events":out=events(root,a.profile,a.task_type)
  elif a.cmd=="assess":out=assess(root,a.profile)
  else:out=summarize(root,a.profile,a.dry_run)
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

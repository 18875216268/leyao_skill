#!/usr/bin/env python3
"""Content-addressed local cache with explicit bypass and atomic metadata."""
from __future__ import annotations
import argparse,json,sys
from runtime_core import append_event,atomic_write_json,cache_key as make_cache_key,checksum,object_meta,runtime_path,safe_id,utc_now,work_dir
RISKY={"delete","overwrite","external_send","login","network","write_original","move"}

def root_dir(root):return runtime_path(root,"runtime","cache",create_parent=True)
def entry_path(root,key):return root_dir(root)/"entries"/(key.removeprefix("sha256:")+".json")
def payload_path(root,key):return root_dir(root)/"payloads"/(key.removeprefix("sha256:")+".json")
def bypass_reason(sensitivity="internal",side_effects=None,approval_required=False,force_refresh=False):
 if force_refresh:return "force_refresh"
 if sensitivity!="internal":return "sensitive"
 effects=set(side_effects or [])
 if approval_required or effects & RISKY:return "approval_required_or_side_effect"
 return None
def make_key(operation,producer,inputs,parameters,context_hash=None,policy_version="1"):return make_cache_key(operation,producer,inputs,parameters,context_hash,policy_version)
def lookup(root,key,sensitivity="internal",side_effects=None,approval_required=False,force_refresh=False):
 reason=bypass_reason(sensitivity,side_effects,approval_required,force_refresh)
 if reason:return {"status":"bypass","reason":reason,"cache_key":key}
 ep=entry_path(root,key);pp=payload_path(root,key)
 if not ep.exists() or not pp.exists():return {"status":"miss","cache_key":key}
 entry=json.loads(ep.read_text(encoding="utf-8"));payload=json.loads(pp.read_text(encoding="utf-8"))
 if entry.get("status")!="ready" or entry.get("payload",{}).get("checksum")!=checksum(pp):return {"status":"miss","reason":"invalid_payload","cache_key":key}
 entry["usage_count"]=int(entry.get("usage_count",0))+1;entry["last_accessed_at"]=utc_now();atomic_write_json(ep,entry)
 append_event(root,"cache",{"op":"hit","cache_key":key,"namespace":entry.get("namespace")});return {"status":"hit","cache_key":key,"payload":payload,"entry":entry}
def store(root,namespace,key,producer,inputs,parameters,payload,context_hash=None,confidence=.0,sensitivity="internal",side_effects=None,approval_required=False):
 reason=bypass_reason(sensitivity,side_effects,approval_required)
 if reason:return {"status":"bypass","reason":reason,"cache_key":key}
 ep=entry_path(root,key);pp=payload_path(root,key);pp.parent.mkdir(parents=True,exist_ok=True);ep.parent.mkdir(parents=True,exist_ok=True)
 if ep.exists():return {"status":"existing","cache_key":key,"entry":json.loads(ep.read_text(encoding="utf-8"))}
 atomic_write_json(pp,payload,overwrite=False)
 payload_ref=str(pp.resolve().relative_to(root.resolve())).replace("\\","/")
 value={**object_meta("cache_entry",safe_id("cache-"+key.removeprefix("sha256:")[:24],"cache-id")),"cache_key":key,"namespace":namespace,"producer":producer,"inputs":inputs,"parameters":parameters,"context_hash":context_hash,"status":"ready","payload":{"path":payload_ref,"checksum":checksum(pp)},"confidence":confidence,"sensitivity":sensitivity,"usage_count":0,"last_accessed_at":None,"created_at":utc_now(),"evictable":True}
 atomic_write_json(ep,value,overwrite=False);append_event(root,"cache",{"op":"store","cache_key":key,"namespace":namespace});return {"status":"stored","cache_key":key,"entry":value}
def invalidate(root,key,reason):
 ep=entry_path(root,key)
 if not ep.exists():raise FileNotFoundError(key)
 value=json.loads(ep.read_text(encoding="utf-8"));value["status"]="invalid";value["invalidated_at"]=utc_now();value["invalidated_reason"]=reason;atomic_write_json(ep,value);append_event(root,"cache",{"op":"invalidate","cache_key":key,"reason":reason});return value
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
 a=s.add_parser("key");a.add_argument("--operation",required=True);a.add_argument("--producer",required=True);a.add_argument("--inputs",default="[]");a.add_argument("--parameters",default="{}");a.add_argument("--context-hash");a.add_argument("--policy-version",default="1")
 a=s.add_parser("store");a.add_argument("--work-dir");a.add_argument("--namespace",required=True);a.add_argument("--key",required=True);a.add_argument("--producer",required=True);a.add_argument("--inputs",default="[]");a.add_argument("--parameters",default="{}");a.add_argument("--payload",required=True);a.add_argument("--context-hash");a.add_argument("--confidence",type=float,default=0);a.add_argument("--sensitivity",default="internal");a.add_argument("--side-effect",action="append",default=[]);a.add_argument("--approval-required",action="store_true")
 a=s.add_parser("lookup");a.add_argument("--work-dir");a.add_argument("--key",required=True);a.add_argument("--sensitivity",default="internal");a.add_argument("--side-effect",action="append",default=[]);a.add_argument("--approval-required",action="store_true");a.add_argument("--force-refresh",action="store_true")
 a=s.add_parser("invalidate");a.add_argument("--work-dir");a.add_argument("--key",required=True);a.add_argument("--reason",required=True)
 args=p.parse_args(argv)
 try:
  if args.cmd=="key":out={"cache_key":make_key(args.operation,args.producer,json.loads(args.inputs),json.loads(args.parameters),args.context_hash,args.policy_version)}
  else:
   root=work_dir(args.work_dir,create=True)
   if args.cmd=="store":out=store(root,args.namespace,args.key,args.producer,json.loads(args.inputs),json.loads(args.parameters),json.loads(args.payload),args.context_hash,args.confidence,args.sensitivity,args.side_effect,args.approval_required)
   elif args.cmd=="lookup":out=lookup(root,args.key,args.sensitivity,args.side_effect,args.approval_required,args.force_refresh)
   else:out=invalidate(root,args.key,args.reason)
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (OSError,ValueError,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only structural validator for the skill package."""
from __future__ import annotations
import argparse, ast, json, re
from pathlib import Path

def frontmatter(path: Path):
    errors=[]; text=path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]: return ["invalid SKILL.md frontmatter"]
    end=text.find("\n---\n",4); fields={}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            key,val=line.split(":",1);fields[key.strip()]=val.strip().strip('"')
    if fields.get("name")!=path.parent.name:errors.append("frontmatter name must match parent directory")
    if not re.fullmatch(r"[a-z0-9]+(?:[-_][a-z0-9]+)*",fields.get("name","")):errors.append("invalid skill name")
    if not fields.get("description"):errors.append("description is missing")
    if not fields.get("version"):errors.append("version is missing")
    if len(text.splitlines())>500:errors.append("SKILL.md exceeds 500 lines")
    return errors

def schema_errors(path):
    try:value=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:return [f"{path.name}: invalid JSON: {exc}"]
    errors=[]
    if not isinstance(value,dict):errors.append(f"{path.name}: schema must be object")
    elif not value.get("title"):errors.append(f"{path.name}: title missing")
    return errors

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument("--root",default=str(Path(__file__).resolve().parents[1]));args=parser.parse_args(argv)
    root=Path(args.root).resolve();errors=[];errors+=frontmatter(root/"SKILL.md")
    for path in (root/"schemas").glob("*.json"):errors+=schema_errors(path)
    for path in (root/"templates").glob("*.json"):
        try:
            if not isinstance(json.loads(path.read_text(encoding="utf-8")),dict):errors.append(f"{path.name}: template must be object")
        except json.JSONDecodeError as exc:errors.append(f"{path.name}: invalid JSON: {exc}")
    if list((root/"templates").glob("*.yaml")):errors.append("YAML templates are not allowed")
    for path in (root/"scripts").glob("*.py"):
        try:ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
        except SyntaxError as exc:errors.append(f"{path.name}: {exc}")
    for path in (root/"references").glob("*.md"):
        for ref in re.findall(r"\[[^\]]+\]\(([^)]+)\)",path.read_text(encoding="utf-8")):
            if not ref.startswith("http") and not ((root/ref).exists() or (root/"references"/ref).exists()):errors.append(f"{path.name}: missing reference {ref}")
    # 环境目录豁免：.workbuddy（WorkBuddy 记忆/规划）、.wrangler（CF 部署登录配置）非 skill 包内容
    allowed={"SKILL.md","references","schemas","templates","scripts","tests","brf","capabilities","self_update.json",".workbuddy",".wrangler"}
    for path in root.iterdir():
        if path.name not in allowed:errors.append(f"unexpected package entry: {path.name}")
    if errors:
        print("VALIDATION FAILED\n"+"\n".join("- "+x for x in errors));return 1
    print("VALIDATION PASSED");return 0
if __name__=="__main__":raise SystemExit(main())

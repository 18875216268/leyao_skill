"""BRF 公共工具：统一重复机制（单一真源）。

集中 4 类曾多处重复的基础能力，各模块 import 复用：
  clean_q            意图/语气词剥离（resolve/k1_memory/dict/guide/tools_discovery）
  run_py             subprocess 跑 python 脚本并解析 JSON（brf.py learn/k1_memory/cli）
  find_dr_scripts    向上遍历定位主 skill scripts（brf.py/k1_memory）
  relevance_2char    2 字滑窗相关性（guide/tools_discovery 工具匹配）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

STOPWORDS = ("怎么做", "怎么分析", "怎么算", "如何", "怎么", "是什么", "什么", "是", "的",
             "了", "吗", "呢", "请", "一下", "查", "搜", "找", "看看", "有哪些", "多少", "？", "?")


def clean_q(q: str) -> str:
    """剥离意图/语气词，提取匹配关键词（如「怎么做ABC分析」→「ABC分析」）。"""
    q = (q or "").strip()
    for s in STOPWORDS:
        q = q.replace(s, "")
    return q.strip()


def run_py(script: Path, *args, timeout: int = 60) -> dict | None:
    """运行 python 脚本并解析 JSON：整体优先，失败逐行（兼容 pretty-print 与流式）。"""
    try:
        r = subprocess.run([sys.executable, str(script), *args],
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = r.stdout or ""
    out = None
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        for line in reversed(text.strip().splitlines()):
            try:
                out = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if out is None:
        return {"ok": False, "error": "UNPARSEABLE", "exit_code": r.returncode,
                "stdout": text[:400], "stderr": (r.stderr or "")[:200]}
    if isinstance(out, dict):
        out["exit_code"] = r.returncode
    return out


def find_dr_scripts(here: Path, require: tuple[str, ...] = ("memory.py", "cache.py", "capabilities.py")) -> Path | None:
    """向上遍历定位主 skill scripts 目录（含任一指定脚本），插件可移动。"""
    for anc in here.parents:
        scripts = anc / "scripts"
        if scripts.is_dir() and any((scripts / n).exists() for n in require):
            return scripts
    return None


def relevance_2char(q: str, blob: str) -> bool:
    """2 字滑窗相关性：问题关键词任一 2 字片段命中目标文本（工具/资产匹配）。"""
    if not q:
        return True
    if q in blob:
        return True
    for i in range(len(q) - 1):
        if q[i:i + 2] in blob:
            return True
    return False

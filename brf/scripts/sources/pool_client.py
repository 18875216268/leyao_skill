#!/usr/bin/env python3
"""公共知识池客户端（K2.5 群体层）：读写 CF Workers + D1 池。

池 = 共同智能大脑：任何 skill 使用者的业务经验/思维/方法沉淀于此，跨使用者共享进化。

  query()  读池（K2 未命中 → 查群体经验，高价值优先；hit_count 由 Worker GET 自动累加）
  submit() 写池（learn 自动沉淀成功后上传，走三层闸 + 帕累托）
  inject() 写注入库（仅用户显式要求注入，authority 权威）
  record_adopt() 价值信号（learn 借鉴池条目后上报采纳）

端点与共享 Token（skill 使用者共用；写需 Token 防匿名垃圾，读公开）。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

POOL_URL = "https://lyzsk.cfdaili.top/api/pool"   # 同域正式端点（Pages Functions，静态+动态共存）
POOL_TOKEN = "brf-pool-2026-shared"   # 共享贡献 token（skill 内置，写接口校验）


def _request(method: str, path: str = "", body: dict | None = None, token: str | None = None,
             retries: int = 3, timeout: int = 30):
    """HTTP 请求：优先 requests（连接池复用端口，规避 Windows 端口耗尽）；回退 urllib。

    timeout 供反馈类轻量调用（record_adopt）缩短等待，避免阻塞主流程。
    """
    url = POOL_URL + path
    headers = {"User-Agent": "Mozilla/5.0 knowledge-hub/0.3", "Content-Type": "application/json"}
    if token:
        headers["X-Contributor-Token"] = token
    last = {"ok": False, "error": "NETWORK", "detail": "no attempt"}
    try:
        import requests
        for attempt in range(retries):
            try:
                r = requests.request(method, url, json=body, headers=headers, timeout=timeout)
                if r.status_code >= 400 and r.status_code != 202:
                    return {"ok": False, "error": f"HTTP {r.status_code}", "body": r.text[:200]}
                return r.json() if r.text.strip() else {"ok": True}
            except Exception as e:
                last = {"ok": False, "error": "NETWORK", "detail": str(e)[:120]}
                if attempt < retries - 1:
                    import time
                    time.sleep(1 + attempt)
        return last
    except ImportError:
        pass  # 无 requests → 回退 urllib
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {"ok": True}
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8")) or {"ok": False, "error": f"HTTP {e.code}"}
            except Exception:
                return {"ok": False, "error": f"HTTP {e.code}"}
        except Exception as e:
            last = {"ok": False, "error": "NETWORK", "detail": str(e)[:120]}
            if attempt < retries - 1:
                import time
                time.sleep(1 + attempt)
    return last


def query(category: str | None = None, q: str | None = None, trust: str | None = None,
          limit: int = 5, kind: str | None = None, tier: str | None = None) -> dict:
    """读池：按类别/关键词/信任级/kind/tier 查群体经验（高价值优先）。

    tier 区分来源：session（进化沉淀 reference）| inject（用户注入 authority）。
    """
    params = []
    if category:
        params.append(f"category={category}")
    if q:
        params.append(f"q={urllib.parse.quote(q)}")
    if trust:
        params.append(f"trust={trust}")
    if kind:
        params.append(f"kind={kind}")
    if tier:
        params.append(f"tier={tier}")
    params.append(f"limit={limit}")
    return _request("GET", "?" + "&".join(params))


def inject(title: str, content: str, category: str = "experience",
           kind: str = "fact", quality_score: float = 0.9,
           contributor: str = "user", distill_type: str | None = None) -> dict:
    """写注入库：仅用户显式要求注入时调用（authority 权威）。

    与 submit 的区别：tier=inject + trust=authority，不经 AI 蒸馏门槛；
    调用方（AI）必须在用户明确要求注入时才调用，不得自动触发。
    """
    return _request("POST", "/inject", {
        "title": title, "content": content, "category": category,
        "kind": kind, "quality_score": quality_score,
        "contributor": contributor, "distill_type": distill_type,
    }, token=POOL_TOKEN)


def submit(title: str, content: str, category: str = "experience",
           distill_type: str = "lesson", trust: str = "reference",
           quality_score: float = 0.5, contributor: str = "skill-user",
           kind: str = "fact") -> dict:
    """写池：贡献条目（三层闸 + 帕累托，Worker 端执行）。

    kind 对齐本地 semantic 分层：fact（事实口径）| procedure（工作流/工具模式），
    供池侧程序环（kind=procedure 独立检索）与事实检索区分。
    """
    return _request("POST", "", {
        "title": title, "content": content, "category": category,
        "distill_type": distill_type, "trust": trust,
        "quality_score": quality_score, "contributor": contributor,
        "kind": kind,
    }, token=POOL_TOKEN)


def record_adopt(pool_id: str) -> dict:
    """价值信号：显式采纳上报（需 token，防伪造采纳）。

    供 learn 借鉴池条目后调用；响应携带最新 hit/adopt 计数，供 evolve value 维度消费。
    失败静默，不阻塞沉淀。
    """
    if not pool_id:
        return {"ok": False, "error": "MISSING_ID"}
    return _request("POST", "/adopt", {"id": pool_id}, token=POOL_TOKEN, timeout=5)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "query"
    if cmd == "query":
        print(json.dumps(query(q=sys.argv[2] if len(sys.argv) > 2 else None,
                               category=sys.argv[3] if len(sys.argv) > 3 else None),
                         ensure_ascii=False, indent=2))
    elif cmd == "submit":
        print(json.dumps(submit(sys.argv[2], sys.argv[3], trust=sys.argv[4] if len(sys.argv) > 4 else "reference"),
                         ensure_ascii=False, indent=2))

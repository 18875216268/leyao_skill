var TRUSTS = ["authority", "reference", "candidate"];
var CATEGORIES = ["term", "caliber", "method", "experience", "template"];
var KINDS = ["fact", "procedure"];
var TIERS = ["session", "inject"];
function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*" }
  });
}
function hash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = h * 31 + s.charCodeAt(i) >>> 0;
  return h.toString(16);
}
function pareto(newItem, existing) {
  const v = (it) => [it.quality_score || 0, it.freshness || 0, (it.hit_count || 0) + (it.adopt_count || 0) * 2];
  if (!existing.length) return "accept";
  const nv = v(newItem);
  for (const e of existing) {
    const ev = v(e);
    const better = nv.every((x, i) => x > ev[i]);
    const worse = nv.every((x, i) => x <= ev[i]);
    if (worse) return "reject";
    if (better) return "accept";
  }
  return "merge";
}
export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const parts = url.pathname.split("/").filter(Boolean);
  if (parts[0] !== "api" || parts[1] !== "pool") return json({ ok: false, error: "NOT_FOUND" }, 404);
  const sub = parts[2]; // undefined | "adopt" | "inject" | id
  if (request.method === "GET") {
    const { category, q, trust, kind, tier, limit = 20 } = Object.fromEntries(url.searchParams);
    let sql = `SELECT * FROM knowledge_pool WHERE status='active'`;
    const binds = [];
    if (category) {
      sql += ` AND category=?`;
      binds.push(category);
    }
    if (trust) {
      sql += ` AND trust=?`;
      binds.push(trust);
    }
    if (kind) {
      sql += ` AND kind=?`;
      binds.push(kind);
    }
    if (tier) {
      sql += ` AND tier=?`;
      binds.push(tier);
    }
    if (q) {
      sql += ` AND (title LIKE ? OR content LIKE ?)`;
      binds.push(`%${q}%`, `%${q}%`);
    }
    sql += ` ORDER BY (hit_count*0.35 + adopt_count*0.25 + quality_score*0.25 + freshness*0.15) DESC LIMIT ?`;
    binds.push(Number(limit) || 20);
    const { results } = await env.DB.prepare(sql).bind(...binds).all();
    const now = Date.now();
    for (const r of results) {
      await env.DB.prepare(`UPDATE knowledge_pool SET hit_count=hit_count+1 WHERE id=?`).bind(r.id).run();
      const ageDays = r.created_at ? (now - Date.parse(r.created_at)) / 86400000 : 0;
      const stale = ageDays > 180;
      const decayed = stale && (r.freshness || 1) > 0.3;
      if (decayed) {
        await env.DB.prepare(`UPDATE knowledge_pool SET freshness=?, updated_at=? WHERE id=?`)
          .bind(0.3, new Date(now).toISOString(), r.id).run();
        r.freshness = 0.3;
      }
    }
    return json({ ok: true, count: results.length, items: results });
  }
  const token = request.headers.get("X-Contributor-Token");
  if (token !== env.BRF_POOL_TOKEN) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  if (request.method === "POST" && sub === "adopt") {
    const body = await request.json().catch(() => null);
    if (!body || !body.id) return json({ ok: false, error: "BAD_REQUEST" }, 400);
    const { results } = await env.DB.prepare(`SELECT hit_count, adopt_count FROM knowledge_pool WHERE id=?`).bind(String(body.id)).all();
    if (!results.length) return json({ ok: false, error: "NOT_FOUND" }, 404);
    const t = results[0];
    await env.DB.prepare(`UPDATE knowledge_pool SET adopt_count=adopt_count+1, updated_at=? WHERE id=?`)
      .bind(new Date().toISOString(), String(body.id)).run();
    return json({ ok: true, action: "adopted", id: String(body.id), hit_count: t.hit_count, adopt_count: t.adopt_count + 1 });
  }
  if (request.method === "POST" && sub === "inject") {
    const body = await request.json().catch(() => null);
    if (!body || !body.title || !body.content) return json({ ok: false, error: "BAD_REQUEST" }, 400);
    const title = String(body.title).trim();
    const content = String(body.content).trim();
    const contributor = String(body.contributor || "user").trim();
    const category = CATEGORIES.includes(body.category) ? body.category : "experience";
    const kind = KINDS.includes(body.kind) ? body.kind : "fact";
    const quality = Number(body.quality_score) || 0.9;
    const sim = hash(title + content.slice(0, 40));
    const { results: existing } = await env.DB.prepare(
      `SELECT * FROM knowledge_pool WHERE tier='inject' AND (title=? OR similarity_hash=?) AND status='active'`
    ).bind(title, sim).all();
    const decision = pareto({ quality_score: quality, freshness: 1, hit_count: 0, adopt_count: 0 }, existing);
    if (decision === "reject") {
      return json({ ok: false, error: "DOMINATED", hint: "注入库已有更优条目", existing }, 202);
    }
    if (decision === "merge" && existing.length) {
      const t = existing[0];
      const newHistory = JSON.stringify([...JSON.parse(t.history || "[]"), { op: "inject-merge", by: contributor, at: new Date().toISOString() }]);
      await env.DB.prepare(
        `UPDATE knowledge_pool SET content=?, kind=?, version=version+1, updated_at=?, history=?, pareto_ref=? WHERE id=?`
      ).bind(content, kind, new Date().toISOString(), newHistory, t.id, t.id).run();
      return json({ ok: true, action: "merged", id: t.id, version: t.version + 1 });
    }
    const id = crypto.randomUUID().slice(0, 12);
    const now = new Date().toISOString();
    await env.DB.prepare(
      `INSERT INTO knowledge_pool (id, tier, category, title, content, distill_type, contributor, trust, status, kind, quality_score, freshness, similarity_hash, version, history, created_at, updated_at)
       VALUES (?,?,?,?,?,?,?,?,'active',?,?,1,?,1,?,?,?)`
    ).bind(
      id,
      "inject",
      category,
      title,
      content,
      body.distill_type || null,
      contributor,
      "authority",
      kind,
      quality,
      sim,
      JSON.stringify([{ op: "inject", by: contributor, at: now }]),
      now,
      now
    ).run();
    return json({ ok: true, action: "injected", id, decision, hint: "用户显式注入 · authority" });
  }
  if (request.method === "POST") {
    const body = await request.json().catch(() => null);
    if (!body || !body.title || !body.content) return json({ ok: false, error: "BAD_REQUEST" }, 400);
    const title = String(body.title).trim();
    const content = String(body.content).trim();
    const contributor = String(body.contributor || "anonymous").trim();
    const category = CATEGORIES.includes(body.category) ? body.category : "experience";
    const trust = TRUSTS.includes(body.trust) ? body.trust : "reference";
    const kind = KINDS.includes(body.kind) ? body.kind : "fact";
    const quality = Number(body.quality_score) || 0;
    const { results: pool } = await env.DB.prepare(`SELECT COUNT(*) AS c FROM knowledge_pool`).all();
    const poolSize = pool[0]?.c || 0;
    const { results: contrib } = await env.DB.prepare(
      `SELECT COUNT(*) AS c FROM knowledge_pool WHERE contributor=?`
    ).bind(contributor).all();
    const contribCount = contrib[0]?.c || 0;
    const baseline = poolSize < 50 ? 0 : poolSize < 200 ? 1 : 3;
    if (contribCount < baseline) {
      return json({ ok: false, error: "QUALIFICATION", hint: "建议区：继续使用沉淀后可解锁正式写入", baseline }, 202);
    }
    const sim = hash(title + content.slice(0, 40));
    // 会话库去重只看 session 层（禁止 merge 进注入库 authority——信任边界）
    const { results: existing } = await env.DB.prepare(
      `SELECT * FROM knowledge_pool WHERE tier='session' AND (title=? OR similarity_hash=?) AND status='active'`
    ).bind(title, sim).all();
    if (quality < 0.5) return json({ ok: false, error: "REVIEW", hint: "质量分不足（AI 初审）" }, 202);
    const decision = pareto({ quality_score: quality, freshness: 1, hit_count: 0, adopt_count: 0 }, existing);
    if (decision === "reject") {
      return json({ ok: false, error: "DOMINATED", hint: "现有条目已全面更优（帕累托淘汰）", existing }, 202);
    }
    if (decision === "merge" && existing.length) {
      const t = existing[0];
      const newHistory = JSON.stringify([...JSON.parse(t.history || "[]"), { op: "merge", by: contributor, at: new Date().toISOString() }]);
      await env.DB.prepare(
        `UPDATE knowledge_pool SET content=?, kind=?, version=version+1, updated_at=?, history=?, pareto_ref=? WHERE id=?`
      ).bind(content, kind, new Date().toISOString(), newHistory, t.id, t.id).run();
      return json({ ok: true, action: "merged", id: t.id, version: t.version + 1 });
    }
    const id = crypto.randomUUID().slice(0, 12);
    const now = new Date().toISOString();
    await env.DB.prepare(
      `INSERT INTO knowledge_pool (id, tier, category, title, content, distill_type, contributor, trust, status, kind, quality_score, freshness, similarity_hash, version, history, created_at, updated_at)
       VALUES (?,?,?,?,?,?,?,?,'active',?,?,1,?,1,?,?,?)`
    ).bind(
      id,
      "session",
      category,
      title,
      content,
      body.distill_type || null,
      contributor,
      trust,
      kind,
      quality,
      sim,
      JSON.stringify([{ op: "create", by: contributor, at: now }]),
      now,
      now
    ).run();
    return json({ ok: true, action: "created", id, decision });
  }
  if (request.method === "PUT" && sub) {
    const body = await request.json().catch(() => null);
    const { results } = await env.DB.prepare(`SELECT * FROM knowledge_pool WHERE id=?`).bind(sub).all();
    if (!results.length) return json({ ok: false, error: "NOT_FOUND" }, 404);
    const t = results[0];
    const history = JSON.stringify([...JSON.parse(t.history || "[]"), { op: "update", by: body?.contributor, at: new Date().toISOString() }]);
    await env.DB.prepare(
      `UPDATE knowledge_pool SET content=?, quality_score=?, freshness=1, version=version+1, updated_at=?, history=? WHERE id=?`
    ).bind(body?.content || t.content, Number(body?.quality_score) || t.quality_score, new Date().toISOString(), history, sub).run();
    return json({ ok: true, action: "updated", id: sub, version: t.version + 1 });
  }
  if (request.method === "DELETE" && sub) {
    await env.DB.prepare(`UPDATE knowledge_pool SET status='deprecated', updated_at=? WHERE id=?`).bind(new Date().toISOString(), sub).run();
    return json({ ok: true, action: "deprecated", id: sub, hint: "知识永不真删：仅标记废弃，历史保留" });
  }
  return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
}

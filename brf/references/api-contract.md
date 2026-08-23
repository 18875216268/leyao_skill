# API 契约（ask 协议与双源路由）

## 一、ask() 协议

```
请求: ask(need_type, question, context=None)
  need_type ∈ {term, caliber, tool, data, template, process}
  question  : 自然语言问题
  context   : {stage, run_id, ...} 可选

响应:
{
  "ok": true,
  "need_type": "caliber",
  "answer": "成本优势率 = 低于合理P4*0.99购进的订单金额 / 总订单金额",
  "source": "ops-glossary",
  "category": "knowledge",
  "trust": "authority",
  "confidence": 0.95,
  "version": "2026-08-20"
}
```

- 响应自带 source/category/trust/confidence/version，支撑四道门的可解释性；
- 未命中：`ok=false`，`reason=no_match`，`fallback_candidates` 列出降级候选；
- 网络/登录：响应前需 approval（调用方负责，与框架 RISKY 判定对齐）。

## 二、路由规则（need_type → category → source）

| need_type | 资产分类 | 当前落点 |
|---|---|---|
| term / caliber | knowledge（caliber 走权威子类） | 运营知识库 API（ops-glossary / ops-metrics） |
| tool | tool | `scripts/sources/leyou/leyou_cloud.py` / BI（leyou-search / leyou-collect） |
| data | data | 运营知识库 API + 取数工具 |
| process / method | method | 运营知识库·方法论 + 语义记忆 |
| template | template | 运营知识库模板 + templates/ |

路由步骤：按 `need_type` 过滤 `covers_need[]` 命中资产 → 按 trust 分级 + 命中率 + 时效排序 → 权威优先，无命中降级。

## 三、公共记忆池 API（免登录读）

| 项 | 值 |
|---|---|
| 端点 | `https://lyzsk.cfdaili.top/api/pool`（三库：注入 authority / 会话 reference / 缓存派生） |
| 过滤 | `?tier=inject\|session&category=term\|caliber\|method\|experience&kind=fact\|procedure&q=关键词&limit=N` |
| 响应 | `{ok, count, items:[{id, tier, trust, title, content, hit_count, adopt_count, freshness}]}` |
| 写 | `POST /inject`（仅用户显式，token）`POST` 提交（learn 沉淀）`POST /adopt`（token） |
| CORS | `Access-Control-Allow-Origin: *` |

查询示例：

```bash
python scripts/ask.py --need-type term --question "缺货率"  # 运营知识库在线实时
```

## 四、乐药云智库 CLI（自动登录，approval）

| 项 | 值 |
|---|---|
| 命令 | `python scripts/sources/leyou/leyou_cloud.py <子命令>`（14 子命令：status/search/detail/collect/download 等） |
| 登录 | 多凭证自动登录：本地优先 → 数据库（leyou_zhiku）兜底 → 失效删库 → 全失效扫码（leyou_firebase_login.py） |
| 桥接 | `scripts/sources/leyou_bridge.py`：ensure_login() + 命令透传 + ask(tool) 协议 |
| 用途 | 制度/课程/附件/全库采集 |

桥接示例：

```bash
python scripts/sources/leyou_bridge.py status              # 凭证自动登录并输出登录态
python scripts/sources/leyou_bridge.py search 毛利          # 搜索透传（自动凭证）
python scripts/sources/leyou_bridge.py summary <slug>
python scripts/sources/leyou_bridge.py detail <slug>
python scripts/sources/leyou_bridge.py ask "查制度 毛利"      # ACS ask 协议（need_type=tool）
```

> 登录态预检：`ensure_login(scan=False)` 只复用本地/库凭证，全失效返回 `LOGIN_REQUIRED`（退出码 3），由调用方决定是否 `--scan` 调起扫码（需真人，走 approval）。

## 五、错误码

| 码 | 含义 | 处理 |
|---|---|---|
| 0 | 成功 | 正常返回 |
| 2 | 输入/参数错误 | 修正调用 |
| 3 | 未命中 / 降级 | 返回 fallback_candidates |
| 4 | 依赖缺失（如 `scripts/sources/leyou/leyou_cloud.py` 缺失） | 提示安装/配置路径 |
| 5 | 网络失败 | 记录偏差 medium，暂停确认 |

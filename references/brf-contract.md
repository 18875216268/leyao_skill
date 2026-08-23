# BRF 子系统衔接契约（主 skill ↔ 插件）

> 本文档是 leyao_seed_pro 与 BRF 子系统的**唯一契约**。
> 主 skill 侧只依赖本文档与 `brf/brf.py` 入口，**不感知 BRF 内部实现**；
> BRF 内部（registry/adapters/sources/resolve）完全自治，可独立修改而不影响主 skill 任何部分。

## 一、挂载点（唯一，收敛）

| 项 | 位置 | 说明 |
|---|---|---|
| 插件目录 | `brf/`（leyao_seed_pro 下） | BRF 子系统本体，内部自治 |
| 统一入口 | `brf/brf.py` | **主 skill 与 BRF 的唯一衔接点** |
| 契约协议 | `protocol 1.0`（固定 JSON 字段） | 见下节 |
| 数据源 | `brf/registry.json`（资产声明式注册） | 运营知识库在线实时 + 云智库原生集成 |
| 能力注册 | 运行时按需 | 主执行链第 5 步如需，将 BRF 入口 `capabilities.py register` 到外部 work-dir（契约字段见 capabilities.py） |

## 二、调用方式（主 skill 侧）

```bash
# 1. 卡点调度：主执行链任意阶段遇到 不懂的名词/无法确定的口径/需要制度依据
cd brf
python brf.py ask --problem "<卡点问题>" --work-dir <外部 work-dir>

# 2. 计算门口径校验：四道质量门之计算门，对照权威口径
python brf.py resolve --problem "<指标>" --need-type caliber --work-dir <外部 work-dir>

# 3. 工具兜底：知识域未命中，允许联网建议（需 approval）
python brf.py resolve --problem "<问题>" --allow-network

# 4. 进化沉淀（L0 快速通道，默认）：卡点解决/复盘/交互火花后自动沉淀
python brf.py learn --problem "<问题>" --answer "<答案>" --need-type term --trust authority --work-dir <外部 work-dir>

# 5. 进化沉淀（L1 深度蒸馏，按需）：workflow/skill 等高复用可执行资产
#    AI 顺手提炼精华（去噪/泛化/结构化步骤序列）传入 --distilled；已自验证可加 --verified
python brf.py learn --problem "<怎么做 X>" --answer "<原始轨迹>" --need-type process \
       --distilled "1. <步骤> → 2. <步骤> → 3. <步骤>" --work-dir <外部 work-dir>
#    L1 差异：content 用提炼版 + 质量分升级 + 结构完整性验证（workflow 须含步骤链 / skill 须含执行痕迹）
#    term/caliber 快查一律走 L0，不额外花费（分层蒸馏 · 不给 AI 增加负担）
```

## 三、返回协议（固定字段）

```json
{
  "ok": true,
  "plugin": "brf",
  "protocol": "1.0",
  "problem": "成本优势率怎么算",
  "need_type": "caliber",
  "possibilities": [
    { "answer": "…", "source": "dicts/terms", "trust": "authority", "confidence": 0.97 }
  ],
  "best": { "answer": "…" },
  "path": [ { "layer": "K1", "ok": false }, { "layer": "K2", "ok": true } ],
  "resolved": true,
  "work_dir": "<主 skill work-dir>"
}
```

| 字段 | 语义 | 主 skill 用法 |
|---|---|---|
| `ok` / `resolved` | 是否解决 | 卡点解除 → 继续主流程；未解决 → 转用户确认/人工 |
| `possibilities[]` | 多个候选方案（多可能性） | AI 选最佳/组合/交叉验证 |
| `best` | 推荐方案 | 默认采纳（authority 优先） |
| `path[]` | 分层尝试审计 | 写入 Run 记录（可审计） |
| `work_dir` | 主 skill work-dir 回显 | K1 记忆/缓存接入（演进中） |

## 四、边界（BRF 不做什么）

1. **不替代主执行链**：只解决卡点，解决后回主流程；
2. **不写外部资产**：运营库/云智库只读；唯一写入 = 主 skill 记忆/缓存（进化沉淀，走 supervisor proposal 审批）；
3. **不绕过治理**：网络/登录/装工具/记忆沉淀 → 强制 approval；
4. **不编造答案**：未命中 → `ok:false` + path 记录 + 降级建议。

## 五、进化闭环（复用主 skill 机制）

BRF 解决成功的知识（authority 源/用户确认），按 L1/L2/L3 分级走主 skill 监督闭环沉淀：
`supervisor record → propose → 审批 → memory put(semantic)` + `cache store`。
BRF **不实现** learn 模块/本地记忆/缓存治理（见 `brf/README.md` 与 `brf/references/usage-guide.md`）。

### 三阶段调度（BRF 内部 · ask/resolve 自动执行）

阶段 1 本地 K1（cache 命中即早停——已吸收各源答案；未命中则 memory）；阶段 2 **注入库(authority) 与 会话库(reference) 并行两路查询**（宽词主题检索、全集消费）→ **云智库（leyou 外部数据源，AI 自主规划启用）** → 阶段 3 网络层自助引导（仅空结果）。`path` 记录每阶段尝试；`early_stop:true` 表示本地快路径命中（本地 cache）；复杂问题可 `resolve --expand` 强制全收集。

### 分层蒸馏（L0 快速 / L1 深度 · 不增加负担）

learn 默认 L0 快速通道（六步确定性管线，零额外负担）；**workflow/skill 等高复用可执行资产**（need-type 为 process/template/tool/data 且内容较完整）建议走 **L1 深度蒸馏**——AI 顺手提炼精华（去噪/泛化/结构化步骤序列）作为 `--distilled` 传入（可加 `--verified` 声明已自验证），evolve 用提炼内容 + 质量分升级 + **结构完整性验证**（workflow 须含步骤链、skill 须含执行痕迹，自验证的轻量确定性版，零 LLM）。效益判断：提炼一次、每次命中受益；term/caliber 快查一律走 L0，不额外花费。**蒸馏方法不确定** → 走「外援路径」第 2 级：network-guidance 学蒸馏方法论 → learn 沉淀 → 下次直接命中。

### 交互火花沉淀（进化闭环）

卡点解决成功后 → `python brf/brf.py learn --problem "<问题>" --answer "<答案>" --need-type <term|caliber|...> --trust authority --work-dir <dir>` 自动沉淀（事件+缓存+蒸馏+分流）；**用户交互中确认的新口径、新方法、新认知（非个人指代）同样走 learn**——shared 进公共池供群体复用、personal 仅本地。

## 六、内部自由改动（不影响主 skill 的清单）

- ✅ 修改 `brf/registry.json` 资产条目、新增资产；
- ✅ 修改 `brf/scripts/adapters/`、`brf/scripts/sources/`、`brf/scripts/resolve.py`；
- ✅ 修改 `brf/registry.json` 资产（含 source 指向）、`brf/scripts/**`；
- ✅ 新增 `brf/scripts/adapters/` 自定义适配器；
- ❌ 不修改 `brf/brf.py` 的**协议字段**（possibilities/best/path/ok）；
- ❌ 不修改本契约文档的调用方式。

## 七、资源（安装即用）

BRF 插件运行资源分布（**无离线快照——运营知识库实时查询公共池，保证最新**）：

| 资源 | 位置 | 说明 |
|---|---|---|
| 运营知识库（公共池） | 资产 `source` = `https://lyzsk.cfdaili.top/api/pool` | **每次使用实时查询**（注入库 authority + 会话库 reference） |
| 云智库客户端 | `brf/scripts/sources/leyou/leyou_cloud.py` | **原生集成**（非副本），随插件走 |
| 凭证自动登录 | `brf/scripts/sources/leyou/leyou_firebase_login.py` | 原生集成；凭证写同目录 `leyou_token.json` |
| 模板清单 | 资产 `source` = `../templates` | 主 skill 真实模板（向上遍历查找 templates 目录） |

**原生集成说明**：云智库两脚本已是 BRF 插件的一等公民（`sources/leyou/`），单一来源、随插件走——不再依赖外部「乐药云智库_Skill封装/」目录，也不存在 vendor 副本同步问题。原目录可独立保留（作独立 skill 或脚本升级源头），BRF 不依赖它。

**实时查询说明**：运营知识库（术语/口径/公司/方法论）已迁移公共池两库——术语/口径/公司走注入库（`tier=inject`，authority 权威），方法论走会话库（`tier=session`，reference）。统一走 `pool` 适配器查询 `lyzsk.cfdaili.top/api/pool`，数据最新；代价是依赖网络（用户明确选择，保证最新优先）。原 `data.json` 已从 Pages 移除（存档 `brf/data.json.archive`）。

**唯一外部依赖**：Python 3.9+ 与 `requests` 库（云智库搜索需要；其余功能纯标准库）。
**运行数据**：凭证 token 写 `brf/scripts/sources/leyou/leyou_token.json`；卡点解决结果沉淀走主 skill 记忆/缓存（`--work-dir`）。

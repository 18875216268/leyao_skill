# BRF 子系统（blocker-resolution-framework）

> leyao_seed_pro 的**卡点解决插件子系统**。本目录不是独立 skill——它由主 skill 调度（衔接契约见 `../references/brf-contract.md`），内部完全自治：修改本目录任何内容不影响主 skill。

## 定位

AI 在主执行链任意阶段遇到「不懂的知识 / 无法解决的问题（卡点）」时，由主 skill 调度本子系统：

```
卡点 → brf.py ask(problem)
  → 知识域：K1 主 skill 记忆/缓存 → K2 运营知识库（在线实时）→ K3 云智库（原生集成）
  → 工具域：T1 本地工具 → T2 云端工具链
  → 网络层：兜底（approval）
  → 多可能性输出：possibilities[] + best + path
```

进化沉淀复用主 skill 治理平面②③（supervisor 审批 → semantic 记忆 + 内容寻址缓存），本子系统**不重复实现**记忆/缓存/进化。

## 触发场景

- 出现无法理解的名词、不确定用户意思时，先到此查询消歧；
- 日报/周报/复盘需要业务术语、指标口径、子公司清单等依据；
- 主执行链任意阶段需要知识注入或口径校验。

## 入口（主 skill 唯一衔接点）

```bash
cd brf
python brf.py status
python brf.py ask --problem "<卡点问题>" --work-dir <主skill work-dir>
python brf.py resolve --problem "<指标>" --need-type caliber --work-dir <dir>   # 计算门口径校验
python brf.py resolve --problem "<问题>" --allow-network                         # 网络层建议（approval）
```

返回协议（固定）：`ok / plugin / protocol / problem / need_type / possibilities[] / best / path / resolved / work_dir`。

## 内部结构

```
brf/
├── brf.py                     统一入口（唯一衔接点，协议 1.0）
├── registry.json              资产注册表（运营库在线 + 云智库 + 模板）
├── scripts/
│   ├── resolve.py             多可能性收集内核（K1→知识域→工具域→网络层）
│   ├── infer.py               意图识别（need_type 自动推断）
│   ├── adapters/              dict / api / cli / template 适配器（领域无关）
│   ├── sources/
│   │   ├── k1_memory.py       K1 层（委托主 skill memory/cache）
│   │   └── leyou/             云智库原生集成（leyou_cloud + firebase_login + token）
│   └── ask.py                 ask 薄封装（兼容入口）
├── references/                acs-model / api-contract / usage-guide
├── examples/                  通用接入指南（新源 3 步接入）
└── tests/                     单测（离线确定 + 网络可选）
```

## 关键设计

- **原生集成**：云智库两脚本即插件一等公民（`sources/leyou/`），单一来源；
- **实时数据**：运营知识库迁移公共池两库（注入 authority + 会话 reference），统一查询 `lyzsk.cfdaili.top/api/pool`（本地 K1 → 两库并行 → 云智库确认 → 网络兜底）；
- **不重复建立**：记忆/缓存/进化全复用主 skill 既有机制；
- **多可能性**：resolve 收集全部命中候选（trust→confidence 排序 + best 推荐），AI 拥有选择/组合权。

## 自检（修改内部不影响主 skill 的红线）

- ✅ 可自由改：registry / adapters / sources / resolve / 新增适配器 / 新增资产；
- ❌ 不改 `brf.py` 协议字段（ok/possibilities/best/path）；
- ❌ 不改 `../references/brf-contract.md` 的调用方式。

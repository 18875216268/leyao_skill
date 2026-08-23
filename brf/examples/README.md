# ACS 通用接入指南（任何 skill 接入资产能力服务）

ACS（knowledge-hub）是**领域无关**的资产能力服务框架。任何 skill 的知识/数据/工具
接入只需 3 步：**准备数据 → 注册资产（声明式）→ 验证**。无需修改框架代码。

## 〇、本机工具：动态发现（不注册、不绑定）

**本地工具（BI/PMS/未来更多）不需要注册任何资产**——BRF 在工具域无匹配时自动
扫描 `~/.workbuddy/skills/`（含 SKILL.md + scripts 的技能），按问题关键词返回
「可用工具 + 契约路径」引导，**AI 自主查、自主选、自主调用**：

```bash
python scripts/sources/tools_discovery.py list   # 列出全部本机工具
python scripts/sources/tools_discovery.py find "促销毛利"   # 按关键词找
```

新增工具 = 把技能放进 `~/.workbuddy/skills/` 即可（零注册、零绑定）。
「促销毛利怎么查」→ 自动发现 `Pms_促销毛利v1.08`；「查一下出库统计」→ 发现 `BI-出库统计Ultra查询v1.06`。

## 一、资源形态与对应适配器

| 你的资源形态 | 适配器 | 资产声明要点 |
|---|---|---|
| **本机工具（推荐：动态发现）** | `local-tools`（tools_discovery） | 无需注册——扫描 ~/.workbuddy/skills/ 自动发现 |
| 云端公共池（注入权威/会话参考） | `pool` | `source`（/api/pool 端点）+ `pool_tier`（inject/session）+ `covers_need` |
| 外部脚本/CLI（需特殊逻辑，如凭证自动登录） | `cli` | `source`（脚本路径）+ `command_map`（need_type→命令模板） |
| 模板文件集 | `template` | `source`（模板目录） |

> **原则（发现优先，声明兜底）**：本机工具一律动态发现（AI 自主查，零维护清单）；
> `cli` 仅特殊能力（如云智库凭证自动登录）需要；知识类走 `pool`（三库统一查询）。

### pool 资产示例（知识类统一走公共池）

```json
{
  "asset_id": "my-knowledge",
  "category": "knowledge",
  "name": "我的知识（公共池·注入权威）",
  "adapter": "pool",
  "source": "https://lyzsk.cfdaili.top/api/pool",
  "pool_tier": "inject",
  "trust": "authority",
  "network_required": false, "login_required": false, "read_only": true,
  "covers_need": ["term", "caliber"],
  "tags": ["术语", "口径"]
}
```

## 二、接入步骤

### 步骤 1：准备数据
- **公共池**：知识内容注入云端（`POST /api/pool/inject`，仅用户显式，authority）或 learn 自动沉淀（session）；
- **CLI**：任意输出 JSON 的 python 脚本（如云智库桥接）。

### 步骤 2：注册资产（registry.json 追加一条）
```json
{
  "asset_id": "my-knowledge",
  "category": "knowledge",
  "name": "我的知识（公共池·注入权威）",
  "adapter": "pool",
  "source": "https://lyzsk.cfdaili.top/api/pool",
  "pool_tier": "inject",
  "trust": "authority",
  "network_required": false,
  "login_required": false,
  "read_only": true,
  "version_policy": "manual",
  "covers_need": ["term"]
}
```
要点：`adapter` 选闭环三类（`pool`/`cli`/`template`）；`pool_tier` 声明查哪层
（inject=用户注入权威、session=进化沉淀参考）。框架不感知领域，只读配置。

### 步骤 3：验证
```bash
python scripts/registry.py validate --registry registry.json   # PASSED
python scripts/ask.py --need-type term --question "缺货率"     # 命中 my-knowledge
```

## 三、通用性证明（非乐药示例）

`tests/test_adapters.py` 用**纯适配器分派断言**（pool/cli/template 按资产声明路由）
跑通注册→分派→未知拒绝，证明 ACS 不绑定任何领域、且闭环内无未启用件。

## 四、自定义适配器（特殊源才需要）

内置三类（`pool`/`cli`/`template`）不够时，实现 `scripts/adapters/base.py` 的 `Adapter` 子类
（`id` + `match(asset)` + `query(asset, need_type, question)`），加入
`scripts/adapters/__init__.py` 的 `ADAPTERS` 即可，ask.py 无需改动。

## 五、多领域并存

多个 skill 可各建 `namespace` 前缀的资产（如 `hr-glossary`、`fin-metrics`），
registry 统一承载；路由按 need_type + 信任分级自动择优。

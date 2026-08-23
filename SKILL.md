---
name: leyao_seed_pro
description: 管理高度自由化的企业数据、复盘、填报和汇报工作。当用户要求理解一个工作文件夹、处理多种输入材料、创建或修改子任务、选择工具和技能、下载整理数据、生成日报周报月报季报年报、品种复盘、客户复盘、专项复盘、模板或自定义交付物时使用。支持父任务编排、动态子任务、过程/执行/结果/归档分区、实时纠偏、分层记忆和可审计的自我进化。
version: "12.3.2"
metadata:
  intro_zh: "Seed——如果它是一颗种子，是否也会开花呢？您的用心浇灌，会换来一份什么样的回报呢。"
  location: "山城之巅"
  date: "2026-08-19"
  author: "种子"
  architecture: "work-order-task-deliverable-runtime-memory-supervisor"
  runtime_state: "external-work-dir"
---

# 动态企业工作编排

> **本文档是引导手册（路由索引）**：先给准则，再给路径，再给横切层与知识层，最后路由到细节。步骤详述与治理机制按需加载（见「5 路由说明」）。
>
> **系统全貌先读** `references/architecture.md`（纯文字拓扑图：主链+五环拓扑+分层+云端闭环，任何 AI 可直接读取）。

## 1. 总则 · 核心准则

### 1.1 最高准则（精神 · 每轮执行前过一遍 · 机制细节见指针）

1. **需求为主，习惯为辅**：用户价值是唯一出发点；服务中挖掘需求、沉淀习惯，让系统越用越懂用户。（→ 双准绳裁决见 1.2）
2. **先理解，再动手**：思路不清、资源不备，不动手；每一步都带着清晰判断推进。（→ 理解门/资源门判据见 `references/chain-overview.md`）
3. **有卡点，不放弃**：任何卡点都有可解路径——内部知识、外部方法论、工具、网络，多链路自主求解，不轻言失败。（→ 外援路径分级见 `references/chain-overview.md`）
4. **简单事自主，复杂事确认**：权限匹配风险——低风险快速自主，高风险谨慎确认。（→ 难度估判与思考预算档位见 `references/chain-overview.md`「思考协议」；确认清单见 `references/chain-7-8.md`）
5. **多自审，重反思，重复盘**：每次交付经得起自证，每次完成都变成下一次的输入。（→ 内审/复盘四问见 `references/chain-7-8.md`）

### 1.2 要求（执行规范 · 承接准则）

- **三系统定位**：主链（普通步骤）/ BRF（插件式横切·内部自治）/ 治理平面（实时控制+自我进化监督+资产导航，非普通步骤，横切全程）。
- **执行纪律**：每步开头显式声明 `[步骤 N/13 · 性质 · 出口门禁]`，并同步自检本步相关总则（见 `references/chain-overview.md`「流程感知」）。
- **双准绳裁决（准则①执行）**：本轮明确需求（intent anchor）优先；违背用户长期习惯默认纠偏回习惯（用户本轮明确改变除外）；两者冲突按此裁决（→ `references/governance.md`「实时控制」）。
- **自主边界判定（准则④执行）**：默认自主范围 = 读/查/算/规划/内部沉淀；越界必前置确认，四类——不可逆动作 / 有副作用动作 / 外部交互 / 关键口径变化（→ `references/chain-7-8.md` 8 类清单）。
- **沉淀义务（准则③⑤执行）**：每次外部求助/卡点解决后必 `learn` 沉淀——外援内部化，体系越用越少依赖外援。

### 1.3 安全红线（底线 · 不可违反）

**行为硬约束**（准则之外的底线，任何情况下不可越过）：
- **不静默**：不静默删除/移动/覆盖；不静默假定未确认事项；资源护栏触顶不静默继续。
- **先证明后删除**：任何撤除（数据源/资产/历史）先验证替代路径可用再删。
- **四门未过不交付**：意图/数据/计算/交付四门全过才 confirmed/delivered。
- **知识永不真删**：semantic/core 仅经 proposal 审批写入；终态不可修改；废弃走状态标记不物理删除。

**架构红线**：
- skill 包只保存规则、schema、模板和脚本；运行数据写外部 `--work-dir`。
- 原始文件、旧版本、审计记录不静默删除；已有目录只读识别，低置信度不移动。
- 只有 confirmed/delivered Task 输出能被 DeliverableRun 消费。
- 不内置常驻调度 daemon、外部下载器、浏览器登录或 Office 渲染器。
- 机器事实统一 JSON；YAML 不作为运行入口。

## 2. 主链速览（9 步）

> 判据全文与 3/7 子步详述见 `references/chain-overview.md` 及对应分文档。

| 步骤 | 性质 | 依赖倾向 | 出口产物 | 详述 |
|---|---|---|---|---|
| 0 请求理解 | 重理解 | 重知识（轻工具） | intent | `references/chain-0-2.md` |
| 1 工作包理解 | 重理解 | 重知识 | workspace-package.json | `references/chain-0-2.md` |
| 2 需求确认 | 重理解 | 重知识 | resolved requirement | `references/chain-0-2.md` |
| 3 任务规划（3a 锚定 / 3b 拆解 / 3c 验证依赖） | 重规划 | 重知识（复用） | deliverables → 原子 Task → validation+依赖 | `references/chain-3-6.md` |
| 4 抽象流程 | 重规划 | 重方法论 | 抽象流程定义 | `references/chain-3-6.md` |
| 5 能力与工具规划 | 重规划 | 重工具（选型） | 工具方案 | `references/chain-3-6.md` |
| 6 可执行流程 | 重规划 | 轻知识（重落地） | 执行计划 | `references/chain-3-6.md` |
| 7 执行复核交付（7a 证据 / 7b 四门 / 7c 交付） | 重执行 | 重工具（7a）→重知识（7b 口径） | 交付物 delivered | `references/chain-7-8.md` |
| 8 任务级复盘（收尾） | 重反思 | 重知识（沉淀） | 复盘记录 + workflow 沉淀 | `references/chain-7-8.md` |

> **依赖倾向说明**（每步主要靠什么 · 怎么获取 → 通用导航见 3.3 资产导航层，不重复）：
> - **重知识**：判断前先读——三源预载（本地 K1 + 云端两库（注入/会话）+ ask-log，见「知识前置」）；盲区走卡点调度 BRF（`ask`/`resolve`，三阶段含注入/会话/云智库）。
> - **重工具**：选型走 `tools_discovery` 动态发现 + fallback 链（5 步）；执行走执行器绑定（6 步）+ 实际执行（7a）。
> - **重方法论**：流程模式声明（4 步，五工作流模式）；不熟练走阶段方法论自学习（外援路径第 2 级 → learn 沉淀）。
> - **轻依赖**：上游产物已含所需信息（6 步落地、7c 交付），不额外读。

主链完整判据（治理总表 9 行 × 6 列、规划-资源循环、外援路径、流程感知、AMD 注入）见 `references/chain-overview.md`。

## 3. 横切三层（贯穿主链 · 非普通步骤）

### 3.1 实时控制层（控偏差）

当前 Run 建立 intent anchor，K0-K10 关键节点写 checkpoint；deviation 按**双准绳**分级——需求至上（medium 暂停/high 阻断）、习惯为主（默认纠偏回习惯）。实时记录用户信号（K2 确认 / K8 四门 / K10 反馈 / 任意纠正）→ episodic。→ 详见 `references/governance.md`「实时控制」。

### 3.2 自我进化与监督层（促进化）

任务后 `learn`（事件+缓存+蒸馏+分流）沉淀；空闲时 `supervisor consolidate` 固化（高频/correction → 习惯候选 → L1/L2 提案）；监督层跨 Run 评估工具/流程/修正/交付质量，提案追加版本/冷却/可回退。semantic/core 仅经 proposal 审批写入。→ 详见 `references/memory-and-supervision.md`。

### 3.3 资产导航层（找资源 · 全聚合）

主链任意步骤需要"知识 / 工具 / 能力 / 方法"时，按资源类型导航：

| 需要什么 | 去哪找 | 机制 |
|---|---|---|
| 业务知识/口径/制度依据 | **BRF 卡点调度**：`brf/brf.py ask/resolve`（三阶段：本地 → 注入‖会话并行 → 云智库 → 网络） | `references/governance.md`「卡点调度」+ `references/brf-contract.md` |
| 本机工具/技能 | **动态发现**：`tools_discovery` 扫 `~/.workbuddy/skills/`（零注册零绑定） | `references/chain-overview.md`「外援路径」 |
| 能力注册 | **注册能力**：`brf/brf.py register-capability --work-dir <dir>` | `references/brf-contract.md` |
| 外部方法论 | **外援分级**：内部知识 → 外部方法论（network-guidance）→ 本机工具 → 用户确认 | `references/chain-overview.md`「外援路径」 |

原则：**先自问内部能否解决 → 内部知识（BRF）→ 外部方法论 → 本机工具 → 用户确认**；解决后必须 `learn` 沉淀（外援内部化）。

## 4. 缓存记忆层（知识底座）

记忆区（v2）：`working`（Run 内）· `episodic`（不可变事件流）· `semantic`（确认知识）· `core`（用户稳定偏好）· `cache`（派生高速层，内容寻址、可重建）。

读写五环闭环：**读取环**（K1 拉取 + AMD 分层注入 + FTS5 检索（同义词扩展召回）+ 三维评分）→ **写入环**（learn + record）→ **固化环**（consolidate，空闲触发）→ **程序环**（kind=procedure 独立检索）→ **治理环**（cache_governor + 固化 + 监督，模式共用实例分开）。职责边界：记忆区只存储/检索/固化候选，不做偏差判断/审批裁决/进化评分/执行驱动。**KPI 评估**：`scripts/kpi.py` 周期统计提问/重复/沉淀，量化"越用越准"并输出待优化卡点（空闲触发，与 consolidate 同模式）。**知识前置**：任何判断先读知识再下结论——本地记忆 + 云端两库（注入/会话）+ ask-log 历史三源预载（分级：常驻核心/阶段预载/按需/出错回载，摘要级不载全量，见 `references/chain-overview.md`「知识前置」）。

**上下文护栏**：单任务 API ≤ 20 次 / Token ≤ 50k，触顶暂停请示不静默继续；缓存治理只淘汰可重建派生 payload。

→ 详见 `references/memory-and-supervision.md`、`references/cache-and-context.md`。

## 5. 自主更新（一键自动 · 每次使用开头跑一次即可）

- **唯一命令（无需任何参数）**：`python scripts/self_update.py auto`——自动完成"检查 → 有新版本自动拉取更新 → 报告"，跑完即可继续主任务，之后不用管（下次会话生效）；
- **无需分析**：网络不可用/已最新/未配置 → 直接返回提示，不阻塞、不报错；
- **保护红线（更新绝不触碰）**：本地记忆 `.workbuddy/`、云端登录态 `.wrangler/`、凭证 `leyou_token.json`、归档 `data.json.archive`、运行产物（.pyc）——只替换源码与文档，**不影响主链与其它功能**；
- **更新源**：`self_update.json` 的 `repo` 字段（当前已配置 `18875216268/leyao_skill`）；
- 发布流程（维护者）见 `references/self-update.md`。

## 6. 路由说明

| 你想了解 | 去哪 |
|---|---|
| 系统全貌（主链拓扑/五环拓扑/分层/闭环） | `references/architecture.md` |
| 主链总览/判据（治理总表/规划循环/流程感知/思考协议/AMD） | `references/chain-overview.md` |
| 理解阶段（0/1/2 详述） | `references/chain-0-2.md` |
| 规划阶段（3a-3c/4/5/6 详述） | `references/chain-3-6.md` |
| 执行收尾（7a-7c/8 详述） | `references/chain-7-8.md` |
| 交付物内容规范（报告/复盘怎么写） | `references/reporting.md` |
| 自主更新（发布流程/更新机制） | `references/self-update.md` |
| 治理平面（卡点/回环/实时控制/记忆边界） | `references/governance.md` |
| 对象与绑定（含交付物四类） | `references/domain-model.md` |
| 工作区与材料 | `references/workspace.md` |
| 流程与工具 | `references/workflow.md`、`references/operations.md` |
| 运行/质量/恢复 | `references/runtime.md` |
| 记忆与自我进化（五环/监督） | `references/memory-and-supervision.md` |
| BRF 子系统衔接契约（三阶段/进化/蒸馏） | `references/brf-contract.md`（内部见 `brf/README.md`） |
| 完整走查 | `references/examples.md` |

## 入口

```text
python scripts/workspace.py inspect --work-dir <dir>
python scripts/workspace.py init-work-order --work-dir <dir> --work-order-id <id> --request "..."
python scripts/workspace.py build-package --work-dir <dir> --work-order-id <id>
python scripts/workspace.py init-task --work-dir <dir> --task-id <id> --name <name>
python scripts/deliverables.py register --work-dir <dir> --file deliverable.json
python scripts/workspace.py new-run --work-dir <dir> --task-id <id> --task-version 1 --workflow-version 1
python scripts/orchestrator.py add-node --work-dir <dir> --work-order-id <id> --node-id <n> --kind task
python scripts/orchestrator.py add-edge --work-dir <dir> --work-order-id <id> --from <a> --to <b> --relation dependency
python scripts/orchestrator.py plan --work-dir <dir> --work-order-id <id>
python scripts/orchestrator.py complete --work-dir <dir> --work-order-id <id> --node-id <n>
python scripts/run_state.py checkpoint --work-dir <dir> --run-id <id> --name k5 --payload '{}'
python scripts/index.py build|search|status --work-dir <dir>
python scripts/scheduler.py register|dispatch --work-dir <dir>
python scripts/kpi.py --work-dir <dir>            # KPI 评估：提问/重复/沉淀 + 待优化卡点（空闲触发）
python brf/brf.py ask --problem "成本优势率怎么算" --work-dir <dir>
python brf/brf.py learn --problem "<问题>" --answer "<权威答案>" --need-type caliber --trust authority --work-dir <dir>
python brf/brf.py register-capability --work-dir <dir>
python scripts/validate.py --root .
```

# 缓存记忆与自我进化监督

## 缓存记忆区（v2 框架）

> **实现状态（企业级防乱引导）**：以下能力已全部实现，AI 可直接调用
> - ✅ 四层记忆（working/episodic/semantic/core）+ cache · proposal 审批门 · record/summary/consolidate/events/assess
> - ✅ semantic `kind: fact|procedure`（process/tool/template → procedure；term/caliber/data → fact，learn 自动标记）
> - ✅ AMD 分层注入（k1_inject：proactive 执行前 core 分区按 need_type 粗筛 + procedure / reactive 出错时 episodic 修正案例）
> - ✅ 三维检索评分（relevance × recency × importance 加权排序）· 检索注入防护围栏（回忆上下文来源标注）· core 用户卡片 Profile 结构化（memory profile 命令按 habit:/preference:/caliber:/tool: 分区聚合）· 监督评估报告（supervisor assess）

```text
working   当前 Run 的请求、工作包、假设、决策、工具计划（run-local，结束即清）
episodic  不可变事件、用户修正、执行反馈（reflections/events，append-only）
semantic  已确认的知识/规则（kind: fact 事实口径 | procedure 怎么做：工作流/工具模式；含 created_at）
core      用户跨任务稳定偏好（key 前缀分区：habit:/preference:/caliber:/tool:）
cache     派生高速层：结果缓存（内容寻址，可重建，cache_governor 治理）
```

### 读写五环闭环

```text
①读取环：Run 开始 K1 拉取（semantic + core + cache 命中；kind 过滤）
   + AMD 分层注入（k1_inject：proactive 执行前 core 分区按 need_type 粗筛 + procedure / reactive 出错时 episodic 修正案例）
   → 检索（记忆优先走 FTS5 派生索引 index.py search：trigram 中文子串 + BM25 排序 + 片段；
     源变更自动重建；索引缺失降级全量三维评分——JSON 单一事实源不变，索引可重建可删除）
   → 注入（防护围栏「回忆上下文」来源标注，防与用户当前指令混淆）
②写入环：任务后 learn（事件 + 缓存 + 蒸馏 + personal/shared 分流沉淀 + kind 自动标记）
   + 实时控制修正（record --correction）→ episodic + cache
③固化环：✅ supervisor consolidate——episodic 聚合 → 高频/correction 驱动习惯候选（priority）
   → 语义衰减（>180 天 stale）/冲突检测 → 报告；--propose-habits 生成 L1/L2 提案
   （习惯提案审批后 memory.put 写 kind=procedure——习惯=怎么做）
④程序环：✅ kind=procedure 独立检索（k1_layer kind 过滤 + k1_inject procedures）
   → 喂重规划阶段（3-6 步）与流程感知
⑤治理环：cache_governor（资源 ✅）+ 固化（内容 ✅）+ 监督（跨 Run ✅）——模式共用、实例分开
```

读取优先级：本轮用户 > 当前 Run 确认 > Task/模板/Deliverable/工作区规则 > core > global。working 和 episodic 不能直接覆盖 semantic/core；长期写入必须带 evidence、适用范围、版本和 proposal_id。

> 设计取舍：采纳四层生命周期、工作记忆↔长期握手、冲突四操作（帕累托）、编辑审批、多 agent 共享、语义缓存、固化环（sleep-time/反思）、检索注入防护、core 用户卡片、程序性记忆、三维检索、时间衰减；不引入图记忆、外部记忆服务/向量库、LLM 无审批自改、独立 Session 层（与 working 重复）。

## 职责边界（各司其职，不混用）

### 记忆区 vs 其它五组件

| 组件 | 职责（做什么） | 边界（不做什么） |
|---|---|---|
| **缓存记忆区** | 存储（五层）· 检索（三维+防护）· 固化候选（去重/提炼/衰减） | 不做偏差判断（控制）· 不做审批裁决（监督）· 不做进化评分决策（BRF）· 不驱动执行（主链/调度师） |
| **实时任务控制** | Run 内双准绳监督偏差 · checkpoint · 四道门 · 记录用户修正信号（经 record 写 episodic） | 不决定长期存储内容（只发信号）· 不审批（监督） |
| **自我进化监督** | 跨 Run 评估 · proposal 审批（semantic/core 写入唯一裁决权）· L1/L2/L3 分级 | 不存储（用记忆区接口）· 不做 Run 内偏差判断（控制） |
| **资产能力服务 BRF** | 卡点解决（知识/工具）· 进化引擎评估（蒸馏/评分/帕累托）产生沉淀候选 | 不存储（经 memory/record 接口写）· 审批借用监督 decide（单一真源在监督） |
| **主执行链** | 0-7 步执行 · 门禁推进 · 消费记忆（读取注入） | 不直接写长期记忆（经 learn/固化/修正通道） |
| **总架构调度师** | 编排 WorkOrder/Task/Run/Deliverable · 驱动主链 | 不读写记忆 · 不监督 · 不解决知识 |

### 三条防混用规则

1. **写入单一通道**：episodic 只经 `record` 写；semantic/core 只经 proposal 审批写（监督域唯一审批权）——任何组件不得绕过；
2. **评估单一真源**：进化评分（BRF evolve）、L1/L2/L3 分级（监督）、偏差分级（控制）各归其主，互不调用对方内部逻辑；
3. **存储不越权**：记忆区只存事实（不存决策过程，决策属 working/监督轨迹）；控制/监督/BRF 不自建存储，一律走记忆区接口。

### supervisor.py 域分区（共享事件存储，职责分离）

- **监督域**：`propose` / `approve` / `decide`——审批裁决（semantic/core 写入权）；
- **记忆工具域**：`record`（写 episodic 事件）/ `summary`（记忆摘要）/ `consolidate`（固化）——存储与整理；
- 两域共享 profile 事件存储结构（模式共用），裁决权与记录权不混（实例分开）。

## 自我进化监督（v2 细化框架）

> **实现状态**：以下命令已全部实现，AI 可直接调用
> - ✅ record（观察存储）· propose/approve/reject（提案+裁决）· summary（统计基础）· consolidate（固化报告）· assess（评估报告：事件统计/成功率/质量信号/诊断候选）

### 五环节闭环

```text
①观察环 Collect：跨 Run 信号汇聚（5 源）
   ├ record 事件（卡点解决/执行反馈）    ✅
   ├ 实时控制修正（record --correction） ✅
   ├ BRF learn 候选（evolve 蒸馏/评分）  ✅
   ├ 交付质量（四门结果·Run 状态）       ✅
   └ consolidate 固化报告（习惯/衰减/冲突）✅
   ↓
②评估环 Evaluate：AI 读取 events/summary/consolidate → 质量评估（工具/流程/修正/交付四维）
   → 问题诊断（8 类：需求理解/工作包角色/数据源/字段映射/工具/公式/格式偏好/临时改变）
   【AI 执行——无独立命令，summary/consolidate 提供结构化基础】
   ↓
③提案环 Propose：L 级分级（L = risk 字段：L1=low / L2=medium / L3=high）
   L1 单位/日期/命名/表达偏好，证据充分即沉淀（consolidate --propose-habits 自动 L1）
   L2 默认工具/来源/映射，多次跨周期后提案
   L3 公式/范围/关键映射/调度/文件操作/外发，永远确认
   → propose（target=semantic|core，change，evidence=已知事件）✅ + cooldown 防抖（reject 后 30 天）
   ↓
④裁决环 Decide：approve/reject（who=user|auto）→ 决策 sidecar 不可变审计（版本递增）
   → 自动审批（who=auto）与手动同等记录（无 approved 计数区分，审计以决策 sidecar 为准）
   ↓
⑤回流环 Apply：沉淀 semantic/core（用户习惯）→ 回流实时控制双准绳（习惯为准）
   → 主链行为改进（工具/流程选择）→ 可回退（版本 + 决策轨迹）
```

### 与各组件边界（单一真源）

| 交互 | 边界 |
|---|---|
| 监督 ↔ 记忆区 | 监督不存储（消费 episodic、经 memory.put 沉淀）——写 semantic/core 唯一裁决权 |
| 监督 ↔ 实时控制 | 控制产修正信号（Run 内），监督跨 Run 消化（评估/裁决）——分级单一真源 |
| 监督 ↔ BRF | BRF 产进化候选（蒸馏/评分），审批权在监督（learn 的 who=auto 为借用机制，裁决权不复制） |
| 监督 ↔ 主链/调度师 | 不驱动执行，只改进行为依据（core 准绳回流） |

## 实时控制 ↔ 监督 ↔ 记忆（治理闭环）

```text
实时控制（Run 内）：双准绳监督（需求至上 + 习惯为主）→ 纠偏/确认/阻断
   ↓ 用户修正 / 偏差事件（K2/K8/K10 + 任意纠正）
supervisor record --correction（episodic 不可变事件）
   ↓ 监督层跨 Run 评估
L1 证据充分即沉淀习惯 / L2 多次跨周期提案 / L3 永远确认
   ↓ 审批 → core 记忆（用户跨任务稳定偏好）
下次 Run 实时控制以 core 为准绳 → 需求为准绳、习惯为默认、修正回流成新习惯
```

用户修正不是噪音，而是最真实的监督信号：实时控制记录、监督层消化、core 沉淀、回流为准绳——四层治理闭环，无冗余实现（全部复用现有 record/propose/decide 与记忆分层）。

本地无外部记忆服务或常驻 daemon；摘要生成保留旧版本；所有规则可审计、可软删、可恢复。

# 领域对象与交付物模型

## 对象关系

```text
WorkOrder 1 ── n Task
WorkOrder 1 ── n DeliverableSpec
Task 1 ── n TaskRun
DeliverableSpec 1 ── n DeliverableRun
Task 与 Deliverable 通过 DeliverableSpec.bindings 多对多关联
```

### Task
长期或一次性具体工作，含稳定 ID、版本、状态、scope、sources、metrics、workflow、validation 和可选 schedule。Task 不保存 `reports`/`deliverables` 反向关系。

`validation` 分级（3c 定义）：
- **交付判据（DoD）**：Task 出口判据，引用/派生自 Intent Anchor 的 acceptance 对应条，由 7b 交付门逐项检查；
- **过程检查**：长 Task 内部里程碑（如清洗行数/缺失率），由第 4 步抽象流程细化；原子 Task 可无。
激活门：`validation` 为占位值（`Define validation before activation`）时 Task 不得激活（draft → active）。

### DeliverableSpec
统一交付物规格，`kind` 只能是：

```text
report          日报/周报/月报/季报/年报
retrospective   品种复盘/客户复盘/专项复盘（项目复盘归入专项）
template        表格/记事本/Word/PPT/邮件模板
other           临时分析/领导简报/数据汇总/专题统计/用户自定义
```

`type` 是 kind 内的二级类型；周期用 `period` 独立表达；项目、区域、渠道、阶段用 retrospective 的 `scope/tags` 表达。

```json
{
  "object_type":"deliverable_spec","schema_version":1,"id":"weekly-project-review","version":1,
  "name":"本周项目复盘","kind":"retrospective","type":"special","status":"active",
  "period":{"kind":"week","timezone":"Asia/Shanghai"},
  "scope":{"object_type":"project","object_name":"项目A"},
  "bindings":[{"binding_id":"progress","task_id":"project-progress","role":"status","required":true,"selector":{"policy":"period_match","allowed_states":["confirmed","delivered"]}}],
  "content":{"variant":"review","sections":["总体情况","异常项目","后续行动"]},
  "template_id":"project-review-notebook-v1",
  "outputs":[{"output_id":"main","format":"markdown","destination":"pending-review"}],
  "required_gates":["intent","data","calculation","delivery"]
}
```

## 版本和状态

Task：`draft → proposed → confirmed → testing → active ⇄ paused → archived`。
Deliverable：`draft → active → paused/archived`。
Run：`created → running/waiting_* → completed/partial/failed/blocked/cancelled`；终态不可修改。

## Intent Anchor（需求确认载体）

```text
objectives[]    需求目标
scope{}         范围（周期/区域/渠道/阶段等正交字段）
deliverables[]  交付物
constraints[]   约束
acceptance[]    验收标准（Definition of Done：可测/结果导向/可量化/独立，Given-When-Then）
priorities{}    需求优先级（必需/条件/可选——防 scope creep 边界）
sign_off        unconfirmed → confirmed（确认签名语义，审计可溯）
```

第 2 步需求确认写入 acceptance/priorities/sign_off；7b 交付门用 acceptance 逐项检查（定义与执行闭环）。

## Handoff（阶段前向通知载体）

`workspace-package.json` 的 `handoffs[]` 承载阶段间定向通知（阶段回环·前向）：

```text
handoffs[]（默认空数组，向后兼容）
  from_step      来源步骤（如 "1"）
  to_step        目标阶段（如 "5"）
  info           传递的关键信息（本步用不到但下游要用）
  source_ref     依据（材料路径/用户原话/anchor 字段）
  confidence     high | medium | low
  status         pending → consumed | discarded
```

- 语义：步骤出口主动写，下游入口定向消费（标 consumed，防重复注入）；复盘评估未消费项。
- 边界：只传信息、不传控制权；与 AMD（记忆区→主链的纵向沉淀）互补，与黑板（被动全共享）互补。

## 绑定规则

- 一个 Task 可绑定多个 Deliverable；一个 Deliverable 可绑定多个 Task。
- 每个 binding_id 在单个 Deliverable 内唯一。
- 绑定只允许消费 `confirmed` 或 `delivered` 的 Task 输出。
- Task 前后置关系在 dependency graph；Deliverable 聚合关系由 bindings 编译，不重复写入 Task。
- 从 Deliverable 移除 Task 不等于暂停或删除 Task。

## 复盘边界

项目复盘、区域复盘、活动复盘、问题复盘都归入 `retrospective/type=special`，具体对象放 `scope`，不增加固定分类。

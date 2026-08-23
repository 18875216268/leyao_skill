# 运行控制、质量门与恢复

## 实时任务控制（v2 框架 · 五环节）

```text
①锚定环 Anchor：Run 建立 intent anchor（resolved requirement → intent-anchor.json）
   ——「需求至上」准绳基准 ✅
②进度环 Progress：K0-K10 checkpoint（轻量）+ 输入 checksum → fingerprint 恢复（stale → needs_review）✅
③监督环 Oversight：双准绳偏差（需求至上 vs intent / 习惯为主 vs core）→ deviation 分级
   low 记录纠偏 · medium 暂停确认（needs_user_input）· high 阻断（blocked）✅
④质量环 Gates：intent/data/calculation/delivery 四门全过才 completed（强制校验）；计算门 → resolve caliber ✅
⑤信号环 Signals：K2/K8/K10 + 任意纠正 → record --correction → episodic → 监督消化 → core 回流双准绳 ✅
   + 输出审计：record-output / confirm-output → manifest 血缘 + lineage ✅
```

### 状态联动

```text
created → running → waiting_review | needs_user_input（medium）· blocked（high）→ completed（四门全过）
completed/failed/cancelled 终态不可修改；resume 按 fingerprint：未变继续 / stale → needs_review 只重跑受影响步骤
```

### 职责边界（各司其职）

- 不存储决策（working 归缓存记忆区）；不审批（裁决权归自我进化监督）；不解决知识（卡点 → BRF）；
- 偏差分级单一真源（实时控制）；L1/L2/L3 分级归监督；进化评分归 BRF——互不调用；
- 四门计算门校验借用 BRF `resolve --need-type caliber`（接口复用，非职责混用）。

## 状态事实

`state.json` 保存当前 status、task/deliverable 版本、current_step、steps、gates、awaiting、last_checkpoint、resume_from、stale 和 history。`manifest.json` 只保存文件血缘；`intent-anchor.json` 只保存本次确认目标；`deviations.json` 只保存偏差。

## 状态转换

```text
created → running | waiting_dependency | cancelled
running → waiting_review | needs_user_input | needs_review | blocked | failed | partial | completed | cancelled
waiting_review/needs_review → running | needs_user_input | completed（仅门通过）
needs_user_input/blocked/failed/partial → running | cancelled
completed/failed/cancelled → 不可修改
```

`completed` 必须满足四道门均为 `passed`，并有输出和 manifest；`delivered` 还必须有 DeliverableRun 的输出 checksum 和 lineage。

## 关键节点

K0 请求理解、K1 工作包、K2 需求确认、K3 任务/交付物计划、K4 流程/工具、K5 取数、K6 分析、K7 草稿、K8 四门、K9 交付、K10 反馈。节点记录轻量 checkpoint，不为普通函数调用制造噪声。

**检查点三处衔接（不漂移）**：3c 定义「过程检查」（什么值得查）→ 第 6 步落「执行时点与验证动作」（在哪步查）→ 7a 执行时写 checkpoint 记录结果（K 节点）。落点纪律：状态变更前记录，防崩溃重复执行产生重复副作用。

## 偏差

low 可记录并纠偏；medium 暂停确认；high 阻断当前分支。偏差必须含 expected、actual、category、severity、action、status 和 evidence；支持 resolve，不得静默删除。**high 阻断 = 阶段回退链入口**：阻断后按四门失败类型 + evidence 结构化归因（category=rollback），回根因阶段修正后增量重走；同一 WorkOrder 回退上限 2 次，超限升级人工或新 WorkOrder。

**双准绳判据（监督基准）**：
- ①需求至上——与 intent anchor（用户本轮明确需求）冲突 → 至少 medium 暂停确认；涉及范围、关键映射、外发 → high 阻断；
- ②习惯为主——与 core 记忆（用户跨任务稳定偏好）冲突 → 默认纠偏回习惯；用户本轮明确改变时以本轮为准。

**用户信号实时记录**：K2 确认、K8 四门、K10 反馈及任意时刻的用户纠正 → `supervisor.py record --correction "<纠正内容>"` 入 episodic（不可变事件），供监督层跨 Run 评估。

## 恢复

checkpoint 不覆盖，保存输入文件 checksum。resume 重新计算 fingerprint：未变则继续，已变则 stale → needs_review，只重跑受影响步骤。终态不允许 resume。

## 四道门

- intent：与 anchor 的目标、周期、范围、口径一致。
- data：来源、覆盖、批次、去重和缺失可解释。
- calculation：公式、汇总率、目标合计、异常值通过复核。
- delivery：格式、公式、缺失标识、路径、血缘和敏感信息正确。

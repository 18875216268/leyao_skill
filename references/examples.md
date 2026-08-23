# 完整走查示例

```text
用户请求：完成集团本周模板，并生成项目专项复盘
```

1. `init-work-order` 保存请求；`inspect/build-package` 识别模板、数据、历史样例和控制文件。
2. 用户确认周期、范围、模板字段和缺失数据策略，写入 intent anchor。
3. 创建两个 Task：`project-progress`、`issue-analysis`；创建两个 Deliverable：
   - `weekly-report`：kind=report/type=weekly
   - `project-review`：kind=retrospective/type=special
4. 两个 Deliverable 都通过 bindings 引用两个 Task 的 confirmed 输出，形成多对多关系。
5. 抽象流程后注册 openpyxl/pandas 等 capability，生成 tool plan 和 fallback。
6. 创建 runtime Run，写 state、manifest、anchor、working memory、raw/clean/analysis/checkpoints。
7. K5 取数、K6 分析、K7 生成模板副本和复盘草稿；所有输入写 checksum。
8. 若发现范围从 A 区域变成全量，写 high deviation 并阻断；用户确认后新建 anchor 版本或修正。
9. Task 输出在 result/confirmed 后，DeliverableRun 才能 create/stage。
10. 四道门全部 passed，DeliverableRun 从 pending-review → confirmed → delivered，写 output checksum 和 lineage。
11. 记录 episodic 用户修正；监督层生成 proposal。批准后才更新模板映射或 core 偏好。

## 4→5→6 迷你走查（project-progress Task 片段）

**第 4 步抽象流程**：流程模式 = chaining（固定串行）+ 并行组（多源取数）。
```text
step1 取数（多源）      in: raw/*.xlsx                    out: step1.raw_rows   [parallel: 出库+毛利两源]
step2 清洗              in: step1.raw_rows                out: step2.clean_rows  validation: 行数/缺失率达标
step3 指标计算          in: step2.clean_rows               out: step3.metrics      validation: 口径对上期（计算门）
step4 渲染模板          in: step3.metrics + template       out: step4.draft       失败策略: 自纠正→降级→升级
```

**第 5 步能力规划**：候选 openpyxl/pandas → 六维比较 → 收敛 ≤5 → 主选 pandas + fallback（openpyxl 只读 + 手工校验）；能力描述含"何时用/何时不用"。

**第 6 步可执行流程**：逐条映射——step2 → `python <第 5 步选定的清洗脚本> --in <raw> --out clean/`（tool_choice=required，重试 2 次/超时 120s）；step3 前写 checkpoint（变更前），不可逆外发动作后置 + 确认。

## 阶段回环示例（handoff + rollback）

**handoff 前向通知**：第 1 步探查发现「出库数据源 A 需 VPN 凭证，本地未配置」——本步不取数用不到，但第 5 步选型要用 → 记 handoff：`{from_step:"1", to_step:"5", info:"数据源 A 需 VPN 凭证，本地未配置", source_ref:"materials/出库清单.xlsx", confidence:"medium", status:"pending"}` → 第 5 步选型时自动带上该信息，取数工具选型直接准备 fallback（本地快照/BI 查询），不重复踩坑。

**rollback 按根因回退**：7b 计算门失败——`缺货率` 与上期口径不一致（本期按"期末库存"算，上期按"期初+入库-出库"算）→ 结构化归因：计算门失败 + 口径不符 → 根因第 2 步 → 回第 2 步 `resolve --need-type caliber` 补口径 → 重签 sign-off → 增量重走 3a-7c（第 1 步产物不变保留）；写 deviation（category=rollback, evidence="缺货率口径与上期不一致"），回退计数 +1。

验证重点：旧 reports 只读兼容；未确认 Task 输出不能进入交付物；终态不可改；输入变化恢复进入 needs_review；重复 ID、路径逃逸、DAG 环和未知 schema 关键字失败；流程模式未声明或数据流引用断链视为第 4 步未完成；handoffs 条目缺契约字段或回退超 2 次视为越权。

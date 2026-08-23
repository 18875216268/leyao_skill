# 工作区与工作包

## 外部工作区

```text
<work-dir>/
├── shared/
├── work-orders/{id}/
├── tasks/{task-id}/                 # Task 定义和确认结果
├── deliverables/{deliverable-id}/   # 新交付物事实和结果
├── runtime/runs/{run-id}/           # 新 Run canonical 事实
├── memory/{episodic,semantic,core}/
├── capabilities/
├── scheduler/{schedules,history}/
├── proposals/
├── audit_log/
└── archive/
```

## WorkOrder 目录

```text
work-orders/{id}/
├── work-order.json
├── requirement.json
├── workspace-package.json
├── dependency-graph.json
├── orchestration-state.json
├── intent-anchor.json
├── checkpoints/
└── decisions/
```

## Run 目录

新运行统一写入：

```text
runtime/runs/{run-id}/
├── index.json
├── state.json
├── manifest.json
├── intent-anchor.json
├── deviations.json
├── checkpoints/
├── input/
├── raw/
├── clean/
├── analysis/
├── scripts/
├── temp/
├── memory/
└── tool-logs/
```

## 工作包理解

工作包是目录、输入材料、控制文件、历史成果、脚本、配置及关系的集合。先做目录和文件事实清单，再按需理解 Excel/Word/PDF/PPT/数据/脚本。角色候选必须带 confidence 和 evidence：`control_file`、`output_template`、`raw_data`、`historical_example`、`analysis_result`、`script`、`reference_material`、`unknown`。**角色确认点（反馈机制）**：关键角色（`output_template`/`control_file`）且 confidence < 0.9 时，生成角色确认清单给用户核对（文件/判定角色/confidence/疑点），确认状态写入 workspace-package.json；高置信直接采用，不打扰。

`inspect` 必须只读：不创建目录、不跟随 symlink 越界、不移动、不重命名、不覆盖。低置信目录只生成 reuse 建议和未分类清单。

## Task 四区

```text
tasks/{task-id}/
├── process/                       # 定义、计划、映射、决策、复核
├── result/{pending-review,confirmed,delivered}/
└── archive/
```

交付物也有自己的 `deliverables/{id}/result/{pending-review,confirmed,delivered}`；Task 结果和 Deliverable 结果不混放。

## 血缘

`manifest.json` 记录输入/输出路径、checksum、Task/Run/Deliverable 版本、活动和来源。报告或复盘只能从 confirmed/delivered 结果建立血缘。

# 缓存、上下文预算与缓存治理

缓存层是总框架下的横切基础设施，用于减少重复文件理解、模板结构理解、流程/工具规划、确定性分析和记忆注入的 token 消耗。它不替代用户确认、意图锚点、偏差处理、权限审批、四道质量门或 confirmed/delivered 生命周期。

## 目录

```text
runtime/cache/
├── entries/          # cache_entry 元数据
├── payloads/         # 仅结构化 JSON 派生结果
├── invalidations/    # 失效记录
├── governance/       # 缓存治理评分和决策
└── indexes/          # 可选索引

runtime/runs/{run-id}/context/pack.json
```

缓存目录位于 `runtime/`，工作区 inspect 将整个 runtime 视为系统管理区，不会误识别为用户输入材料。

## 可缓存内容

| namespace | 内容 | 自动复用条件 |
|---|---|---|
| workspace | 目录/材料事实和角色候选 | 文件内容、扫描策略、深度、角色规则未变 |
| artifact/template | 文件结构、sheet、表头、公式、占位符候选 | 文件 checksum、解析器和映射策略未变 |
| plan/tool-plan | 抽象流程、工具候选、fallback | Task/Workflow/Deliverable、能力注册、风险策略、intent 未变 |
| analysis | 可复算清洗、去重、汇总和结构化结果 | 输入 checksum、范围、公式、脚本、参数未变 |
| context | 当前 Run 有效上下文摘要 | 实际选入内容、预算、来源版本、intent 未变 |
| supervision | 事件统计摘要 | profile、事件 ID 集合、策略版本未变 |
| draft | 报告/复盘草稿候选 | confirmed 输入、模板、scope、DeliverableSpec、intent 未变 |

模板结构可直接复用；字段语义映射仅作为候选，关键字段、公式、范围和模板映射仍需当前用户确认。

## 缓存键

缓存 key 是规范化 JSON 的 SHA-256，包含：

```text
operation + producer/version + 输入 checksum 集合 + 参数
+ context hash + policy version + 相关 Task/Workflow/Deliverable 版本
```

不包含时间戳、绝对路径、Run ID 或临时路径。它们只能作为审计使用记录。文件引用始终保留相对路径和 checksum 以支持血缘。

## 命中与失效

命中必须满足：entry=ready、payload checksum 正确、输入内容 checksum 不变、producer/policy/context 兼容、质量/权限策略允许。

以下任一项发生变化都应 miss 或 invalid：

```text
输入内容、Task/Workflow/Deliverable/模板版本、intent anchor、范围、公式、脚本、
能力注册表、解析器/策略版本、memory snapshot、context budget、用户确认、deviation。
```

缓存命中只复用派生结果。当前 Run 仍必须写自己的 manifest、lineage、output 和四门状态；DeliverableRun 仍必须 stage → gates → confirmed → delivered。

## 强制旁路

以下情况不读也不写缓存：

```text
sensitive 数据、任意副作用、approval required、联网/登录、覆盖/删除/移动/外发、
低置信映射、未确认输入、实时数据、force refresh、用户要求重新检查、未解决 deviation。
```

旁路返回结构化 reason，并写审计事件。缓存从不保存批准结果，更不会成为长期授权。

## Context pack 与预算

context pack 只包含当前阶段所需摘要：用户本轮要求、intent anchor、当前 Task/Deliverable 规则、工作包摘要、确认结果、有效 memory、少量相关事件和未决问题。完整原文使用 path + checksum + locator 引用，需要时才读取。

默认采用字符预算近似 token。priority=0 的用户要求、意图锚点、阻断项不可裁剪；其余内容按优先级稳定裁剪。预算变化会改变 pack hash，不能命中旧 pack。

## 缓存治理

`cache_governor.py` 对缓存按 usage、recentness、重建成本、活跃引用、lineage 依赖、风险和当前任务相关性评分：

```text
pinned  活跃 Run/Task/Deliverable、当前模板、lineage 或用户明确保留
warm    高频、近期或重建成本高的可复用缓存
cold    低频、可重建、无活跃引用的派生缓存
```

cold 缓存先变为 `evictable`。`prune` 默认 dry-run；实际清理只删除可重建 JSON payload，并保留 entry、治理记录、失效原因和审计。绝不清理原始数据、Task/Deliverable 结果、confirmed/delivered 文件、审计日志、proposal evidence、active checkpoint、pinned 缓存或被 lineage 引用的缓存。

## 入口

```text
python scripts/cache.py key --operation analysis --producer pandas-v1 --inputs '[]' --parameters '{}'
python scripts/cache.py store --work-dir <dir> --namespace analysis --key <sha256-key> --producer pandas-v1 --payload '{}'
python scripts/cache.py lookup --work-dir <dir> --key <sha256-key>
python scripts/cache.py invalidate --work-dir <dir> --key <sha256-key> --reason input_changed
python scripts/context_pack.py build --work-dir <dir> --run-id <id> --budget 12000 --items '[]'
python scripts/cache_governor.py review --work-dir <dir>
python scripts/cache_governor.py prune --work-dir <dir>           # dry-run
python scripts/cache_governor.py prune --work-dir <dir> --apply   # only evictable payloads
```

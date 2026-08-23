# ACS 使用指南（AI 决策手册）

本文档指导 WorkBuddy 判断「**什么情况下用 ACS、怎么问、结果怎么用**」。
ACS 是横切服务：**不绑定执行阶段**，13 执行点主链中谁遇到卡点谁调用 `ask()`。

## 零、核心范式：资产 = 卡点解决方案库，路由 = 三阶段调度

AI 完成任务遇到不懂/卡点 → `ask()` 按**三阶段调度**寻找解决方案（不是按类型单选数据源）：

```
卡点/问题
  → 阶段 1 · 基石（并发）：本地 K1（cache 优先——已吸收各源答案，命中即早停）
      ‖ 公域 K2.5（高质量源，三层闸过滤；cache 未命中必读）
  → 阶段 2 · 并行补缺（线程池）：K2/K3 运营库+云智库 ‖ 动态工具域（注册+本机发现）
  → 阶段 3 · 网络层 AI 自助引导（仅空结果兜底；--prefetch-network 弱命中可附带）
```

每层命中即返回（带 `path` 记录三阶段尝试）；全部未中 → `unresolved` + 建议。
搜索结果须**与问题相关**（结果名命中问题关键词的 4 字片段）才算解决，否则继续降级。
`early_stop:true` = 本地 cache 快路径命中（已吸收各源，省时省成本）；复杂问题用 `resolve --expand` 强制全收集。

**进化闭环**：解决成功后 `learn`（蒸馏/评分/分流）→ shared 进公共池、personal 仅本地 → 下次阶段 1 直接命中；用户交互中确认的新认知同样走 learn。

## 一、什么时候用 ACS（触发判断）

| 场景 | 示例问句（AI 内部转述） | need_type（自动识别） |
|---|---|---|
| 遇到不认识的业务名词 / 不确定用户意图 | 「缺货率是什么」「TOP3000 是什么意思」 | term |
| 确认指标口径 / 计算公式 | 「成本优势率怎么算」「毛利缺口口径」 | caliber |
| 需要制度/课程/文档资料 | 「查一下毛利制度」「搜采购部制度」 | tool |
| 需要分析方法指导 | 「怎么做 ABC 分析」「库存周转怎么分析」 | process |
| 需要报表/复盘模板 | 「周报模板」「复盘格式」 | template |
| 需要参考数据/基准 | 「上季度毛利率多少」「客户数统计」 | data |
| 需要子公司/组织信息 | 「帝豪公司是哪里的」「子公司清单」 | term（走公司表） |

判定总原则：**先问"这能不能从知识库/云智库得到答案"**，能 → ask()；纯闲聊/主观问题 → 不用。

## 二、怎么调用

```bash
# 不指定类型 → 自动推断意图 + 分层解决路径（推荐）
python scripts/ask.py --question "成本优势率怎么算"

# 明确类型（歧义时兜底，限定层内策略）
python scripts/ask.py --need-type caliber --question "成本优势率"

# 允许 AI 自助联网规划兜底（BRF 不亲自联网，引导 AI 多渠道自助获取）
python scripts/ask.py --question "zzqwxk是什么" --allow-network
# 返回 reason=network_required + guidance_doc=references/network-guidance.md：
# AI 按指引自助规划（判断缺口类型 → GitHub/AI 官方 skill 市场/CSDN/必应等权威源
# → 评估候选 → 下载安装（approval）→ 验证 → 注册资产或沉淀记忆）

# 复杂问题强制全收集（跳过 cache 早停，阶段 1/2 全层收集多可能性）
python brf.py resolve --problem "成本优势率 缺货率 双口径" --expand --work-dir <dir>

# 弱命中时后台预取网络引导（附带 hint，不阻塞主返回）
python brf.py resolve --problem "成本优势率怎么算" --prefetch-network --work-dir <dir>
```

响应字段：`ok / need_type / answer / source / category / trust / confidence / version / path`；
未解决时附加 `reason / hint / suggest / guidance_doc`；三阶段调度附加 `early_stop`。
`path` 记录三阶段尝试（stage1 K1 / stage2 pool·knowledge·tool / stage3 network 各段 ok/source）；
`trust=authority` 才是口径权威；`confidence` 供判断是否需用户确认。

## 三、结果怎么用（8 阶段消费）

| 结果类型 | 消费方式 |
|---|---|
| term/caliber（口径） | 回填 intent anchor 的「口径」字段 → 计算门校验用；`source` 留痕可审计 |
| tool（文档列表） | 取 `answer` 中的 slug → 继续 `leyou_bridge detail <slug>` 拿全文 |
| process（方法论） | 作为分析步骤参考，写入 Task 的 workflow/validation |
| template（模板清单） | 匹配到具体模板 → 作为交付物 template_id |
| data（数据/基准） | 进入 raw/clean 供 analysis 消费（只读，写 manifest） |

## 四、边界与纪律

- **只读消费**：ACS 永不写回知识源；
- **网络/登录**：tool 类走 approval（`network_required=true`），扫码需真人，先 `auto --no-scan` 复用库凭证；
- **缓存**：公共池查询结果走缓存平面（读时回填/写时失效），命中不绕过用户确认与四道门；
- **未命中**：`ok=false` + `reason=no_match` → 转用户确认，**不静默假定**；
- **只认 authority**：口径校验只用 `trust=authority`（注入库 `tier=inject`，ops-glossary/ops-metrics/ops-companies）。

## 五、8 阶段编排锚点

```
0 请求理解    遇到不懂的词 → ask(term) 消歧
2 需求确认    口径/公式 → ask(caliber) 回填 anchor
5 能力规划    需要外部能力 → register-capability 运行时注册 / tools_discovery 动态发现（ACS tool 类）
6 可执行流程  CLI 参数/用法 → ask(tool) 或直接查 api-contract
7 执行交付    取数 K5 → ask(tool/data)；口径复核 → 计算门对照 ask(caliber)
```

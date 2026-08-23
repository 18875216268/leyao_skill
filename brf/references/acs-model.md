# ACS 模型（资产能力服务）

## 一、定位

- 横切**资源服务**平面（与记忆区、缓存平面同类），不是执行链步骤，也不是监控型治理平面；
- 8 个执行阶段均可按需调用 `ask()`，**不绑定任何阶段**；
- 术语边界：第 5 步能力经运行时注册（`register-capability` 写入 work-dir/capabilities/）与 `tools_discovery` 动态发现接入 ACS 能力域，二者不冲突。

## 二、双轴模型

| 轴 | 维度 | 取值 | 作用 |
|---|---|---|---|
| 诉求轴 need_type | 调用方"要什么" | term / caliber / tool / data / template / process | 查询与路由 |
| 资产轴 category | 资源"是什么" | knowledge / tool / method / data / template | 存储与注册 |

- 两轴正交；资产用 `covers_need[]` 声明可服务的诉求；
- 路由引擎完成 `need_type → category → source` 映射。

## 三、双域结构

| 域 | 分类 | 回答 |
|---|---|---|
| 资产域 Assets | knowledge（含 caliber 权威子类）/ data / template / method | "有什么" |
| 能力域 Capabilities | tool / skill / API / 脚本 / 连接器 | "能做什么" |

## 四、分类体系（开放枚举）

| category | 说明 | 样例 |
|---|---|---|
| knowledge | 定义/事实/制度/课程 | 术语表、子公司清单、口径权威子类 |
| tool | 可调用执行的能力 | leyou_cloud.py、云智库采集、BI 查询 |
| method | 过程/分析/SOP | 业务分析方法论、复盘框架 |
| data | 具体数据资产 | 指标基准、报表、字典 |
| template | 可填充骨架 | 日报/周报/复盘模板 |

扩展约定：小写英文 id；新增类别 = 注册分类约定 + 挂 source，接口零改动。

## 五、信任分级

| 级别 | 含义 | 使用规则 |
|---|---|---|
| authority | 权威源（口径只认它） | 默认首选；口径校验必须 authority |
| reference | 参考源 | 降级候选，标注置信 |
| candidate | 候选/待验证 | 仅提示，不参与口径判定 |

## 六、治理钩子（复用现有平面）

| 钩子 | 对接机制 |
|---|---|
| 口径校验 | 计算门（四道门之一） |
| 网络取数 / 登录 | approval（RISKY={network,login,…}） |
| 查询结果 | 缓存平面（内容寻址，checksum 失效） |
| 确认后的口径/模板映射 | 语义记忆（proposal 审批） |

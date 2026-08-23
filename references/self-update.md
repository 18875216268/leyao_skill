# 自主更新（self-update）：发布流程与更新机制

> skill 内置更新模块（`scripts/self_update.py` + `self_update.json`），每次使用自动检查 GitHub main 分支新版本，有新版自动更新。**只替换源码与文档，绝不触碰本地记忆/凭证/登录态/归档**。

## 零、AI 快速使用（直接照做，无需分析）

```bash
python scripts/self_update.py auto
```

一条命令，无任何参数，自动完成：检查远端版本 → 有新版本自动拉取更新（校验递增→备份→原子替换→失败回滚）→ 报告结果。跑完即可继续主任务，之后不用管（更新下次会话生效）。

- 返回"已是最新" → 继续主任务；
- 返回"已自动更新 X → Y" → 更新完成，下次会话生效；
- 网络不可用/未配置 → 直接跳过，不阻塞。

## 一、更新机制（AI 侧 · 每次使用）

1. **自检**：任务开头运行 `python scripts/self_update.py check --json`
   - 网络不可用 → 静默跳过（不阻塞主任务）；
   - 输出三态：`已最新` / `有新版` / `未配置`。
2. **自动更新**：有新版 → `python scripts/self_update.py apply`
   - 下载 `https://codeload.github.com/<repo>/zip/refs/tags/v<tag>`；
   - 校验包内 SKILL.md 版本 **严格高于** 本地（防降级/防重复覆盖）；
   - 备份将被覆盖的文件 → 原子替换（`os.replace`）→ 失败从备份回滚；
   - 更新完成提示"下次会话生效"（当前会话已加载旧版，不中断任务）。
3. **保护红线（apply 绝不覆盖）**：
   - 本地记忆：`.workbuddy/`（记忆/配置/工作日志）；
   - 云端登录态：`.wrangler/`（CF 账号缓存）；
   - 凭证：`leyou_token.json`、`wrangler-account.json`；
   - 归档/数据：`data.json.archive`、`pool_knowledge_dump.json`；
   - 运行产物：`.pyc/.pyo`；更新源配置 `self_update.json` 本身。

## 二、发布流程（维护者侧 · 手动一次）

1. **建仓库**：GitHub 新建仓库（如 `leyao_seed_pro`，public 或 private+token）；
2. **改更新源**：`self_update.json` 的 `repo` 改为 `owner/repo`（如 `yourname/leyao_seed_pro`）；
3. **初始化并推送**：
   ```bash
   cd F:/Dpzhuomian/leyao_seed_pro
   git init && git add . && git commit -m "v12.3.0"
   git remote add origin git@github.com:yourname/leyao_seed_pro.git
   git push -u origin main
   ```
   > 注意：`.workbuddy/`、`.wrangler/`、凭证、归档已在 `.gitignore` 排除（与打包排除清单一致）。
4. **发布版本（每次升级时）**：
   ```bash
   git tag v12.3.0 && git push origin v12.3.0
   ```
   GitHub 自动生成 Release（codeload 可直接拉 `v<tag>` zip）；
5. **验证**：改回旧版本号（或另一台机器）执行 `check` → 应报"有新版"；`apply` → 应更新成功且本地记忆保留。

## 三、不做什么

- 不覆盖本地任何数据/凭证/登录态（保护清单硬编码在 `self_update.py`）；
- 不在任务执行中途强制重启（更新后下次会话生效）；
- 不自动降级（远端版本必须高于本地才允许替换）。

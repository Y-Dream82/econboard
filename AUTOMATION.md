# EconBoard 自动周更使用说明

这个版本把更新流程拆成两层：

1. **自动发现候选**：每周一 08:00（北京时间）由 GitHub Actions 抓取公开资讯，执行去重、关键词过滤和来源初筛。
2. **审核后发布**：候选只进入 `review/candidates.json` 和 `review/weekly-report.md`，不会直接出现在网站；确认真实、有效且面向本科生后，再加入 `config/approved_entries.json`。

这样可以避免新闻报道、往年活动、博士生专场等内容被自动发布，同时减少每周重复检索和打包的工作量。

## 一次性配置

### 1. 上传到 GitHub

把压缩包解压后的全部文件上传至 GitHub 仓库根目录。必须保留：

- `.github/workflows/weekly-update.yml`
- `scripts/weekly_update.py`
- `config/sources.json`
- `config/approved_entries.json`
- `review/candidates.json`
- `index.html`、`data.js`、`netlify.toml`

### 2. 让 Netlify 连接 GitHub

在 Netlify 选择 **Add new site → Import an existing project**，连接该仓库：

- Build command：留空
- Publish directory：`.`

以后 GitHub 有提交时，Netlify 会自动部署，不再需要上传 ZIP。

### 3. 可选：配置 Netlify Build Hook

如果 Netlify 没有开启 Git 自动部署，可在 Netlify 创建 Build Hook，并在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 新建：

- Name：`NETLIFY_BUILD_HOOK`
- Value：Netlify 提供的 Build Hook URL

## 每周怎么操作

1. 打开 `review/weekly-report.md` 查看候选清单。
2. 打开候选的官方页面，核对主办方、年份、截止日期、投稿通道和本科生资格。
3. 将确认通过的完整条目写入 `config/approved_entries.json`。
4. 在 GitHub Actions 页面手动运行一次 **EconBoard 自动周更**；也可以等下周定时任务自动合并。
5. 工作流更新 `data.js` 并提交，Netlify 自动上线。

## 已审核条目格式

```json
{
  "entries": [
    {
      "id": "comp-unique-id",
      "type": "competition",
      "title": "赛事名称",
      "organizer": "主办单位",
      "category": "商科专业",
      "registerEnd": "2026-12-31",
      "eventStart": "2027-01-10",
      "audience": "本科生",
      "officialUrl": "https://example.edu.cn/official-page",
      "sourceName": "主办方官方通知",
      "sourceUrl": "https://example.edu.cn/official-page",
      "summary": "一句话简介",
      "description": "详细说明",
      "location": "线上或具体地点",
      "tags": ["金融", "案例分析"],
      "participationMode": "team",
      "prestigeLevel": "全国性竞赛",
      "prestigeStars": 3,
      "fee": "以官方通知为准"
    }
  ]
}
```

论坛条目的 `type` 改为 `forum`，并建议补充 `forumKind`、`submissionChannel`。日期统一使用 `YYYY-MM-DD`。

## 本地运行

只做格式检查，不访问网络：

```bash
python scripts/weekly_update.py --check
```

执行完整周更：

```bash
python scripts/weekly_update.py
```

## 筛选规则调整

编辑 `config/sources.json`：

- `queries`：每周检索词
- `trusted_domains`：可信来源域名
- `positive_keywords`：有效通知关键词
- `negative_keywords`：新闻总结、旧活动或不适合本科生的排除词
- `max_candidates`：每周最多保留的候选数

## 安全边界

- 自动抓取结果不会直接发布，避免错误信息污染网站。
- 已审核条目按 `id` 更新或新增，不会重复插入。
- `data.js` 会在每次运行后重新校验为标准 JSON。
- 工作流执行失败时不会提交，也不会触发 Netlify 部署。

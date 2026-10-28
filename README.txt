EconBoard Netlify 静态部署包（自动周更版）

直接部署：
1. 将整个目录上传 GitHub。
2. 在 Netlify 连接该 GitHub 仓库。
3. Build command 留空，Publish directory 填英文句点“.”。
4. 每次 GitHub 提交后，Netlify 自动部署。

自动周更：
- 每周一北京时间 08:00 抓取候选资讯。
- 候选写入 review/weekly-report.md，不会未经审核直接展示。
- 审核通过后，把完整条目加入 config/approved_entries.json。
- 详细步骤见 AUTOMATION.md。

手动测试：
- python scripts/weekly_update.py --check
- python scripts/weekly_update.py

网站入口：index.html
数据文件：data.js

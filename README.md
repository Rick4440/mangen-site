# mangen-static-site

株式会社万源 静态站 · 托管于 Cloudflare Pages

## 当前状态（2026-09-23）

✅ 已部署到 CloudStudio 临时预览（迁移到 Cloudflare Pages 前的视觉验证）：

| 路由 | 状态 |
|---|---|
| 日文首页 `/` | ✅ 200 |
| 中文页 `/zh.html` | ✅ 200 |
| 英文页 `/en.html` | ✅ 200 |
| 博客列表 `/blog/` | ✅ 200 |
| 3 篇博客详情页 | ✅ 200 |
| 5 个车型 + 公司信息 JSON | ✅ 200（被 JS 动态渲染） |
| admin 后台入口 `/admin/` | ✅ 200（仅 Cloudflare Pages + GitHub OAuth 可用） |
| sitemap.xml / robots.txt | ✅ 200 |

临时预览链接（仅供评审，**不是生产**）：
**https://c2fb27c3ee7a428cbd32c223543b0301.app.workbuddy.host**

⏳ 等用户完成下列事项后转入 Cloudflare Pages + mangen.jp：
1. J-PlatPat 商标查询
2. Xserver 注册 mangen.jp
3. ✅ **GitHub repo** — `https://github.com/Rick4440/mangen-site`（public，2026-09-23 已推送）
4. Cloudflare 注册

## 架构

```
GitHub repo  →  Cloudflare Pages（自动部署）  →  mangen.jp
                     ↓
              Decap CMS（/admin/）  →  GitHub 写入 /content/*.json + /content/posts/*.md
                     ↓
              Cloudflare Pages Function (/api/contact)  →  Formspree / Resend
                     ↓
              Gmail（mangeninc@gmail.com，表单收件）
```

## 月成本

| 项目 | 金额 |
|---|---|
| Cloudflare Pages 托管 | ¥0 |
| Cloudflare DNS | ¥0 |
| Decap CMS | ¥0 |
| Formspree 免费档 | ¥0（50 条/月） |
| Gmail 收件 | ¥0 |
| .jp 域名 (onamae.com) | ¥3,800/年 ≈ ¥317/月 |
| **合计** | **约 ¥317/月** |

## 内容管理

后台地址：https://mangen.jp/admin/

| 集合 | 说明 |
|---|---|
| 公司信息 | 电话、地址、资质、邮箱、Schema |
| 车型 | 增删改车型 |
| 博客文章 | 新增 / 编辑 / 删除文章 |
| 博客列表索引 | 新增文章时必须同步登记 |

## 旅行指南 · 主题

列表上的旅行主题只有六个，和目的地筛选一样排成一行：行程路线、交通接送、住宿美食、购物退税、季节活动、礼仪与生活。新文章在 front matter 或后台的 `topic` 里写其中一个。路线、景点介绍和城市攻略都归「行程路线」；交通、包车、机场和出入境都归「交通接送」。留空时，分类 a/c 归交通接送，d 归行程路线，b/e 归礼仪与生活。旧名称（目的地攻略、景点行程、交通与接送、交通出行、机场与出入境）在构建时会自动并入对应的新主题。文章网址不随主题改变。

## 旅行指南 · 每日精选

中文首页的「旅行指南」和 `/blog/` 的「编辑精选」使用同一个函数，版式都是一篇大卡片加四篇小卡片。日文和英文首页没有这一栏。选择只看日本日历日期：同一天多次构建结果相同，第二天换成另外五篇。五篇链接写在 HTML 里，不靠浏览器脚本替换。

候选是已发布、并且有可用封面图（png / jpg / webp / gif / avif）的文章。没有封面的文章不进入这五篇。排序优先内部链接更少的文章，其次是更早发布的文章，这样轮换把首页和精选的链接送到档案里较少被提到的文章，而不是一直停在最新几篇。内部链接统计正文里的 `/blog/…` 链接，以及每篇文章「相关阅读」的三篇；正在选出的这五篇本身不计入。`/blog/` 下面的「全部指南」仍按发布日期从新到旧排列，不参与这套轮换。

有封面的文章超过五篇时，当天的五篇和前一天的五篇不会相同。不足五篇时，有几篇显示几篇。`featured` 不再决定这五篇，只在相关阅读的其他条件相同时略为靠前。

没有新文章提交的日子，由 GitHub Actions 在每天日本时间 00:05 触发一次 Cloudflare Pages 构建。构建命令会重新运行 `scripts/build.py`，爬虫看到的是构建结果里的静态链接。定时任务要在本文件进入 `main` 之后才会按点运行。接入步骤见 `docs-deploy.md` 的「每日精选轮换」。

## 部署

参见 `docs/deployment-playbook.md`（Cloudflare Pages 版）。

## ⏳ 上线前必替换的占位符

`admin/config.yml` 里（**已替换**）：
- ✅ `YOUR_GITHUB_USER` → `Rick4440`
- ✅ `mangen-static-site` → `mangen-site`

`functions/api/contact.js` 里：
- ⏳ `YOUR_FORMSPREE_ID` → 在 formspree.io 注册后获取（50 条/月免费）

`content/settings/company.json` 里：
- ⏳ `mangen.example.com` → 替换成真实域名（mangen.jp 注册后）
- ⏳ channels 里的 `value: "準備中"` → 真实 LINE/WeChat/WhatsApp ID

## 目录结构

```
mangen-static-site/
├── index.html / zh.html / en.html      三语首页
├── blog/                                博客（4 个文件）
├── admin/                                Decap CMS 后台
│   ├── index.html
│   └── config.yml
├── content/                             Decap 写入（Git 同步）
│   ├── settings/company.json
│   ├── fleet/fleet.json
│   └── posts/*.md + _index.json
├── functions/api/contact.js             Cloudflare Pages Function（表单）
├── assets/                              静态资源（CSS/JS/IMG）
├── _headers                             Cloudflare Pages 缓存策略
├── wrangler.toml                        Pages 配置
├── sitemap.xml / robots.txt
└── docs/deployment-playbook.md          部署手册（根目录软链 → ../../docs/）
```

更新：表单收件邮箱为 `mangeninc@gmail.com`；域名尚未注册，Cloudflare 账号尚未连接。最新的构建与验收步骤参见 `docs-deploy.md`。

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
2. onamae.com 注册 mangen.jp
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
              Zoho Mail（域名邮箱 info@mangen.jp）
```

## 月成本

| 项目 | 金额 |
|---|---|
| Cloudflare Pages 托管 | ¥0 |
| Cloudflare DNS | ¥0 |
| Decap CMS | ¥0 |
| Formspree 免费档 | ¥0（50 条/月） |
| Zoho Mail 免费 | ¥0（5 用户） |
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
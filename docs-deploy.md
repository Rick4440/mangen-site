# 万源上线与日常更新

## Cloudflare Pages

连接 GitHub 仓库 `Rick4440/mangen-site`，生产分支 `main`。选择无框架预设，构建命令 `python -m pip install -r requirements.txt && python scripts/build.py`，输出目录 `.`。构建失败时不要部署旧页面。部署后检查 `/blog/` 和三篇文章的网页源代码含正文。

将 `mangen.jp` 绑定到 Pages，并在域名完成注册、DNS 生效后检查 HTTPS、`/robots.txt` 和 `/sitemap.xml`。在此之前，canonical 中的正式域名并不代表它已开通。

## 指南订阅与 IndexNow

`/blog/feed.xml` 是最新 50 篇旅行指南的 Atom 订阅。文章页和 `/blog/` 用 `<link rel="alternate">` 指向它。sitemap 里文章的 `lastmod` 使用 `+09:00` 的完整时间。稿件目前只写了日历日期，没有钟点，因此时间取该日日本时间 00:00，不用构建时刻冒充更新时间。

推送到 `main` 后，GitHub Actions 工作流 IndexNow（`.github/workflows/indexnow.yml`）用本次提交的 `sitemap.xml` 和上一次提交里的 `sitemap.xml` 比较，把新增或 `lastmod` 变了的 URL POST 到 `https://api.indexnow.org/indexnow` 和 `https://www.bing.com/indexnow`。返回 200 或 202 算成功；其他状态会把响应正文写进日志并让这一步失败。运行器不请求 `mangen.jp`。站点根目录的 `e61e8cdfd15dbe8d1e1c92f0140ffbf1.txt` 是公开校验文件，内容就是文件名。IndexNow 会自己来抓这个文件，所以它必须能被部署出去。不需要再设 GitHub Actions 密钥。

手动运行时没有「上一次提交」，会提交 sitemap 里的全部 URL。定时轮换如果只在 Cloudflare 上重建、不产生新的 Git 提交，不会触发这次提交。

## 每日精选轮换

中文首页「旅行指南」和 `/blog/`「编辑精选」的五篇链接是构建时写进 HTML 的。Cloudflare Pages 的构建命令必须保持为 `python -m pip install -r requirements.txt && python scripts/build.py`，输出目录 `.`。只重新部署仓库里现成的 HTML、不跑这个构建，日期不会变，五篇也不会变。

没有新提交的日子，用 GitHub Actions 在日本时间 00:05 调用 Cloudflare Pages 的部署钩子。仓库里的工作流是 `.github/workflows/daily-guide-rotation.yml`。它不改 Git 历史。钩子地址是密钥，不要写进仓库。

Rick 需要做的设置：

1. Cloudflare 控制台打开 **Workers & Pages → mangen-site → Settings → Builds → Deploy hooks**。
2. **Create deploy hook**。名称填 `daily-guide-rotation`，要构建的分支选 `main`。
3. 复制生成的 URL。形式是 `https://api.cloudflare.com/client/v4/pages/webhooks/deploy_hooks/` 后面接一串 id。
4. GitHub 打开 `Rick4440/mangen-site` → **Settings → Secrets and variables → Actions → New repository secret**。
5. Name 必须是 `CLOUDFLARE_PAGES_DEPLOY_HOOK`。Value 粘贴上一步的完整 URL。
6. 确认 Pages 生产分支是 `main`，构建命令和输出目录与上文一致。
7. 把包含该工作流的提交合并到 `main`。GitHub 的定时任务只对默认分支上的工作流生效，合并前不会在 00:05 运行。
8. 合并后到 **Actions → Daily guide rotation → Run workflow** 手动跑一次。成功时 Cloudflare 上会出现一次新的 `main` 部署。密钥没配时，这一步会失败并提示缺少 `CLOUDFLARE_PAGES_DEPLOY_HOOK`。

定时表达式是 `5 15 * * *`（UTC 15:05，即日本时间 00:05）。GitHub 的定时任务偶尔会晚几分钟；构建用的是运行当时的日本日期。

## 咨询表单

网页表单使用 Web3Forms，三语首页的 `access_key` 对应“万源官网咨询”表单，通知收件人是 `mangeninc@gmail.com`。表单由浏览器直接提交，提交成功以 Web3Forms JSON 的 `success: true` 为准。发布后从正式网页真实提交一次，在 Web3Forms Submissions 及 Gmail 收件箱同时核对；无法送达时页面保留邮件草稿入口。旧 `/api/contact` 的 Formspree 转发接口已不再被前端调用。

对外邮箱 `info@mangen.jp` 已由 Cloudflare Email Routing 转发至 `mangeninc@gmail.com`，并已用另一邮箱发信测试成功（初次邮件进入垃圾邮件）。网站展示地址及表单失败时的邮件草稿地址均使用 `info@mangen.jp`；Web3Forms 表单通知仍直接发送至 Gmail。请在 Gmail 中把测试邮件标记为“非垃圾邮件”，并检查后续真实咨询能否进入收件箱。转发仅解决收信；需要以 `info@mangen.jp` 发信还需另配 SMTP 发信服务。

## 文章发布

后台将 Markdown 写入 `content/posts/`；每篇必须使用英文短横线 slug、中文标题与摘要、发布日期及正文。每次 GitHub 提交触发 Pages 构建，脚本自动更新文章页、列表与 sitemap，无须手动维护 `_index.json`。正式环境可删除旧索引数据。

CMS 地址：`https://mangen.jp/admin/`。GitHub 登录由 Pages Functions 的 `/api/auth` 和 `/api/callback` 提供。用有仓库写入权限的 GitHub 账号创建 OAuth App：Homepage URL `https://mangen.jp/`，Authorization callback URL **必须是** `https://mangen.jp/api/callback`。如果之前创建的 OAuth App 使用 `mangen-site.pages.dev`，先在 GitHub 开发者设置中改回调网址。将 Client ID 和 Client Secret 分别设为 Pages 项目**生产环境**变量 `GITHUB_CLIENT_ID`、`GITHUB_CLIENT_SECRET`；Secret 选择加密，不要写进仓库或聊天。注意两个变量值不同；更新生产环境变量后必须重新部署，才能供 Pages Functions 使用。重新部署后用有仓库写入权限的 GitHub 账号登录后台，新增文章并保存，核查 GitHub 提交和 Pages 构建。Cloudflare Pages 的 GitHub 部署授权不能替代 CMS 登录。请从 `mangen.jp` 登录，避免预览域名与正式域名之间的弹窗来源不一致。

## 上线验收

逐页检查日中英首页、手机导航与 Logo；核对资质、地址、电话和车型；测试表单成功与失败两种情况；查看文章 HTML 源码、索引和 sitemap；接入 Google Search Console 并提交 sitemap。日常更新建议每月发布一篇经事实核查的用车或路线文章，并复核旧路线的营业时间、交通与法规信息。

## 域名与公司邮箱

域名 `mangen.jp` 已注册并接入 Cloudflare DNS；网站通过 Cloudflare Pages 托管。已启用 `info@mangen.jp` 转发至 Gmail 收件。Logo 使用现有资源，待新设计完成再替换。

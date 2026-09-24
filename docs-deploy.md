# 万源上线与日常更新

## Cloudflare Pages

连接 GitHub 仓库 `Rick4440/mangen-site`，生产分支 `main`。选择无框架预设，构建命令 `python -m pip install -r requirements.txt && python scripts/build.py`，输出目录 `.`。构建失败时不要部署旧页面。部署后检查 `/blog/` 和三篇文章的网页源代码含正文。

将 `mangen.jp` 绑定到 Pages，并在域名完成注册、DNS 生效后检查 HTTPS、`/robots.txt` 和 `/sitemap.xml`。在此之前，canonical 中的正式域名并不代表它已开通。

## 咨询表单

网页表单使用 Web3Forms，三语首页的 `access_key` 对应“万源官网咨询”表单，通知收件人是 `mangeninc@gmail.com`。表单由浏览器直接提交，提交成功以 Web3Forms JSON 的 `success: true` 为准。发布后从正式网页真实提交一次，在 Web3Forms Submissions 及 Gmail 收件箱同时核对；无法送达时页面保留邮件草稿入口。旧 `/api/contact` 的 Formspree 转发接口已不再被前端调用。

对外邮箱待 Cloudflare Email Routing 把 `info@mangen.jp` 转发至 `mangeninc@gmail.com` 并用另一邮箱发信测试成功后，才在 `content/settings/company.json` 和 `assets/js/main.js` 替换网页显示及回退邮件地址。转发仅解决收信；需要以 `info@mangen.jp` 发信还需另配 SMTP 发信服务。

## 文章发布

后台将 Markdown 写入 `content/posts/`；每篇必须使用英文短横线 slug、中文标题与摘要、发布日期及正文。每次 GitHub 提交触发 Pages 构建，脚本自动更新文章页、列表与 sitemap，无须手动维护 `_index.json`。正式环境可删除旧索引数据。

CMS 地址：`https://mangen.jp/admin/`。GitHub 登录由 Pages Functions 的 `/api/auth` 和 `/api/callback` 提供。用有仓库写入权限的 GitHub 账号创建 OAuth App：Homepage URL `https://mangen.jp/`，Authorization callback URL **必须是** `https://mangen.jp/api/callback`。如果之前创建的 OAuth App 使用 `mangen-site.pages.dev`，先在 GitHub 开发者设置中改回调网址。将 Client ID 和 Client Secret 分别设为 Pages 项目**生产环境**变量 `GITHUB_CLIENT_ID`、`GITHUB_CLIENT_SECRET`；Secret 选择加密，不要写进仓库或聊天。注意两个变量值不同；更新生产环境变量后必须重新部署，才能供 Pages Functions 使用。重新部署后用有仓库写入权限的 GitHub 账号登录后台，新增文章并保存，核查 GitHub 提交和 Pages 构建。Cloudflare Pages 的 GitHub 部署授权不能替代 CMS 登录。请从 `mangen.jp` 登录，避免预览域名与正式域名之间的弹窗来源不一致。

## 上线验收

逐页检查日中英首页、手机导航与 Logo；核对资质、地址、电话和车型；测试表单成功与失败两种情况；查看文章 HTML 源码、索引和 sitemap；接入 Google Search Console 并提交 sitemap。日常更新建议每月发布一篇经事实核查的用车或路线文章，并复核旧路线的营业时间、交通与法规信息。

## 域名与公司邮箱

域名 `mangen.jp` 已注册并接入 Cloudflare DNS；网站通过 Cloudflare Pages 托管。先保留 Gmail 收件；是否启用域名邮箱可在正式上线后决定。Logo 使用现有资源，待新设计完成再替换。

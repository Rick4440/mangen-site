# 万源上线与日常更新

## Cloudflare Pages

连接 GitHub 仓库 `Rick4440/mangen-site`，生产分支 `main`。选择无框架预设，构建命令 `python -m pip install -r requirements.txt && python scripts/build.py`，输出目录 `.`。构建失败时不要部署旧页面。部署后检查 `/blog/` 和三篇文章的网页源代码含正文。

将 `mangen.jp` 绑定到 Pages，并在域名完成注册、DNS 生效后检查 HTTPS、`/robots.txt` 和 `/sitemap.xml`。在此之前，canonical 中的正式域名并不代表它已开通。

## 咨询表单

在 Formspree 创建表单，收件人设为 `mangeninc@gmail.com` 并验证该邮箱，在 Pages 生产环境变量设置 `FORMSPREE_ENDPOINT` 为完整的 `https://formspree.io/f/...` 地址。实际提交一次并核查邮箱收到内容。未配置时接口返回 503，页面提示访客电话联系。

## 文章发布

后台将 Markdown 写入 `content/posts/`；每篇必须使用英文短横线 slug、中文标题与摘要、发布日期及正文。每次 GitHub 提交触发 Pages 构建，脚本自动更新文章页、列表与 sitemap，无须手动维护 `_index.json`。正式环境可删除旧索引数据。

Decap CMS GitHub backend 需要独立的 GitHub OAuth 服务；Cloudflare Pages 的 GitHub 部署授权不能替代它。在认证服务设置完成前，管理员可先直接在 GitHub 编辑文章。不要将 OAuth client secret 写进仓库。上线前需实际验证 `/admin/` 登录、保存和重新部署。

## 上线验收

逐页检查日中英首页、手机导航与 Logo；核对资质、地址、电话和车型；测试表单成功与失败两种情况；查看文章 HTML 源码、索引和 sitemap；接入 Google Search Console 并提交 sitemap。日常更新建议每月发布一篇经事实核查的用车或路线文章，并复核旧路线的营业时间、交通与法规信息。

## 域名与公司邮箱

域名拟在 Xserver 注册，注册完成后在 Cloudflare 添加站点，按 Cloudflare 给出的两条名称服务器到注册商后台修改。先保留 Gmail 收件；是否启用域名邮箱可在正式上线后决定。Logo 使用现有资源，待新设计完成再替换。

"""Build output contracts; each test runs the actual static generator in isolation."""
from datetime import date, timedelta
from pathlib import Path
from html import escape
from html.parser import HTMLParser
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.items = []; self.feed(source)
    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))
    def attrs(self, tag, **filters):
        return [attrs for name, attrs in self.items if name == tag and all(attrs.get(k) == v for k,v in filters.items())]
    def cards(self):
        return [attrs for tag, attrs in self.items if tag == 'a' and 'guide-card' in attrs.get('class', '').split()]

class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        for name in ['scripts', 'content', 'blog', 'assets']:
            shutil.copytree(ROOT / name, self.root / name)
        self.original = sorted(p.stem for p in (self.root / 'content/posts').glob('*.md'))
    def tearDown(self): self.tmp.cleanup()
    def build(self):
        subprocess.run(['python3', 'scripts/build.py'], cwd=self.root, check=True, capture_output=True, env=os.environ.copy())
    def read(self, name): return (self.root / name).read_text()
    def extra_posts(self, count):
        for i in range(count):
            (self.root / 'content/posts' / f'b-20261001-{i:06}.md').write_text(f'---\ndate: 2026-10-01\ncategory: b\ntitle: "测试指南 {i}"\nexcerpt: "正文摘要"\n---\n## 准备\n内容\n')
    def test_real_cards_and_generated_search_catalog_keep_all_source_urls(self):
        self.build(); index = Elements(self.read('blog/index.html'))
        self.assertEqual(len(index.cards()), min(12, len(self.original)))
        payload = json.loads(self.read('blog/articles.json'))
        self.assertEqual(sorted(p['slug'] for p in payload['posts']), self.original)
        self.assertEqual(payload['perPage'], 12)
        for slug in self.original:
            self.assertTrue((self.root / f'blog/{slug}.html').is_file())
            self.assertIn(f'https://mangen.jp/blog/{slug}', self.read('sitemap.xml'))
    def test_pagination_has_real_links_distinct_canonicals_and_no_overlap(self):
        self.extra_posts(20); self.build()
        total = len(self.original) + 20
        routes = ['blog/index.html'] + [f'blog/page/{n}/index.html' for n in range(2, math.ceil(total / 12) + 1)]
        self.assertTrue((self.root / routes[1]).exists(), 'More than 12 posts must produce page 2')
        all_urls=[]; descriptions=[]
        for i, route in enumerate(routes, 1):
            page = Elements(self.read(route)); cards = page.cards(); all_urls += [c['href'] for c in cards]
            self.assertEqual(len(cards), min(12, total - (i - 1) * 12))
            canonical='https://mangen.jp/blog/' if i==1 else f'https://mangen.jp/blog/page/{i}/'
            self.assertEqual(page.attrs('link', rel='canonical')[0]['href'], canonical)
            self.assertIn(canonical, self.read('sitemap.xml'))
            description = page.attrs('meta', name='description')[0]['content']
            self.assertEqual(page.attrs('meta', **{'property': 'og:description'})[0]['content'], description)
            descriptions.append(description)
            if i > 1:
                self.assertIn(f'第 {i} 页。', description)
        self.assertEqual(len(descriptions), len(set(descriptions)))
        self.assertEqual(len(all_urls), total)
        self.assertEqual(len(set(all_urls)), total)
        self.assertIn('href="/blog/page/2/"', self.read(routes[0]))
        self.assertIn('href="/blog/"', self.read(routes[1]))
    def test_repeat_build_is_identical_and_removed_posts_remove_stale_pages(self):
        self.extra_posts(20); self.build()
        before={str(p.relative_to(self.root)):p.read_bytes() for p in (self.root/'blog').rglob('*') if p.is_file()}
        self.build()
        after={str(p.relative_to(self.root)):p.read_bytes() for p in (self.root/'blog').rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        for path in (self.root/'content/posts').glob('b-20261001*.md'): path.unlink()
        self.build()
        stale_page = math.ceil(len(self.original) / 12) + 1
        self.assertFalse((self.root/f'blog/page/{stale_page}/index.html').exists())
        self.assertFalse((self.root/'blog/b-20261001-000000.html').exists())
    def test_filters_are_grounded_and_no_mock_articles_exist(self):
        self.build(); source=self.read('blog/index.html')
        self.assertIn('data-filter="destination"', source)
        catalog = json.loads(self.read('blog/articles.json'))['posts']
        expected = {destination for post in catalog for destination in post['destinations']}
        buttons = Elements(source).attrs('button', **{'data-filter': 'destination'})
        desktop = [item['value'] for item in buttons if item['value']]
        self.assertEqual(desktop, ['region:东京・关东', 'region:大阪・关西', 'region:京都', 'region:北海道', 'region:冲绳', 'region:其他'])
        more = source.split('aria-label="更多目的地"', 1)[1].split('</select>', 1)[0]
        more_values = [item['value'] for item in Elements(more).attrs('option') if item['value']]
        self.assertEqual(set(more_values), expected)
        self.assertEqual(len(more_values), len(expected), 'No duplicate places in 更多')
        mobile = source.split('>目的地 · 全部</option>', 1)[1].split('</select>', 1)[0]
        mobile_values = [item['value'] for item in Elements(mobile).attrs('option') if item['value']]
        self.assertTrue(set(desktop) <= set(mobile_values))
        self.assertTrue(expected <= set(mobile_values))
        self.assertNotIn('富士山一日游，把风景留给旅途', source)
        self.assertIn('value="京都"', source)
        tags = re.findall(r'class="guide-taxonomy">(.*?)</(?:div|span)>', source)
        self.assertTrue(tags)
        for tag in tags:
            self.assertNotIn(' / ', tag)
        self.assertIn('class="guide-taxonomy">东京<span> · </span>行程路线</div>', source)
        self.assertNotIn('大阪 / 京都 / 奈良', source)
        topic_buttons = [item['value'] for item in Elements(source).attrs('button', **{'data-filter': 'topic'}) if item['value']]
        self.assertEqual(topic_buttons, ['行程路线', '交通接送', '住宿美食', '购物退税', '季节活动', '礼仪与生活'])
        self.assertIn('filter-row--line', source)
        for retired in ('景点行程', '目的地攻略', '交通与接送', '交通出行', '机场与出入境'):
            self.assertNotIn(f'value="{retired}"', source)
        featured = next(post for post in catalog if post['slug'] == 'osaka-kyoto-nara-3days')
        self.assertEqual(featured['regions'], ['大阪・关西', '京都'])
    def test_drafts_never_enter_catalog_and_related_links(self):
        path=self.root/'content/posts'/f'{self.original[0]}.md'; path.write_text(path.read_text().replace('draft: false','draft: true'))
        self.build()
        self.assertFalse((self.root/f'blog/{self.original[0]}.html').exists())
        self.assertNotIn(self.original[0], self.read('blog/articles.json'))
    def test_article_has_summary_toc_and_shared_navigation_without_url_changes(self):
        self.build(); page=self.read('blog/osaka-kyoto-nara-3days.html')
        self.assertIn('class="article-toc"',page)
        self.assertIn('class="article-summary"',page)
        self.assertIn('aria-controls="site-navigation"',page)
        self.assertNotIn('/zh.html',page)
        self.assertIn('href="https://mangen.jp/blog/osaka-kyoto-nara-3days"',page)
    def test_generated_pages_use_four_character_chinese_navigation(self):
        self.build()
        # Reverting a shared navigation label must fail on every generated page.
        for path in (self.root / 'blog').rglob('*.html'):
            with self.subTest(page=path.relative_to(self.root)):
                header = path.read_text().split('</header>', 1)[0]
                for href, label in [('/zh#services', '用车服务'), ('/zh#fleet', '车型阵容'),
                                    ('/blog/', '旅行指南'), ('/zh#contact', '联系我们'),
                                    ('/zh#company', '公司介绍')]:
                    self.assertIn(f'href="{href}">{label}</a>', header)
                self.assertIn('lang="ja" aria-label="日本語">JA</a>', header)
                self.assertIn('lang="zh-CN" aria-label="中文">ZH</a>', header)
                self.assertIn('lang="en" aria-label="English">EN</a>', header)
                self.assertIn('href="/"', header)
                self.assertIn('href="/zh"', header)
                self.assertIn('href="/en"', header)
                self.assertNotIn('日本語首页', header)
                self.assertNotIn('English 首页', header)
                self.assertNotIn('>日本語</a>', header)
                self.assertNotIn('>中文</a>', header)
                self.assertNotIn('>English</a>', header)
    def test_generated_footer_labels_are_consistent_and_keep_destinations(self):
        self.build()
        # Reverting a footer template must fail for all articles or list pages.
        for path in (self.root / 'blog').rglob('*.html'):
            with self.subTest(page=path.relative_to(self.root)):
                footer = path.read_text().split('<footer ', 1)[1].split('</footer>', 1)[0]
                links = Elements(footer).attrs('a')
                if path.name == 'index.html':
                    self.assertEqual([a['href'] for a in links], ['/zh', '/zh#company'])
                    self.assertIn('<a href="/zh#company">公司介绍</a>', footer)
                    self.assertIn('072-275-4665', footer)
                    self.assertIn('info@mangen.jp', footer)
                else:
                    self.assertEqual([a['href'] for a in links], ['mailto:info@mangen.jp', '/zh', '/blog/'])
                    self.assertIn('<a href="/zh">返回首页</a>', footer)
                    self.assertIn('<a href="/blog/">旅行指南</a>', footer)
                    self.assertIn('042-649-9057', footer)
                    self.assertIn('东京・大阪机场接送与包车服务｜以关东、关西为主，其他地区欢迎咨询', footer)
                    self.assertNotIn('大阪・东京', footer)
                    self.assertNotIn('关西、关东', footer)
                    self.assertNotIn('日本全国', footer)
                    self.assertLess(footer.index('072-275-4665'), footer.index('042-649-9057'))

    def test_explicit_optional_metadata_is_used_and_escaped(self):
        self.extra_posts(1); path=self.root/'content/posts/b-20261001-000000.md'
        path.write_text(path.read_text().replace('category: b','category: b\ndestinations: [东京]\ntopic: 季节活动\nfeatured: true\nupdated: 2026-10-02').replace('测试指南 0','测试 &lt;script&gt;指南'))
        self.build(); payload=json.loads(self.read('blog/articles.json')); post=next(p for p in payload['posts'] if p['slug']==path.stem)
        self.assertEqual(post['destinations'],['东京']); self.assertEqual(post['topic'],'季节活动')
        self.assertIn('2026-10-02',self.read(f'blog/{path.stem}.html'))
        self.assertNotIn('<script>指南',self.read('blog/index.html'))

    def test_cover_credits_include_source_author_license_and_crop_note(self):
        self.build()
        article = self.read('blog/osaka-kyoto-nara-3days.html')
        self.assertIn('https://creativecommons.org/licenses/by-sa/4.0', article)
        self.assertIn('https://commons.wikimedia.org/wiki/User:Martin_Falbisoner', article)
        self.assertIn('网页显示裁切', article)
        self.assertIn('2016', article)
        self.assertIn('cover', article)

    def test_cleared_optional_destinations_keep_title_inference(self):
        self.extra_posts(1)
        path = self.root / 'content/posts/b-20261001-000000.md'
        path.write_text(path.read_text().replace('category: b', 'category: b\ndestinations: []').replace('测试指南 0', '京都旅行指南'))
        self.build()
        post = next(p for p in json.loads(self.read('blog/articles.json'))['posts'] if p['slug'] == path.stem)
        self.assertEqual(post['destinations'], ['京都'])

    def test_blog_picks_use_the_shared_lead_and_four_rows(self):
        self.build()
        page = self.read('blog/index.html')
        section = page.split('id="featured-section"', 1)[1].split('</section>', 1)[0]
        self.assertEqual(section.count('home-guide--lead'), 1)
        self.assertEqual(section.count('home-guide--row'), 4)
        self.assertNotIn('featured-lead', section)
        self.assertNotIn('featured-mini', section)
        self.assertIn('编辑精选', section)
        self.assertNotIn('id="featured-section"', self.read('blog/page/2/index.html'))
        picks = re.findall(r'<article class="home-guide[^"]*">\s*<a href="([^"]+)">', section)
        cards = re.findall(r'class="guide-card[^"]*" href="([^"]+)"', page)
        self.assertEqual(len(picks), 5)
        self.assertEqual(len(cards), 12)
        # The latest-article grid stays in publication order and is not the rotating set.
        self.assertNotEqual(cards[:5], picks)

    def test_chinese_homepage_shows_latest_guides_apart_from_editor_picks(self):
        shutil.copy(ROOT / 'zh.html', self.root / 'zh.html')
        # Keep the fixture newest as real daily articles are added.
        self.build()
        latest_date = max(date.fromisoformat(post['date']) for post in json.loads(self.read('blog/articles.json'))['posts'])
        fixture_date = (latest_date + timedelta(days=1)).isoformat()
        fixture_slug = 'b-' + fixture_date.replace('-', '') + '-000001'
        (self.root / 'content/posts' / f'{fixture_slug}.md').write_text(
            f'---\ndate: {fixture_date}\ncategory: b\ntopic: 交通接送\n'
            'title: "最新 <指南>"\nexcerpt: "摘要 & 说明"\n---\n正文\n')
        self.build()
        page = self.read('zh.html')
        header = page.split('</header>', 1)[0]
        self.assertIn('href="/blog/">旅行指南</a>', header)
        self.assertNotIn('href="#guides">旅行指南</a>', header)
        start = page.index('<!-- home-guides:start -->')
        end = page.index('<!-- home-guides:end -->')
        self.assertLess(page.index('id="fleet"'), start)
        self.assertLess(end, page.index('id="quality"'))
        self.assertLess(end, page.index('id="contact"'))
        block = page[start:end]
        self.assertIn('<h2>旅行指南</h2>', block)
        self.assertIn('href="/blog/">查看全部 →</a>', block)
        self.assertNotIn('查看全部旅行指南', block)
        self.assertNotIn('home-guides-more', block)
        self.assertIn('loading="lazy"', block)
        self.assertNotIn('loading="eager"', block)
        links = re.findall(r'<article class="home-guide[^"]*">\s*<a href="([^"]+)">', block)
        self.assertEqual(len(links), 5)
        self.assertNotIn(f'/blog/{fixture_slug}', links)
        self.assertEqual(block.count('home-guide--lead'), 1)
        self.assertEqual(block.count('home-guide--row'), 4)
        self.assertEqual(block.count('home-guide-excerpt'), 1)
        self.assertIn(f'data-guide-date="', block)
        featured_page = self.read('blog/index.html')
        featured = featured_page.split('id="featured-section"', 1)[1].split('</section>', 1)[0]
        featured_links = re.findall(r'<article class="home-guide[^"]*">\s*<a href="([^"]+)">', featured)
        self.assertEqual(links, featured_links)
        self.assertEqual(block.split('data-guide-date="', 1)[1].split('"', 1)[0], featured.split('data-guide-date="', 1)[1].split('"', 1)[0])
        self.assertEqual(featured.count('home-guide--lead'), 1)
        self.assertEqual(featured.count('home-guide--row'), 4)
        cards = re.findall(r'class="guide-card[^"]*" href="([^"]+)"', featured_page)
        self.assertEqual(cards[0], f'/blog/{fixture_slug}')
        self.assertIn('最新 &lt;指南&gt;', featured_page)
        self.assertIn('摘要 &amp; 说明', featured_page)
        self.assertNotIn('<指南>', featured_page)
        self.build()
        self.assertEqual(self.read('zh.html'), page)

    def test_local_stylesheets_and_scripts_use_content_hashes(self):
        for name in ("index.html", "zh.html", "en.html", "404.html", "quote.html"):
            shutil.copy(ROOT / name, self.root / name)
        header = self.read("scripts/journal-header.html")
        self.build()
        self.assertEqual(self.read("scripts/journal-header.html"), header)
        pages = [
            "index.html", "zh.html", "en.html", "404.html", "quote.html",
            "scripts/article-template.html", "scripts/blog-index-template.html",
            "blog/index.html", "blog/osaka-kyoto-nara-3days.html",
        ]
        hashes = {}
        for path in (self.root / "assets").rglob("*"):
            if path.suffix in {".css", ".js"} and path.is_file():
                hashes["/" + path.relative_to(self.root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        for name in pages:
            source = self.read(name)
            refs = re.findall(r'/assets/[A-Za-z0-9_./-]+\.(?:css|js)(?:\?[^"\']*)?', source)
            with self.subTest(page=name):
                self.assertTrue(refs)
                for ref in refs:
                    path = ref.split("?", 1)[0]
                    self.assertEqual(ref, f"{path}?v={hashes[path]}")
                self.assertNotIn("?v=20261024-", source)
                if "fonts.googleapis.com" in source:
                    self.assertIn("fonts.googleapis.com/css2?family=", source)
                    self.assertNotIn("fonts.googleapis.com/css2?v=", source)
        style = self.root / "assets/css/style.css"
        style.write_bytes(style.read_bytes() + b"\n/* cache-bust probe */\n")
        changed = hashlib.sha256(style.read_bytes()).hexdigest()[:12]
        self.build()
        self.assertIn(f'/assets/css/style.css?v={changed}', self.read("index.html"))
        self.assertIn(f'/assets/css/style.css?v={changed}', self.read("blog/index.html"))
        self.assertIn(f'/assets/css/style.css?v={changed}', self.read("404.html"))
        self.assertNotIn(f'/assets/css/style.css?v={hashes["/assets/css/style.css"]}', self.read("zh.html"))
        self.assertIn(f'/assets/js/main.js?v={hashes["/assets/js/main.js"]}', self.read("en.html"))
        self.assertIn(f'/assets/quote/styles.css?v={hashes["/assets/quote/styles.css"]}', self.read("quote.html"))

    def test_feed_sitemap_timestamps_and_indexnow_key(self):
        self.build()
        robots = (ROOT / 'robots.txt').read_text()
        self.assertIn('Sitemap: https://mangen.jp/sitemap.xml', robots)
        self.assertIn('User-agent: *', robots)
        catalog = json.loads(self.read('blog/articles.json'))['posts']
        self.assertNotIn('updated_at', catalog[0])
        osaka = next(post for post in catalog if post['slug'] == 'osaka-kyoto-nara-3days')
        sitemap = self.read('sitemap.xml')
        self.assertIn(f'<lastmod>{osaka["updated"]}T00:00:00+09:00</lastmod>', sitemap)
        self.assertIn('<loc>https://mangen.jp/blog/feed.xml</loc>', sitemap)
        page2 = self.read('blog/page/2/index.html')
        self.assertIn('content="从城市漫步到山间温泉，找到适合你的日本旅行灵感。万源整理行程路线、交通接送与实用旅行指南。第 2 页。"', page2)
        self.assertNotEqual(
            re.search(r'name="description" content="([^"]*)"', self.read('blog/index.html')).group(1),
            re.search(r'name="description" content="([^"]*)"', page2).group(1),
        )
        self.assertNotRegex(sitemap, r'<lastmod>\d{4}-\d{2}-\d{2}</lastmod>')
        for stamp in re.findall(r'<lastmod>(.*?)</lastmod>', sitemap):
            self.assertRegex(stamp, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$')
        import xml.etree.ElementTree as ET
        root = ET.fromstring(sitemap)
        ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        for loc in ('https://mangen.jp/', 'https://mangen.jp/zh', 'https://mangen.jp/en'):
            node = next(item for item in root.findall('sm:url', ns) if item.findtext('sm:loc', namespaces=ns) == loc)
            self.assertIsNone(node.find('sm:lastmod', ns))
        feed = self.read('blog/feed.xml')
        entries = feed.split('<entry>')[1:]
        slugs = [re.search(r'<id>https://mangen.jp/blog/([^<]+)</id>', entry).group(1) for entry in entries]
        self.assertEqual(slugs, [post['slug'] for post in catalog[:50]])
        self.assertEqual(feed.count('<entry>'), 50)
        self.assertIn('xmlns="http://www.w3.org/2005/Atom"', feed)
        for name in ('blog/index.html', 'blog/page/2/index.html', 'blog/osaka-kyoto-nara-3days.html'):
            page = self.read(name)
            self.assertIn('rel="alternate" type="application/atom+xml" title="日本旅行指南" href="https://mangen.jp/blog/feed.xml"', page)
        key = _indexnow().find_key(ROOT)
        self.assertEqual((ROOT / f'{key}.txt').read_text(encoding='utf-8').strip(), key)
        workflow = (ROOT / '.github/workflows/indexnow.yml').read_text()
        self.assertIn('api.indexnow.org', (ROOT / 'scripts/indexnow.py').read_text())
        self.assertIn('INDEXNOW_BEFORE', workflow)
        self.assertNotIn('secrets.', workflow)

    def test_topic_and_region_hubs_are_crawlable_indexes(self):
        stale = self.root / 'blog/topic/not-a-topic/index.html'
        stale.parent.mkdir(parents=True)
        stale.write_text('stale hub')
        self.build()
        self.assertFalse(stale.exists())
        index = self.read('blog/index.html')
        nav = index.split('class="guide-hubs"', 1)[1].split('</nav>', 1)[0]
        self.assertLess(nav.index('/blog/region/tokyo-kanto/'), nav.index('/blog/region/osaka-kansai/'))
        for slug in ('routes', 'transfers', 'food-and-stay', 'tax-free-shopping', 'seasons', 'etiquette'):
            self.assertIn(f'href="/blog/topic/{slug}/"', nav)
        for slug in ('tokyo-kanto', 'osaka-kansai', 'kyoto', 'hokkaido', 'okinawa', 'other'):
            self.assertIn(f'href="/blog/region/{slug}/"', nav)
        routes = self.read('blog/topic/routes/index.html')
        self.assertIn('<title>行程路线 | 日本旅行指南 | 株式会社万源</title>', routes)
        self.assertIn('content="收录主题为行程路线的旅行指南。"', routes)
        self.assertIn('href="https://mangen.jp/blog/topic/routes/"', routes)
        self.assertIn('"@type": "BreadcrumbList"', routes)
        self.assertIn('"@type": "CollectionPage"', routes)
        self.assertIn('"@type": "ItemList"', routes)
        self.assertEqual(len(Elements(routes).cards()), 12)
        self.assertIn('href="/blog/topic/routes/page/2/"', routes)
        page2 = self.read('blog/topic/routes/page/2/index.html')
        self.assertIn('<title>行程路线 · 第 2 页 | 日本旅行指南 | 株式会社万源</title>', page2)
        self.assertIn('content="收录主题为行程路线的旅行指南。第 2 页。"', page2)
        self.assertIn('rel="prev" href="https://mangen.jp/blog/topic/routes/"', page2)
        first = {card['href'] for card in Elements(routes).cards()}
        second = {card['href'] for card in Elements(page2).cards()}
        self.assertTrue(second.isdisjoint(first))
        kanto = self.read('blog/region/tokyo-kanto/index.html')
        self.assertIn('收录目的地属于东京・关东的旅行指南。东京・关东包含：东京、横滨、镰仓、江之岛、川越、箱根、富士山、日光、高尾山、长瀞、足利、热海、羽田、成田。', kanto)
        other = self.read('blog/region/other/index.html')
        self.assertIn('其他指未归入东京・关东、大阪・关西、京都、北海道、冲绳的目的地。', other)
        tax = self.read('blog/topic/tax-free-shopping/index.html')
        self.assertIn('已显示全部指南', tax)
        self.assertLessEqual(len(Elements(tax).cards()), 12)
        article = self.read('blog/osaka-kyoto-nara-3days.html')
        self.assertIn('href="/blog/topic/routes/">行程路线</a>', article)
        self.assertIn('href="/blog/region/osaka-kansai/">大阪</a>', article)
        self.assertIn('href="/blog/region/kyoto/">京都</a>', article)
        self.assertIn('href="/blog/region/osaka-kansai/">奈良</a>', article)
        self.assertIn('这条路线适合谁？', article.split('<div class="body">', 1)[1].split('</div>', 1)[0])
        sitemap = self.read('sitemap.xml')
        self.assertIn('https://mangen.jp/blog/topic/routes/</loc>', sitemap)
        self.assertIn('https://mangen.jp/blog/region/tokyo-kanto/</loc>', sitemap)
        self.assertIn('https://mangen.jp/blog/topic/routes/page/2/</loc>', sitemap)
        hub_lastmod = re.search(r'https://mangen.jp/blog/region/tokyo-kanto/</loc>\s*<lastmod>([^<]+)</lastmod>', sitemap)
        self.assertIsNotNone(hub_lastmod)
        self.assertRegex(hub_lastmod.group(1), r'^\d{4}-\d{2}-\d{2}T00:00:00\+09:00$')
        self.assertLess(sitemap.index('tokyo-kanto'), sitemap.index('osaka-kansai'))

    def test_every_article_related_block_is_static_cards(self):
        self.build()
        catalog = {post['slug']: post for post in json.loads(self.read('blog/articles.json'))['posts']}
        self.assertNotIn('tags', next(iter(catalog.values())))
        for slug, post in catalog.items():
            page = self.read(f'blog/{slug}.html')
            self.assertIn('class="related-reading"', page, slug)
            section = page.split('class="related-reading"', 1)[1].split('</section>', 1)[0]
            hrefs = re.findall(r'<a href="([^"]+)">', section)
            pool = sum(1 for other in catalog.values() if other['slug'] != slug and (
                other['topic'] == post['topic'] or set(other['regions']) & set(post['regions'])))
            self.assertGreaterEqual(len(hrefs), min(3, pool), slug)
            self.assertLessEqual(len(hrefs), 5, slug)
            self.assertEqual(len(hrefs), len(set(hrefs)), slug)
            self.assertNotIn(post['url'], hrefs, slug)
            self.assertEqual(section.count('<img ') + section.count('related-thumb'), len(hrefs))
            self.assertIn('loading="lazy"', section)
            for href in hrefs:
                other = catalog[href.removeprefix('/blog/')]
                shares_topic = other['topic'] == post['topic']
                shares_region = bool(set(other['regions']) & set(post['regions']))
                self.assertTrue(shares_topic or shares_region, slug)
                self.assertIn(f'datetime="{other["date"]}"', section)
                self.assertIn(escape(other['title'], quote=True), section)


def _indexnow():
    spec = importlib.util.spec_from_file_location('mangen_indexnow', ROOT / 'scripts' / 'indexnow.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _builder():
    spec = importlib.util.spec_from_file_location('mangen_build', ROOT / 'scripts' / 'build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _guide(slug, published, topic='行程路线', places=None, cover='/assets/uploads/fixture.png', links=None):
    return {'slug': slug, 'url': f'/blog/{slug}', 'title': slug, 'excerpt': '', 'date': published,
            'topic': topic, 'destinations': places or [], 'featured': False, 'cover': cover,
            'body_links': links or []}


class DailyGuideTests(unittest.TestCase):
    def setUp(self):
        self.build = _builder()
        self.today = date(2026, 10, 24)

    def test_same_date_is_stable_and_the_next_date_is_a_different_set(self):
        posts = [_guide(f'p-{index:02d}', f'2026-09-{index + 1:02d}', topic=self.build.TOPICS[index % 6]) for index in range(12)]
        first = [post['slug'] for post in self.build.select_daily_guides(posts, self.today)]
        second = [post['slug'] for post in self.build.select_daily_guides(list(reversed(posts)), self.today)]
        nxt = [post['slug'] for post in self.build.select_daily_guides(posts, self.today + timedelta(days=1))]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 5)
        self.assertNotEqual(set(first), set(nxt))

    def test_skips_articles_without_a_raster_thumbnail(self):
        posts = [_guide(f'p-{index}', f'2026-08-{index + 1:02d}') for index in range(6)]
        posts.append(_guide('bare', '2026-10-01', cover=''))
        posts.append(_guide('vector', '2026-10-02', cover='/assets/uploads/x.svg'))
        slugs = [post['slug'] for post in self.build.select_daily_guides(posts, self.today)]
        self.assertNotIn('bare', slugs)
        self.assertNotIn('vector', slugs)
        self.assertEqual(len(slugs), 5)

    def test_less_linked_older_articles_lead_when_the_window_starts(self):
        posts = [_guide(f'quiet-{index}', f'2020-01-{index + 1:02d}') for index in range(5)]
        posts.append(_guide('popular', '2026-10-01'))
        for post in posts:
            if post['slug'] != 'popular':
                post['body_links'] = ['popular']
        ordinal = self.today.toordinal()
        while (ordinal * 5) % len(posts):
            ordinal += 1
        day = date.fromordinal(ordinal)
        picks = [post['slug'] for post in self.build.select_daily_guides(posts, day)]
        counts = self.build.inbound_link_counts(posts, day)
        self.assertGreater(counts['popular'], counts['quiet-0'])
        self.assertEqual(picks[0], 'quiet-0')
        self.assertNotIn('popular', picks)
        previous = {post['slug'] for post in self.build.select_daily_guides(posts, day - timedelta(days=1))}
        self.assertNotEqual(set(picks), previous)

    def test_short_pool_returns_every_article_with_a_thumbnail(self):
        posts = [_guide('only', '2026-01-01'), _guide('two', '2026-01-02', cover='')]
        self.assertEqual([post['slug'] for post in self.build.select_daily_guides(posts, self.today)], ['only'])

    def test_card_text_is_escaped(self):
        html = self.build.render_home_guide_card({
            'url': '/blog/x', 'title': '最新 <指南>', 'excerpt': '摘要 & 说明', 'topic': '交通接送',
            'date': '2026-10-26', 'cover': '/assets/uploads/fixture.png', 'coverAlt': '',
            'coverCredit': '', 'coverLicense': '', 'coverCaption': '', 'coverChanges': '',
            'coverSource': '', 'coverLicenseUrl': '', 'coverCreatorUrl': '',
        }, True)
        self.assertIn('最新 &lt;指南&gt;', html)
        self.assertIn('摘要 &amp; 说明', html)
        self.assertNotIn('<指南>', html)

    def test_retired_topic_names_publish_as_the_six_current_topics(self):
        build = _builder()
        self.assertEqual(build.canonical_topic('目的地攻略', 'd'), '行程路线')
        self.assertEqual(build.canonical_topic('景点行程', 'b'), '行程路线')
        self.assertEqual(build.canonical_topic('机场与出入境', 'b'), '交通接送')
        self.assertEqual(build.canonical_topic('交通出行', 'c'), '交通接送')
        self.assertEqual(build.canonical_topic('', 'a'), '交通接送')
        self.assertEqual(build.canonical_topic('', 'd'), '行程路线')
        self.assertEqual(build.canonical_topic(None, 'b'), '礼仪与生活')

    def test_region_chips_follow_article_counts_and_keep_geographic_order(self):
        build = _builder()
        self.assertEqual(build.visible_region_chips([
            {'destinations': ['广岛']}, {'destinations': ['广岛']}, {'destinations': ['东京']},
        ]), ['东京・关东', '其他'])
        self.assertEqual(build.visible_region_chips([
            {'destinations': ['东京']}, {'destinations': ['大阪']}, {'destinations': ['京都']},
            {'destinations': ['札幌']}, {'destinations': ['那霸']}, {'destinations': ['名古屋']},
        ]), ['东京・关东', '大阪・关西', '京都', '北海道', '冲绳', '其他'])
        self.assertLessEqual(len(build.visible_region_chips([
            {'destinations': [place]} for place in build.DESTINATIONS
        ])), 6)



def _related_post(build, slug, published, topic, places, tags=None, title=None, cover='/assets/uploads/x.png'):
    return {
        'slug': slug, 'url': f'/blog/{slug}', 'date': published, 'topic': topic,
        'destinations': places, 'regions': build.regions_for(places), 'tags': tags or [],
        'title': title or slug, 'cover': cover, 'coverAlt': title or slug,
    }


class RelatedArticleTests(unittest.TestCase):
    def setUp(self):
        self.build = _builder()

    def test_newest_page_links_the_older_matches_and_not_itself(self):
        posts = [_related_post(self.build, f'g-{i:02d}', f'2026-01-{i+1:02d}', '行程路线', ['东京']) for i in range(8)]
        newest = posts[-1]
        related = self.build.select_related_map(posts)
        slugs = [post['slug'] for post in related[newest['slug']]]
        self.assertEqual(slugs, [f'g-{i:02d}' for i in range(5)])
        self.assertNotIn(newest['slug'], slugs)
        again = [post['slug'] for post in self.build.select_related_map(list(reversed(posts)))[newest['slug']]]
        self.assertEqual(again, slugs)
        inbound = {post['slug']: 0 for post in posts}
        for picks in related.values():
            for post in picks:
                inbound[post['slug']] += 1
        self.assertTrue(all(count > 0 for count in inbound.values()))
        self.assertGreaterEqual(inbound['g-00'], inbound['g-07'])

    def test_region_and_topic_win_then_same_topic_fills_a_short_pool(self):
        tokyo = [_related_post(self.build, f'tokyo-{i}', f'2026-02-0{i+1}', '行程路线', ['东京']) for i in range(2)]
        osaka = [_related_post(self.build, f'osaka-{i}', f'2026-03-0{i+1}', '行程路线', ['大阪']) for i in range(6)]
        other = _related_post(self.build, 'food', '2026-04-01', '住宿美食', ['东京'])
        related = self.build.select_related_map(tokyo + osaka + [other])
        slugs = [post['slug'] for post in related['tokyo-1']]
        self.assertIn('tokyo-0', slugs)
        self.assertNotIn('food', slugs)
        self.assertTrue(all(slug.startswith('osaka-') or slug == 'tokyo-0' for slug in slugs))
        self.assertGreaterEqual(len(slugs), 3)
        self.assertLessEqual(len(slugs), 5)

    def test_same_tag_counts_and_region_only_is_the_last_resort(self):
        tagged = _related_post(self.build, 'tagged', '2026-05-01', '购物退税', ['大阪'], tags=['退税'])
        peer = _related_post(self.build, 'peer', '2026-05-02', '礼仪与生活', ['大阪'], tags=['退税'])
        far = _related_post(self.build, 'far', '2026-05-03', '礼仪与生活', ['东京'], tags=['退税'])
        neighbors = [_related_post(self.build, f'near-{i}', f'2026-06-0{i+1}', '住宿美食', ['大阪']) for i in range(4)]
        solo = _related_post(self.build, 'solo', '2026-07-01', '季节活动', ['京都'])
        related = self.build.select_related_map([tagged, peer, far, solo, *neighbors])
        tagged_slugs = [post['slug'] for post in related['tagged']]
        self.assertEqual(tagged_slugs[0], 'peer')
        self.assertIn('far', tagged_slugs)
        self.assertLess(tagged_slugs.index('peer'), tagged_slugs.index('far'))
        solo_slugs = [post['slug'] for post in related['solo']]
        self.assertEqual(solo_slugs, [])
        thin = self.build.select_related_map([solo, neighbors[0]])
        self.assertEqual([post['slug'] for post in thin['solo']], [])

    def test_region_neighbors_fill_when_the_topic_is_unique(self):
        solo = _related_post(self.build, 'solo', '2026-07-01', '季节活动', ['大阪'])
        neighbors = [_related_post(self.build, f'near-{i}', f'2026-06-0{i+1}', '住宿美食', ['大阪']) for i in range(4)]
        tokyo = _related_post(self.build, 'tokyo', '2026-08-01', '住宿美食', ['东京'])
        related = self.build.select_related_map([solo, tokyo, *neighbors])
        self.assertEqual([post['slug'] for post in related['solo']], [f'near-{i}' for i in range(4)])

    def test_cards_show_thumbnail_title_date_and_escape(self):
        post = _related_post(self.build, 'old', '2026-01-02', '行程路线', ['东京'], title='旧文 <指南> & 说明', cover='')
        covered = _related_post(self.build, 'pic', '2026-01-03', '行程路线', ['东京'], title='有图', cover='/assets/uploads/a.png')
        html = self.build.render_related_section([post, covered])
        self.assertIn('class="related-thumb"', html)
        self.assertIn('src="/assets/uploads/a.png"', html)
        self.assertIn('loading="lazy"', html)
        self.assertIn('旧文 &lt;指南&gt; &amp; 说明', html)
        self.assertIn('datetime="2026-01-02"', html)
        self.assertIn('>2026.01.02</time>', html)
        self.assertNotIn('<指南>', html)
        self.assertEqual(self.build.render_related_section([]), '')


class HubCopyTests(unittest.TestCase):
    def test_intros_use_only_the_taxonomy_names(self):
        build = _builder()
        self.assertEqual(build.topic_intro('行程路线'), '收录主题为行程路线的旅行指南。')
        self.assertEqual(build.topic_hub_path('交通接送'), '/blog/topic/transfers/')
        self.assertEqual(build.topic_hub_path('礼仪与生活', 2), '/blog/topic/etiquette/page/2/')
        self.assertEqual(build.region_hub_path('东京・关东'), '/blog/region/tokyo-kanto/')
        self.assertEqual(build.region_hub_path('大阪・关西', 3), '/blog/region/osaka-kansai/page/3/')
        intro = build.region_intro('大阪・关西')
        self.assertEqual(intro, '收录目的地属于大阪・关西的旅行指南。大阪・关西包含：大阪、神户、奈良、姬路、和歌山、滋贺、箕面。')
        self.assertNotIn('推荐', intro)
        self.assertNotIn('最佳', intro)


class DiscoveryTests(unittest.TestCase):
    def test_timestamps_use_japan_offset_and_do_not_invent_a_clock(self):
        build = _builder()
        self.assertEqual(build.jst_timestamp('2026-10-14'), '2026-10-14T00:00:00+09:00')
        self.assertEqual(build.jst_timestamp(date(2026, 10, 14)), '2026-10-14T00:00:00+09:00')
        self.assertEqual(
            build.jst_timestamp(build.datetime(2026, 10, 14, 1, 0, tzinfo=build.timezone.utc)),
            '2026-10-14T10:00:00+09:00',
        )

    def test_indexnow_submits_only_new_or_changed_sitemap_urls(self):
        indexnow = _indexnow()
        previous = (
            '<urlset><url><loc>https://mangen.jp/</loc></url>'
            '<url><loc>https://mangen.jp/blog/old</loc><lastmod>2026-01-01T00:00:00+09:00</lastmod></url></urlset>'
        )
        current = (
            '<urlset><url><loc>https://mangen.jp/</loc></url>'
            '<url><loc>https://mangen.jp/blog/old</loc><lastmod>2026-02-01T00:00:00+09:00</lastmod></url>'
            '<url><loc>https://mangen.jp/blog/new</loc><lastmod>2026-03-01T00:00:00+09:00</lastmod></url></urlset>'
        )
        self.assertEqual(indexnow.changed_locations(previous, current), [
            'https://mangen.jp/blog/old', 'https://mangen.jp/blog/new',
        ])
        self.assertEqual(indexnow.changed_locations('', current)[0], 'https://mangen.jp/')

if __name__ == '__main__': unittest.main()

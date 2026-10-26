"""Build output contracts; each test runs the actual static generator in isolation."""
from datetime import date, timedelta
from pathlib import Path
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
        for name in ('index.html', 'zh.html', 'en.html'):
            shutil.copy2(ROOT / name, self.root / name)
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
        self.assertIn('class="guide-taxonomy">大阪 · 行程路线</div>', source)
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
        page = self.read('blog/index.html')
        self.assertIn('https://creativecommons.org/licenses/by-sa/4.0', page)
        self.assertIn('https://commons.wikimedia.org/wiki/User:Martin_Falbisoner', page)
        self.assertIn('网页显示裁切', page)
        article = self.read('blog/osaka-kyoto-nara-3days.html')
        self.assertIn('2016', article)
        self.assertIn('cover', article)

    def test_cleared_optional_destinations_keep_title_inference(self):
        self.extra_posts(1)
        path = self.root / 'content/posts/b-20261001-000000.md'
        path.write_text(path.read_text().replace('category: b', 'category: b\ndestinations: []').replace('测试指南 0', '京都旅行指南'))
        self.build()
        post = next(p for p in json.loads(self.read('blog/articles.json'))['posts'] if p['slug'] == path.stem)
        self.assertEqual(post['destinations'], ['京都'])

    def test_editor_picks_show_a_lead_and_smaller_cards_with_the_pinned_guide(self):
        self.build()
        page = self.read('blog/index.html')
        section = page.split('id="featured-section"', 1)[1].split('</section>', 1)[0]
        self.assertEqual(section.count('class="featured-lead'), 1)
        minis = section.count('class="featured-mini"')
        self.assertGreaterEqual(minis, 2)
        self.assertLessEqual(1 + minis, 5)
        # The only manual pin stays the lead card, ahead of the automatic cards.
        self.assertLess(section.index('/blog/osaka-kyoto-nara-3days'), section.index('featured-mini'))
        self.assertNotIn('id="featured-section"', self.read('blog/page/2/index.html'))

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
        self.assertIn('最新 &lt;指南&gt;', block)
        self.assertIn('摘要 &amp; 说明', block)
        self.assertNotIn('<指南>', block)
        self.assertIn('loading="lazy"', block)
        self.assertNotIn('loading="eager"', block)
        self.assertIn('>交通接送</p>', block)
        self.assertIn(f'datetime="{fixture_date}"', block)
        links = re.findall(r'<article class="home-guide[^"]*">\s*<a href="([^"]+)">', block)
        self.assertEqual(len(links), 5)
        self.assertEqual(links[0], f'/blog/{fixture_slug}')
        self.assertEqual(block.count('home-guide--lead'), 1)
        self.assertEqual(block.count('home-guide--row'), 4)
        self.assertEqual(block.count('home-guide-excerpt'), 1)
        featured = self.read('blog/index.html').split('id="featured-section"', 1)[1].split('</section>', 1)[0]
        featured_links = re.findall(r'href="(/blog/[^"]+)"', featured)
        self.assertNotEqual(links, featured_links)
        self.assertLess(featured.index('/blog/osaka-kyoto-nara-3days'), featured.index('featured-mini'))
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


    def test_editorial_policy_schema_service_block_and_shared_source_note(self):
        self.build()
        airport = self.read('blog/b-20261017-090000.html')
        source = (self.root / 'content/posts/b-20261017-090000.md').read_text()
        self.assertNotIn('资料核对：', source)
        self.assertIn('reviewed:', source)
        self.assertIn('https://tokyo-haneda.com/service/facilities/observation_deck.html', airport)
        self.assertEqual(airport.count('class="source-note"'), 1)
        self.assertIn('资料核对：<time datetime="2026-10-17">2026-10-17</time>', airport)
        self.assertIn('发布于 <time datetime="2026-10-17">2026-10-17</time>', airport)
        self.assertNotIn('更新于', airport)
        self.assertIn('"url": "https://mangen.jp/editorial/zh/"', airport)
        self.assertIn('"logo": {"@type": "ImageObject", "url": "https://mangen.jp/assets/img/logo.png"}', airport)
        self.assertNotIn('"dateModified"', airport)
        self.assertIn('href="/zh#services">用车服务</a>', airport)
        self.assertIn('href="/zh#fleet">车型阵容</a>', airport)
        self.assertIn('href="/zh#contact">联系我们</a>', airport)
        self.assertIn('为访日旅客与商务人士提供在日出行用车。', airport)
        niseko = self.read('blog/d-20261021-090004.html')
        niseko_source = (self.root / 'content/posts/d-20261021-090004.md').read_text()
        self.assertIn('日期为雪场计划，实际开放受雪况与运营调整影响。', niseko_source)
        self.assertIn('日期为雪场计划，实际开放受雪况与运营调整影响。', niseko)
        self.assertNotIn('class="guide-service"', niseko)
        self.assertIn('class="source-note"', niseko)
        kyoto = self.read('blog/d-20261025-090003.html')
        self.assertNotIn('class="guide-service"', kyoto)
        osaka = self.read('blog/osaka-kyoto-nara-3days.html')
        self.assertIn('class="guide-service"', osaka)
        self.assertNotIn('class="source-note"', osaka)
        changed = self.read('blog/first-trip-japan-2026.html')
        self.assertIn('"dateModified": "2026-10-14"', changed)
        self.assertIn('发布于 <time datetime="2026-09-24">2026-09-24</time>', changed)
        self.assertIn('更新于 <time datetime="2026-10-14">2026-10-14</time>', changed)
        self.assertNotIn('class="guide-service"', changed)
        for route, canonical in (
            ('editorial/index.html', 'https://mangen.jp/editorial/'),
            ('editorial/zh/index.html', 'https://mangen.jp/editorial/zh/'),
            ('editorial/en/index.html', 'https://mangen.jp/editorial/en/'),
        ):
            page = self.read(route)
            self.assertIn('content="index,follow"', page)
            self.assertNotIn('noindex', page)
            self.assertIn(f'href="{canonical}"', page)
            self.assertIn('hreflang="ja" href="https://mangen.jp/editorial/"', page)
            self.assertIn('hreflang="zh-CN" href="https://mangen.jp/editorial/zh/"', page)
            self.assertIn('hreflang="en" href="https://mangen.jp/editorial/en/"', page)
            self.assertIn('hreflang="x-default" href="https://mangen.jp/editorial/"', page)
            self.assertNotIn('TODO', page)
            self.assertIn('示意图（AI 辅助制作），非实景，仅供参考。', page)
            self.assertIn('info@mangen.jp', page)
            self.assertNotIn('梁超', page)
            self.assertNotIn('Chao Liang', page)
            self.assertLess(page.index('072-275-4665'), page.index('042-649-9057'))
            self.assertIn(f'<lastmod>2026-10-26T00:00:00+09:00</lastmod>', self.read('sitemap.xml'))
            self.assertIn(f'<loc>{canonical}</loc>', self.read('sitemap.xml'))
        zh = self.read('editorial/zh/index.html')
        self.assertIn('审稿由编辑部负责。', zh)
        ja = self.read('editorial/index.html')
        self.assertIn('確認は編集部が行います。', ja)
        en = self.read('editorial/en/index.html')
        self.assertIn('Reviewed by the Editorial Team.', en)
        self.assertIn('href="/zh#services">用车服务</a>', zh)
        self.assertIn('href="/blog/">旅行指南</a>', zh)
        self.assertIn('>JA</a>', zh)
        self.assertIn('>ZH</a>', zh)
        self.assertIn('>EN</a>', zh)
        self.assertNotIn('24/7', zh)
        self.assertNotIn('24小时营业', zh)


def _builder():
    spec = importlib.util.spec_from_file_location('mangen_build', ROOT / 'scripts' / 'build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _post(slug, published, topic, places, featured=False, order=None, until=''):
    return {'slug': slug, 'date': published, 'topic': topic, 'destinations': places,
            'featured': featured, 'featured_order': order, 'featured_until': until}


class EditorPickTests(unittest.TestCase):
    def setUp(self):
        self.build = _builder()
        self.today = date(2026, 10, 24)

    def test_manual_pins_keep_order_and_stop_at_five(self):
        posts = [_post(f'pin-{i}', '2026-09-01', f'topic-{i}', [f'place-{i}'], True, order=6 - i) for i in range(6)]
        posts.append(_post('newer', '2026-10-23', 'extra', ['tokyo'], True))
        picks = self.build.select_editor_picks(posts, self.today)
        self.assertEqual([post['slug'] for post in picks], ['pin-5', 'pin-4', 'pin-3', 'pin-2', 'pin-1'])

    def test_expired_pin_loses_priority_and_same_day_selection_is_stable(self):
        posts = [
            _post('old-pin', '2026-10-01', '路线', ['大阪'], True, until='2026-10-23'),
            _post('kept', '2026-09-22', '行程', ['京都'], True, order=1),
        ]
        posts += [_post(f'auto-{i}', '2026-10-20', f'主题{i}', [f'地区{i}']) for i in range(6)]
        first = [post['slug'] for post in self.build.select_editor_picks(posts, self.today)]
        second = [post['slug'] for post in self.build.select_editor_picks(posts, self.today)]
        self.assertEqual(first[0], 'kept')
        self.assertNotIn('old-pin', first)
        self.assertEqual(len(first), 5)
        self.assertEqual(first, second)
        self.assertNotEqual(
            self.build.rotation_rank('auto-0', self.today),
            self.build.rotation_rank('auto-0', date(2026, 10, 25)),
        )

    def test_auto_fill_skips_the_latest_row_and_repeats_a_topic_only_when_needed(self):
        newest = [_post(f'new-{i}', f'2026-10-{24 - i:02d}', '交通出行', ['东京']) for i in range(3)]
        mixed = [
            _post('a1', '2026-10-18', '行程路线', ['京都']),
            _post('a2', '2026-10-18', '行程路线', ['奈良']),
            _post('b', '2026-10-17', '季节活动', ['大阪']),
            _post('c', '2026-10-17', '礼仪与生活', ['北海道']),
            _post('d', '2026-10-16', '购物退税', ['福冈']),
            _post('e', '2026-10-16', '景点行程', ['箱根']),
        ]
        picks = self.build.select_editor_picks(newest + mixed, self.today)
        slugs = [post['slug'] for post in picks]
        self.assertEqual(len(slugs), 5)
        self.assertTrue(set(slugs).isdisjoint({post['slug'] for post in newest}))
        self.assertEqual(sum(post['topic'] == '行程路线' for post in picks), 1)

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

    def test_old_catalog_falls_back_to_recent_posts_and_short_catalogs_stay_short(self):
        old = [_post(f'old-{i}', '2026-01-01', f'topic-{i}', [f'place-{i}']) for i in range(6)]
        picks = self.build.select_editor_picks(old, self.today)
        self.assertEqual([post['slug'] for post in picks], [f'old-{i}' for i in range(5, 0, -1)])
        short = old[:2]
        self.assertEqual(len(self.build.select_editor_picks(short, self.today)), 2)

if __name__ == '__main__': unittest.main()

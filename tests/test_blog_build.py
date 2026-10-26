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


if __name__ == '__main__': unittest.main()

"""Build output contracts; each test runs the actual static generator in isolation."""
from pathlib import Path
from html.parser import HTMLParser
import json
import os
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
    def test_real_cards_and_generated_search_catalog_keep_all_five_urls(self):
        self.build(); index = Elements(self.read('blog/index.html'))
        self.assertEqual(len(index.cards()), 5)
        payload = json.loads(self.read('blog/articles.json'))
        self.assertEqual(sorted(p['slug'] for p in payload['posts']), self.original)
        self.assertEqual(payload['perPage'], 12)
        for slug in self.original:
            self.assertTrue((self.root / f'blog/{slug}.html').is_file())
            self.assertIn(f'https://mangen.jp/blog/{slug}', self.read('sitemap.xml'))
    def test_pagination_has_real_links_distinct_canonicals_and_no_overlap(self):
        self.extra_posts(20); self.build()
        routes = ['blog/index.html', 'blog/page/2/index.html', 'blog/page/3/index.html']
        self.assertTrue((self.root / routes[1]).exists(), 'More than 12 posts must produce page 2')
        all_urls=[]
        for i, route in enumerate(routes, 1):
            page = Elements(self.read(route)); cards = page.cards(); all_urls += [c['href'] for c in cards]
            self.assertEqual(len(cards), 12 if i < 3 else 1)
            canonical='https://mangen.jp/blog/' if i==1 else f'https://mangen.jp/blog/page/{i}/'
            self.assertEqual(page.attrs('link', rel='canonical')[0]['href'], canonical)
            self.assertIn(canonical, self.read('sitemap.xml'))
        self.assertEqual(len(set(all_urls)), 25)
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
        self.assertFalse((self.root/'blog/page/2/index.html').exists())
        self.assertFalse((self.root/'blog/b-20261001-000000.html').exists())
    def test_filters_are_grounded_and_no_mock_articles_exist(self):
        self.build(); source=self.read('blog/index.html')
        self.assertIn('data-filter="destination"', source)
        self.assertNotIn('value="北海道"',source)
        self.assertNotIn('富士山一日游，把风景留给旅途', source)
        self.assertIn('value="京都"',source)
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

if __name__ == '__main__': unittest.main()

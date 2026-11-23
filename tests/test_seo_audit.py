import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import seo_audit


class SeoAuditTests(unittest.TestCase):
    def test_counts_distinct_canonical_sources_not_repeated_links_or_self(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'blog').mkdir()
            (root / 'blog/a.html').write_text('<link rel="canonical" href="https://mangen.jp/blog/a">'
                '<a href="/blog/b.html#one">one</a><a href="https://mangen.jp/blog/b">two</a>'
                '<a href="/blog/a">self</a><a href="/blog/c" rel="nofollow">skip</a>')
            (root / 'blog/b.html').write_text('<link rel="canonical" href="https://mangen.jp/blog/b">')
            result = seo_audit.snapshot(root)
            self.assertEqual(result['inbound']['/blog/b'], ['/blog/a'])
            self.assertEqual(result['inbound']['/blog/a'], [])

    def test_all_numbered_articles_have_archive_links_and_unique_metadata(self):
        result = seo_audit.snapshot(ROOT)
        self.assertEqual(seo_audit.issues(result), [])
        self.assertTrue(result['numbered'])
        for path in result['numbered']:
            self.assertIn('/blog/archive/', result['inbound'][path], path)

    def test_all_homepages_offer_ten_latest_articles(self):
        import build
        import json
        records = json.loads((ROOT / 'blog/articles.json').read_text())['posts']
        latest = build.select_latest_guides(records, build.journal_today(), 10)
        for filename in ['index.html', 'zh.html', 'en.html']:
            content = (ROOT / filename).read_text()
            for post in latest:
                self.assertIn('href="' + post['url'] + '"', content)

    def test_every_article_has_three_to_five_relevant_links(self):
        import build
        import json
        records = json.loads((ROOT / 'blog/articles.json').read_text())['posts']
        mapping = build.select_related_map(records)
        for source in records:
            picks = mapping[source['slug']]
            self.assertGreaterEqual(len(picks), 3, source['slug'])
            self.assertLessEqual(len(picks), 5)
            self.assertTrue(all(build.related_tier(source, p) is not None for p in picks))


    def test_archive_has_styles_and_complete_collection_schema(self):
        import json
        import re
        content = (ROOT / 'blog/archive/index.html').read_text()
        self.assertIn('/assets/css/article-archive.css', content)
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', content, re.S)[1])
        collection = next(item for item in schema['@graph'] if item['@type'] == 'CollectionPage')
        records = json.loads((ROOT / 'blog/articles.json').read_text())['posts']
        items = collection['mainEntity']['itemListElement']
        self.assertEqual(len(items), len(records))
        self.assertEqual(collection['mainEntity']['numberOfItems'], len(records))
        self.assertEqual({item['url'] for item in items}, {'https://mangen.jp' + post['url'] for post in records})
        self.assertEqual([item['position'] for item in items], list(range(1, len(records) + 1)))

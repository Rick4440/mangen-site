"""CMS changes must survive rebuilds, including removal of published content."""
from pathlib import Path
from html import unescape
import importlib.util
import json
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FaqPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ('index.html', 'zh.html', 'en.html'):
            shutil.copy2(ROOT / name, self.root / name)
        shutil.copytree(ROOT / 'content', self.root / 'content')

    def tearDown(self):
        self.tmp.cleanup()

    def build(self):
        path = ROOT / 'scripts/site_pages.py'
        self.assertTrue(path.exists(), 'A build-time CMS renderer is required')
        spec = importlib.util.spec_from_file_location('site_pages', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.update_site_pages(self.root)

    def test_final_five_are_visible_after_company_in_all_languages(self):
        self.build()
        data = json.loads((self.root / 'content/settings/faq.json').read_text())
        for lang, filename, heading in [('zh','zh.html','常见问题'),('ja','index.html','よくあるご質問'),('en','en.html','Frequently Asked Questions')]:
            html = (self.root / filename).read_text()
            faq = html.split('<!-- faq:start -->')[1].split('<!-- faq:end -->')[0]
            self.assertEqual(faq.count('class="faq-item"'), 5)
            self.assertNotIn('<details', faq)
            self.assertNotRegex(faq, r'(?<![-\w])hidden(?:\s|=|>)')
            self.assertIn(heading, faq)
            self.assertLess(html.index('id="company"'), html.index('id="faq"'))
            self.assertLess(html.index('id="faq"'), html.index('</main>'))
            self.assertNotIn('<section', html[html.index('id="company"'):html.index('<!-- faq:start -->')].split('</section>', 1)[-1])
            for item in data['items']:
                self.assertIn(item['question_i18n'][lang], unescape(faq))
                self.assertIn(item['answer_i18n'][lang], unescape(faq))
        self.assertIn('适用于埃尔法（Alphard）和海狮（HiAce）', (self.root/'zh.html').read_text())

    def test_edit_delete_reorder_hide_escape_and_repeat_build(self):
        self.build()
        path = self.root/'content/settings/faq.json'
        data = json.loads(path.read_text())
        removed = data['items'].pop(0)
        data['items'].reverse()
        data['items'][0]['question_i18n']['zh'] = '<script>alert(1)</script> & 问题'
        path.write_text(json.dumps(data, ensure_ascii=False))
        self.build()
        before = (self.root/'zh.html').read_text()
        self.assertNotIn(removed['question_i18n']['zh'], before)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt; &amp; 问题', before)
        self.assertLess(before.index('alert(1)'), before.index(data['items'][1]['question_i18n']['zh']))
        self.build()
        self.assertEqual(before, (self.root/'zh.html').read_text())
        data['items'] = []
        path.write_text(json.dumps(data))
        self.build()
        self.assertNotIn('id="faq"', (self.root/'zh.html').read_text())
        data['items'] = [removed]
        data['enabled'] = False
        path.write_text(json.dumps(data))
        self.build()
        self.assertNotIn('id="faq"', (self.root/'en.html').read_text())

    def test_standalone_pages_publish_translate_and_delete_without_touching_other_files(self):
        source = self.root/'content/pages/test-car.md'
        source.parent.mkdir(exist_ok=True)
        source.write_text('---\ndraft: true\ntitle_i18n: {zh: 测试车型, ja: テスト車両, en: Test vehicle}\ndescription_i18n: {zh: 简介, ja: 紹介, en: Description}\nbody_i18n: {zh: "## 空间\\n可编辑正文", ja: "## 車内\\n編集可能", en: "## Cabin\\nEditable text"}\n---\n')
        self.assertNotIn('/pages/test-car/', self.build())
        source.write_text(source.read_text().replace('draft: true','draft: false'))
        urls = self.build()
        for lang, route, title in [('zh','/pages/test-car/','测试车型'),('ja','/pages/test-car/ja/','テスト車両'),('en','/pages/test-car/en/','Test vehicle')]:
            self.assertIn(route, urls)
            html = (self.root/route.strip('/')/'index.html').read_text()
            self.assertIn(title, html)
            self.assertIn('rel="canonical" href="https://mangen.jp'+route+'"', html)
            self.assertEqual(html.count('rel="alternate" hreflang='), 3)
            self.assertNotIn('noindex', html)
        protected = self.root/'pages/unrelated.txt'
        protected.write_text('keep')
        source.unlink()
        self.build()
        self.assertFalse((self.root/'pages/test-car/index.html').exists())
        self.assertFalse((self.root/'pages/test-car/en/index.html').exists())
        self.assertEqual(protected.read_text(), 'keep')

    def test_missing_translation_is_reported_instead_of_falling_back_to_wrong_language(self):
        path = self.root/'content/settings/faq.json'
        self.assertTrue(path.exists(), 'FAQ must have an editable source')
        data = json.loads(path.read_text())
        data['items'][0]['answer_i18n']['ja'] = ''
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'ja'):
            self.build()


if __name__ == '__main__':
    unittest.main()

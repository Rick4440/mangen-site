from pathlib import Path
import importlib.util
import json
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / 'content/settings', self.root / 'content/settings')
        for name in ('index.html', 'zh.html', 'en.html'):
            shutil.copy2(ROOT / name, self.root / name)
        (self.root/'blog').mkdir()
        shutil.copy2(ROOT/'blog/green-plate-guide.html', self.root/'blog/green-plate-guide.html')

    def tearDown(self):
        self.tmp.cleanup()

    def build(self):
        path = ROOT/'scripts/site_navigation.py'
        self.assertTrue(path.exists(), 'Shared navigation renderer is required')
        spec = importlib.util.spec_from_file_location('site_navigation', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.update_site_navigation(self.root)

    def test_localized_faq_and_all_six_footer_links_on_home_and_article(self):
        self.build()
        for lang, name, home, label in [('zh','zh.html','/zh','常见问题'),('ja','index.html','/','よくあるご質問'),('en','en.html','/en','FAQ'),('zh','blog/green-plate-guide.html','/zh','常见问题')]:
            s=(self.root/name).read_text()
            header=s.split('<header',1)[1].split('</header>',1)[0]
            footer=s.split('<footer',1)[1].split('</footer>',1)[0]
            self.assertIn(f'href="{home}#faq">{label}</a>', header)
            for target in ('services','fleet','contact','company','faq'):
                self.assertIn(f'href="{home}#{target}"', footer)
            self.assertIn('href="/blog/"',footer)
            self.assertEqual(footer.count('class="footer-navigation"'),1)
            self.assertNotIn('license-1',footer)

    def test_edits_propagate_and_disabled_faq_has_no_dead_links(self):
        self.build()
        p=self.root/'content/settings/navigation.json'
        data=json.loads(p.read_text())
        data['items'][-1]['label_i18n']['zh']='用车问答'
        p.write_text(json.dumps(data))
        self.build()
        s=(self.root/'zh.html').read_text()
        self.assertIn('>用车问答</a>',s)
        self.build()
        self.assertEqual(s,(self.root/'zh.html').read_text())
        p=self.root/'content/settings/faq.json'
        data=json.loads(p.read_text());data['enabled']=False;p.write_text(json.dumps(data))
        self.build()
        for name in ('zh.html','en.html','index.html','blog/green-plate-guide.html'):
            s=(self.root/name).read_text()
            self.assertNotIn('#faq"',s)


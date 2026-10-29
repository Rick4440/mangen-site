import importlib.util
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
class BrowserQATests(unittest.TestCase):
    def test_qa_chooses_changed_articles_and_all_list_pages(self):
        path=ROOT/'scripts/browser_qa.py'
        self.assertTrue(path.exists(), 'Portable browser QA is missing')
        spec=importlib.util.spec_from_file_location('browser_qa',path)
        qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
        posts=[{'slug':str(i),'url':'/blog/'+str(i)} for i in range(25)]
        self.assertEqual(qa.select_routes(posts,12,['2','24']), ['/blog/2','/blog/24','/blog/','/blog/page/2/','/blog/page/3/'])
        with self.assertRaises(ValueError):qa.select_routes(posts,12,['missing'])
        with self.assertRaises(ValueError):qa.select_routes(posts,0,[])
        with self.assertRaises(ValueError):qa.select_routes([],12,[])
        with self.assertRaises(ValueError):qa.select_routes(posts+posts[:1],12,[])
        self.assertEqual(qa.select_routes(posts[:1],12,[]),['/blog/0','/blog/'])
    def test_local_targets_resolve_clean_urls_and_reject_missing(self):
        import tempfile
        path=ROOT/'scripts/browser_qa.py'
        spec=importlib.util.spec_from_file_location('browser_qa',path)
        qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
        self.assertTrue(hasattr(qa,'validate_local_targets'), 'Local link verification is missing')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'blog').mkdir()
            (root/'blog/a.html').write_text('<a href="https://mangen.jp/blog/b#section">next</a><img src="/image.png">')
            (root/'blog/b.html').write_text('target');(root/'image.png').write_bytes(b'x')
            self.assertEqual(qa.validate_local_targets(root,['/blog/a']), [])
            (root/'image.png').unlink()
            self.assertEqual(len(qa.validate_local_targets(root,['/blog/a'])),1)

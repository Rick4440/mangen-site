"""Local preview serves the same extensionless routes as Cloudflare Pages."""
import importlib.util
from pathlib import Path
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
class PreviewTests(unittest.TestCase):
    def test_extensionless_articles_and_querystrings_resolve_locally(self):
        preview = ROOT / 'scripts/preview.py'
        self.assertTrue(preview.exists(), 'Portable preview entry point is missing')
        spec = importlib.util.spec_from_file_location('preview', preview)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'blog').mkdir();(root/'blog/example.html').write_text('article');(root/'blog/index.html').write_text('index')
            (root/'.git').mkdir();(root/'.git/config').write_text('not served')
            server=ThreadingHTTPServer(('127.0.0.1',0),module.handler_for(root));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base=f'http://127.0.0.1:{server.server_port}'
                self.assertEqual(urlopen(base+'/blog/example?q=test').read(),b'article')
                self.assertEqual(urlopen(base+'/blog/?q=test').read(),b'index')
                from urllib.error import HTTPError
                with self.assertRaises(HTTPError) as caught: urlopen(base+'/.git/config')
                self.assertEqual(caught.exception.code,404)
            finally: server.shutdown();server.server_close();thread.join()

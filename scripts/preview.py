"""Serve the built static site locally, including Cloudflare-style clean URLs.

Run: python3 scripts/preview.py --port 4173
Production still uses scripts/build.py and Cloudflare Pages; this has no deploy step.
"""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, unquote

ROOT = Path(__file__).resolve().parents[1]


def handler_for(root):
    root = Path(root).resolve()

    class PreviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def send_head(self):
            url = urlsplit(self.path)
            parts = Path(unquote(url.path)).parts
            if any(part.startswith('.') for part in parts):
                self.send_error(404)
                return None
            resolved = Path(self.translate_path(url.path))
            if not resolved.exists() and resolved.with_suffix('.html').is_file() and not resolved.suffix:
                self.path = urlunsplit(('', '', url.path + '.html', url.query, ''))
            return super().send_head()

        def list_directory(self, path):
            self.send_error(404)
            return None

    return PreviewHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=4173)
    parser.add_argument('--strictPort', action='store_true', help='Accepted for preview tool compatibility; ports never auto-increment.')
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler_for(ROOT))
    print(f'Local preview only: http://{args.host}:{args.port}/blog/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

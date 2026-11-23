"""Audit generated HTML, counting distinct crawlable source pages per target."""
import argparse
import json
import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote

BASE = 'https://mangen.jp'

def normalize(url):
    path = unquote(urlsplit(urljoin(BASE + '/', url)).path)
    if path.endswith('/index.html'):
        path = path[:-10]
    elif path == '/index.html':
        path = '/'
    elif path.endswith('.html'):
        path = path[:-5]
    return path

class Page(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.title = ''; self.description = ''; self.canonical = ''; self.links = set()
        self.noindex = False; self.in_title = False
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'title': self.in_title = True
        if tag == 'meta' and a.get('name') == 'description': self.description = a.get('content', '')
        if tag == 'meta' and a.get('name') == 'robots': self.noindex = 'noindex' in a.get('content', '')
        if tag == 'link' and a.get('rel') == 'canonical': self.canonical = a.get('href', '')
        if tag == 'a' and a.get('href') and 'nofollow' not in a.get('rel', '').split():
            self.links.add(a['href'])

    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False

    def handle_data(self, data):
        if self.in_title: self.title += data

def snapshot(root):
    pages = {}; inbound = defaultdict(set)
    for file in sorted(root.rglob('*.html')):
        relative = file.relative_to(root)
        if relative.parts[0] not in {'blog', 'editorial', 'pages'} and len(relative.parts) != 1:
            continue
        page = Page(file.read_text(encoding='utf-8'))
        if page.noindex or not page.canonical: continue
        path = normalize(page.canonical)
        pages[path] = {'file': str(relative), 'title': page.title, 'description': page.description}
        for href in page.links:
            absolute = urljoin(page.canonical, href)
            if urlsplit(absolute).netloc.lower() not in {'mangen.jp', 'www.mangen.jp'}: continue
            target = normalize(absolute)
            if target != path: inbound[target].add(path)
    return {'pages': pages, 'inbound': {p: sorted(inbound[p]) for p in pages},
            'numbered': sorted(p for p in pages if re.fullmatch(r'/blog/[a-e]-\d{8}-\d{6}', p))}

def issues(data):
    result = []; groups = {key: defaultdict(list) for key in ('title', 'description')}
    for path, page in data['pages'].items():
        if len(page['description']) < 50: result.append(f'{path}: description < 50')
        # Judge the full title, not just a short place name before the separator.
        if len(page['title'].strip()) < 15: result.append(f'{path}: title < 15')
        for key in groups: groups[key][page[key]].append(path)
    for key, values in groups.items():
        for value, paths in values.items():
            if len(paths) > 1: result.append(f'duplicate {key}: {paths}')
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = snapshot(Path(__file__).resolve().parents[1])
    if args.output: args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'pages': len(data['pages']), 'numbered': len(data['numbered']), 'issues': issues(data)}, ensure_ascii=False, indent=2))

"""Portable, read-only browser release checks; never deploys or changes content.

Run after scripts/build.py. Reports and screenshots go outside production paths.
All published article and list routes are tested at desktop and mobile widths.
"""
import argparse
import asyncio
import json
import math
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit, urljoin, unquote
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def select_routes(posts, per_page, slugs):
    if not posts or per_page < 1:
        raise ValueError('Empty catalog or invalid page size')
    by_slug = {p['slug']: p['url'] for p in posts}
    if len(by_slug) != len(posts):
        raise ValueError('Duplicate article slugs')
    missing = set(slugs) - set(by_slug)
    if missing:
        raise ValueError(f'Articles absent from built catalog: {sorted(missing)}')
    urls = [by_slug[s] for s in slugs] if slugs else [p['url'] for p in posts]
    return urls + ['/blog/'] + [f'/blog/page/{p}/' for p in range(2, math.ceil(len(posts)/per_page)+1)]


def validate_local_targets(root, routes):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.urls=[]
        def handle_starttag(self, tag, attrs):
            if tag not in ('a','img','script','link','source'):
                return
            values=dict(attrs)
            self.urls.extend(values[key] for key in ('href','src') if values.get(key))
            if values.get('srcset'):
                self.urls.extend(part.strip().split()[0] for part in values['srcset'].split(','))
    def resolve(path):
        target=(root/unquote(path).lstrip('/')).resolve()
        if not target.is_relative_to(root.resolve()):
            return None
        if target.is_dir(): target=target/'index.html'
        elif not target.is_file() and not target.suffix: target=target.with_suffix('.html')
        return target if target.is_file() else None
    failures=[]
    for route in routes:
        source=resolve(route)
        if source is None:
            failures.append({'route':route,'target':route}); continue
        parser=Links();parser.feed(source.read_text())
        for value in parser.urls:
            target=urlsplit(urljoin('https://mangen.jp'+route,value))
            if target.scheme not in ('http','https') or target.hostname not in ('mangen.jp','www.mangen.jp'):
                continue
            if resolve(target.path) is None:
                failures.append({'route':route,'target':value})
    return failures


async def run(output):
    from playwright.async_api import async_playwright
    from preview import handler_for
    data = json.loads((ROOT/'blog/articles.json').read_text())
    routes = select_routes(data['posts'], data['perPage'], [])
    sitemap = {urlsplit(x.text).path for x in ET.parse(ROOT/'sitemap.xml').iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')}
    assert set(routes) <= sitemap, 'Article or list route absent from sitemap'
    broken=validate_local_targets(ROOT,routes)
    assert not broken, f'Broken local links/resources: {broken}'
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(ROOT))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    output.mkdir(parents=True, exist_ok=True)
    results=[]
    # Capture all list pages and latest ten articles. All articles are still tested.
    capture = {p['url'] for p in data['posts'][:10]}
    capture.update(r for r in routes if r.endswith('/'))
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            for width, height in [(1440,1000),(393,852)]:
                context = await browser.new_context(viewport={'width':width,'height':height}, device_scale_factor=1)
                # No external services, analytics or fonts are contacted by QA.
                async def local_only(route):
                    if route.request.url.startswith(base+'/'):
                        await route.continue_()
                    else:
                        await route.fulfill(status=200, body='', content_type='text/css' if route.request.resource_type=='stylesheet' else 'text/plain')
                await context.route('**/*', local_only)
                page = await context.new_page()
                page.set_default_timeout(15000)
                errors=[]
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda msg: errors.append(msg.text) if msg.type=='error' else None)
                page.on('response', lambda response: errors.append(f'HTTP {response.status}: {response.url}') if response.url.startswith(base+'/') and response.status>=400 else None)
                page.on('requestfailed', lambda request: errors.append(f'Failed request: {request.url}') if request.url.startswith(base+'/') else None)
                for path in routes:
                    errors.clear()
                    entry={'path':path,'width':width,'passed':False}
                    try:
                        response=await page.goto(base+path, wait_until='domcontentloaded')
                        assert response and response.status==200, 'Route did not return HTTP 200'
                        assert await page.locator('h1').count()==1, 'Expected one page heading'
                        await asyncio.wait_for(page.evaluate("async()=>{for(const img of document.images){img.loading='eager';await img.decode();}await document.fonts.ready;}"),timeout=15)
                        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'), 'Horizontal overflow'
                        assert not errors, f'Browser errors: {errors}'
                        assert await page.locator('link[rel="canonical"]').count()==1, 'Missing canonical'
                        if path in capture:
                            name=path.strip('/').replace('/','_') or 'root'
                            await page.screenshot(path=str(output/f'{width}-{name}.png'),full_page=True)
                        entry['passed']=True
                    except Exception as error:
                        entry['error']=str(error)
                        try:
                            name=path.strip('/').replace('/','_') or 'root'
                            await page.screenshot(path=str(output/f'FAILED-{width}-{name}.png'),full_page=True,timeout=5000)
                        except Exception:
                            pass
                    results.append(entry)
                # Exercise real search submit/reset and mobile menu on built page.
                try:
                    await page.goto(base+'/blog/')
                    await page.locator('#guide-search').fill(data['posts'][0]['title'])
                    await page.locator('.journal-search').evaluate('(form)=>form.requestSubmit()')
                    await page.wait_for_function('document.querySelectorAll(".guide-card").length > 0 && location.search.includes("q=")')
                    await page.locator('[data-clear]').first.click()
                    await page.wait_for_function('!location.search.includes("q=")')
                    if width==393:
                        button=page.locator('.menu-btn')
                        await button.click()
                        assert await button.get_attribute('aria-expanded')=='true'
                        await button.click()
                        assert await button.get_attribute('aria-expanded')=='false'
                    results.append({'path':'interactive-controls','width':width,'passed':True})
                except Exception as error:
                    results.append({'path':'interactive-controls','width':width,'passed':False,'error':str(error)})
                await context.close()
            await browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join()
        (output/'report.json').write_text(json.dumps({'posts':len(data['posts']),'routes':len(routes),'checks':results,'external_requests':'stubbed; local Noto fonts used','passed':bool(results) and all(r['passed'] for r in results)},ensure_ascii=False,indent=2))
    failures=[r for r in results if not r['passed']]
    print(json.dumps({'checks':len(results),'failures':failures},ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('browser-results'))
    args=parser.parse_args()
    asyncio.run(run(args.output))

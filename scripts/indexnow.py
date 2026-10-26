"""Tell IndexNow about sitemap URLs that are new or whose lastmod changed.

The URL list comes from this checkout's sitemap.xml and the previous commit.
The runner does not request mangen.jp. IndexNow fetches the public key file
itself. There is no Actions secret.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
HOST = "mangen.jp"
ENDPOINTS = (
    "https://api.indexnow.org/indexnow",
    "https://www.bing.com/indexnow",
)
URL_LIMIT = 10000
_KEY_NAME = re.compile(r"^[a-f0-9]{32}\.txt$")


def sitemap_entries(xml_text):
    if not (xml_text or "").strip():
        return []
    root = ET.fromstring(xml_text)
    namespace = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""

    def name(tag):
        return f"{{{namespace}}}{tag}" if namespace else tag

    entries = []
    for url in root.findall(name("url")):
        loc = url.findtext(name("loc")) or ""
        lastmod = url.find(name("lastmod"))
        entries.append((loc, lastmod.text if lastmod is not None else None))
    return entries


def changed_locations(previous_xml, current_xml):
    previous = dict(sitemap_entries(previous_xml))
    changed = []
    for loc, lastmod in sitemap_entries(current_xml):
        if loc not in previous or previous[loc] != lastmod:
            changed.append(loc)
    return changed


def find_key(root=ROOT):
    matches = [path for path in root.glob("*.txt") if _KEY_NAME.fullmatch(path.name) and path.read_text(encoding="utf-8").strip() == path.stem]
    if len(matches) != 1:
        raise SystemExit(f"Expected one 32-character IndexNow key file at the site root, found {len(matches)}.")
    return matches[0].stem


def submit(key, urls):
    payload = json.dumps({
        "host": HOST,
        "key": key,
        "keyLocation": f"https://{HOST}/{key}.txt",
        "urlList": urls,
    }).encode("utf-8")
    for endpoint in ENDPOINTS:
        request = urllib.request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            status = error.code
            body = error.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as error:
            print(f"{endpoint} request failed: {error.reason}")
            raise SystemExit(1) from error
        if status not in (200, 202):
            print(f"{endpoint} returned HTTP {status}: {body}")
            raise SystemExit(1)
        print(f"Submitted {len(urls)} URL(s) to {endpoint}.")


def previous_sitemap(before):
    if not before or set(before) == {"0"}:
        return ""
    try:
        return subprocess.check_output(["git", "show", f"{before}:sitemap.xml"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return ""


def main():
    key = find_key()
    current = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    urls = [loc for loc in changed_locations(previous_sitemap(os.environ.get("INDEXNOW_BEFORE", "")), current) if loc]
    if not urls:
        print("No new or changed sitemap URLs.")
        return
    for start in range(0, len(urls), URL_LIMIT):
        submit(key, urls[start:start + URL_LIMIT])


if __name__ == "__main__":
    main()

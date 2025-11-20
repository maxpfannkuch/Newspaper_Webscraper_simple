#!/usr/bin/env python3
"""
scrape_by_start.py
Crawlt Listing-Seiten: BASE + LISTING_PATH + "?start=N" (N = START_FROM .. MAX_START)
Pro Listing-Seite: extrahiert den Headline-Link (h2.article-title a), folgt dem Link,
speichert HTML/Text/Bilder in OUTDIR und Metadaten in SQLite.
"""

import os
import time
import sqlite3
import json
import logging
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from slugify import slugify
import urllib.robotparser as robotparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ========== Konfiguration ==========
BASE = "https://example.com"               # Platzhalter – echte URL über ENV setzen
LISTING_PATH = "/news/region.html"         # Generischer Pfad
START_FROM = 0
MAX_START = 100
OUTDIR = "data"
HTMLDIR = os.path.join(OUTDIR, "html")
IMAGEDIR = os.path.join(OUTDIR, "images")
DBFILE = os.path.join(OUTDIR, "articles.db")
USER_AGENT = "GenericNewsScraper/1.0"
RATE_BETWEEN_LISTINGS = 0.8
RATE_BETWEEN_ARTICLES = 0.5
COOKIES_FILE = "cookies.json"              # optional
# ===================================

os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(HTMLDIR, exist_ok=True)
os.makedirs(IMAGEDIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Session mit Retry
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})
retries = Retry(
    total=4,
    connect=4,
    read=4,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET"])
)
session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))

def load_cookies_into_session(session, fname=COOKIES_FILE):
    """Lade (optionale) Cookies aus einer JSON-Datei."""
    if not os.path.exists(fname):
        return
    try:
        with open(fname, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for c in cookies:
            name, val = c.get("name"), c.get("value")
            domain = c.get("domain") or None
            if name:
                session.cookies.set(name, val, domain=domain)
        logging.info("Cookies geladen aus %s", fname)
    except Exception as e:
        logging.warning("Fehler beim Laden von %s: %s", fname, e)

def allowed_by_robots(url: str) -> bool:
    """Konservativer robots.txt-Check."""
    try:
        rp = robotparser.RobotFileParser()
        rp.set_url(urljoin(BASE, "/robots.txt"))
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        logging.warning("robots.txt konnte nicht gelesen werden.")
        return True

# ----------------- DB -----------------
def init_db():
    conn = sqlite3.connect(DBFILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS articles (
      id INTEGER PRIMARY KEY,
      url TEXT UNIQUE,
      title TEXT,
      published_at TEXT,
      author TEXT,
      text TEXT,
      html_path TEXT,
      saved_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()

def already_saved(url: str) -> bool:
    conn = sqlite3.connect(DBFILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM articles WHERE url = ?", (url,))
    ok = cur.fetchone() is not None
    conn.close()
    return ok

def save_article_meta(url, title, published_at, author, text, html_path):
    conn = sqlite3.connect(DBFILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO articles (url, title, published_at, author, text, html_path)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (url, title, published_at, author, text, html_path))
    conn.commit()
    conn.close()

# -------------- Helpers --------------
def get_soup(url: str):
    if not allowed_by_robots(url):
        raise RuntimeError(f"Blocked by robots.txt: {url}")
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser"), r.text

def save_html(title_or_id: str, url: str, html: str) -> str:
    base = title_or_id or url
    name = slugify(base)[:100] or "page"
    filename = f"{name}.html"
    path = os.path.join(HTMLDIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path

def absolutize_url(page_url: str, maybe_url: str) -> str:
    if not maybe_url:
        return ""
    if maybe_url.startswith("//"):
        parsed_page = urlparse(page_url)
        return f"{parsed_page.scheme}:{maybe_url}"
    return urljoin(page_url, maybe_url)

def download_image(img_url: str, title_slug: str):
    if not img_url or img_url.startswith("data:"):
        return None
    try:
        parsed = urlparse(img_url)
        ext = os.path.splitext(parsed.path)[1]
        if not ext or len(ext) > 6:
            ext = ".jpg"
        name = slugify(os.path.basename(parsed.path))[:60] or "img"
        fname = f"{title_slug[:60]}-{name}{ext}"
        fpath = os.path.join(IMAGEDIR, fname)
        if not os.path.exists(fpath):
            headers = {"Referer": BASE, "User-Agent": USER_AGENT}
            rr = session.get(img_url, headers=headers, stream=True, timeout=30)
            rr.raise_for_status()
            with open(fpath, "wb") as out:
                for chunk in rr.iter_content(1024 * 8):
                    if chunk:
                        out.write(chunk)
            time.sleep(0.05)
        return fpath
    except Exception as e:
        logging.warning("Bild %s konnte nicht geladen werden: %s", img_url, e)
        return None

# -------- Listing Parsing ----------
def parse_listing_for_links(listing_html: str, base_url: str):
    soup = BeautifulSoup(listing_html, "html.parser")
    a = soup.select_one("h2.article-title a")
    if not a:
        a = soup.select_one(".leading .article-title a") or \
            soup.select_one(".items-leading a") or \
            soup.select_one(".item-title a")
    if a and a.get("href"):
        full = urljoin(base_url, a["href"]).split("#")[0]
        if LISTING_PATH in full:
            return []
        return [full]
    return []

# -------- Article Fetch ----------
def fetch_and_store_article(url: str):
    if already_saved(url):
        logging.info("Bereits gespeichert: %s", url)
        return
    try:
        soup, html = get_soup(url)
    except Exception as e:
        logging.error("Fehler beim Laden %s: %s", url, e)
        return

    title_el = soup.find("h1") or soup.find("title")
    title = (title_el.get_text(strip=True) if title_el else "") or ""

    published_at = None
    t_el = soup.find("time")
    if t_el:
        published_at = t_el.get("datetime") or t_el.get_text(strip=True)
    if not published_at:
        meta_date = soup.find("meta", {"property": "article:published_time"}) or \
                    soup.find("meta", {"name": "date"})
        if meta_date:
            published_at = meta_date.get("content")

    author = None
    meta_author = soup.find("meta", {"name": "author"}) or \
                  soup.find("meta", {"property": "article:author"})
    if meta_author:
        author = meta_author.get("content")

    container = soup.find("article") or soup
    paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    text = "\n\n".join([p for p in paras if p])

    html_path = save_html(title or url, url, html)

    title_slug = slugify(title or url)
    for img in container.find_all("img", src=True):
        img_url = absolutize_url(url, img.get("src"))
        download_image(img_url, title_slug)

    save_article_meta(url, title, published_at, author, text, html_path)
    logging.info("Artikel gespeichert: %s", url)

# ========== Main ==========
def main():
    load_cookies_into_session(session)
    init_db()

    found_any = False

    for start in range(START_FROM, MAX_START + 1):
        listing_url = f"{urljoin(BASE, LISTING_PATH)}?start={start}"
        logging.info("Listing prüfen: %s", listing_url)

        try:
            soup, listing_html = get_soup(listing_url)
        except Exception as e:
            logging.warning("Listing %s konnte nicht geladen werden: %s", listing_url, e)
            break

        links = parse_listing_for_links(listing_html, listing_url)
        if not links:
            logging.info("Keine Artikel gefunden bei start=%s — stoppe.", start)
            break

        found_any = True
        logging.info("Links gefunden: %d", len(links))

        for url in links:
            fetch_and_store_article(url)
            time.sleep(RATE_BETWEEN_ARTICLES)

        time.sleep(RATE_BETWEEN_LISTINGS)

    if not found_any:
        logging.warning("Über alle Startwerte keine Links gefunden.")
    else:
        logging.info("Fertig. Daten gespeichert in %s", OUTDIR)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
update_texts.py

Robuste Extraktion von Artikeltexten aus lokalen HTML-Dateien (data/html/*)
und Speicherung in der SQLite DB (data/articles.db).

Usage:
    python update_texts.py                 # nur leere Einträge verarbeiten
    python update_texts.py --force         # alle Einträge neu extrahieren (überschreibt)
    python update_texts.py --id 42         # nur Artikel mit id=42 verarbeiten
    python update_texts.py --limit 10      # nacheinander die ersten 10 Einträge verarbeiten (kombinierbar)
"""
import sqlite3
import os
import re
import argparse
from bs4 import BeautifulSoup
import trafilatura
import logging
import difflib

DBPATH = "data/articles.db"
ENC = "utf-8"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def clean_text(txt: str) -> str:
    if not txt:
        return None
    txt = txt.replace('\r\n', '\n').replace('\r', '\n')
    txt = re.sub(r'\u00A0', ' ', txt)
    txt = re.sub(r'\n\s*\n\s*\n+', '\n\n', txt)
    txt = "\n".join(line.strip() for line in txt.splitlines())
    txt = txt.strip()
    return txt if txt else None

def gather_paragraphs_in_order(soup, container):
    """
    Gibt eine Liste von Paragraph-Strings (in document-order) aus dem container zurück.
    (Bleibt als Hilfsfunktion erhalten - kann für spezielle Fälle genutzt werden.)
    """
    paras = []
    seen = set()
    for p in container.find_all(["p","div"], recursive=True):
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        if len(text) < 5:
            continue
        if text in seen:
            continue
        seen.add(text)
        paras.append(text)
    return paras

# -------------------------
# Noise keywords + Helfer
# -------------------------
NOISE_KEYWORDS = [
    "anzeige", "nächster artikel", "kommentar schreiben", "zeig dein herz",
    "spendier", "spendiere", "redaktion", "info@", "drucken", "typographie",
    "lese modus", "lesen modus", "teilen", "e-mail", "e mail", "newsletter",
    "tools drucken e-mail", "werbung", "zum artikel", "anzeigen", "anzeigen"
]

def _is_noise_text(s: str) -> bool:
    if not s:
        return True
    ss = s.strip().lower()
    # very short lines that are not sentences
    if len(ss) < 10:
        return True
    # contains explicit noise keywords
    for k in NOISE_KEYWORDS:
        if k in ss:
            return True
    # e-mail / url detection -> noise
    if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", ss):
        return True
    if "http://" in ss or "https://" in ss or ss.startswith("www."):
        return True
    # if more non-letter than letters (like '---' or '***') -> noise
    letters = len(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]", ss))
    non_letters = len(ss) - letters
    if letters == 0 or non_letters > letters * 2:
        return True
    return False

def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()

# -------------------------
# Neue, robuste Extraktionsfunktion
# -------------------------
def extract_from_article_dom(html, base_url=None):
    """
    Robustere Strategie:
    - Finde den besten Inhalts-Container (größter Textumfang / p-Anzahl)
    - Sammle dann alle Block-Elemente darin in Dokument-Reihenfolge
    - Weniger aggressive Dedupe-Regeln, erlauben kurze sinnvolle Sätze
    - Intro (blockquote.article-intro) wird vorangestellt, falls vorhanden
    """
    soup = BeautifulSoup(html, "lxml")

    # Entferne störende Tags
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form", "iframe"]):
        tag.decompose()

    # Entferne klar erkennbare UI-/Share-/Ad-Container (vorsichtig)
    ui_selectors = [
        ".article-tools", ".toolbox", ".share", ".social-share",
        ".print", ".print-button", ".visually-hidden", ".sr-only",
        ".ad", ".advert", ".anzeigen", ".ad-box", ".sidebar", ".related", ".teaser"
    ]
    for sel in ui_selectors:
        for el in soup.select(sel):
            try:
                el.decompose()
            except Exception:
                pass

    # Kandidaten-Selektoren, aus denen wir den besten Container wählen
    candidate_selectors = [
        "section.article-content[itemprop='articleBody']",
        "section.article-content",
        "section.article-full",
        "div.article-content-main",
        "div.article-content",
        "div[itemprop='articleBody']",
        "article",
        "main",
        "div[class*='article']",
        "div[class*='content']",
        "body"
    ]

    # Funktion: Score für einen container (mehr P-Tags + mehr Text = besser)
    def container_score(cont):
        p_count = len(cont.find_all("p"))
        text_len = sum(len(p.get_text(" ", strip=True)) for p in cont.find_all("p"))
        # gewichtung: p_count wichtig, dann text_len
        return p_count * 10 + (text_len // 100)

    # Sammle alle Kandidaten und wähle den mit höchstem Score
    candidates = []
    for sel in candidate_selectors:
        for c in soup.select(sel):
            candidates.append((container_score(c), c))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_container = candidates[0]
    else:
        best_container = soup  # fallback

    # Wenn Intro vorhanden, nimm es als eigenen Block voran
    parts = []
    seen = []
    intro = soup.select_one("blockquote.article-intro[itemprop='description'], blockquote.article-intro")
    if intro:
        intro_texts = []
        for el in intro.find_all(["p","div","span"], recursive=True):
            t = el.get_text(" ", strip=True)
            if t:
                intro_texts.append(re.sub(r"\s+"," ", t).strip())
        if intro_texts:
            parts.extend(intro_texts)
            seen.extend(intro_texts)

    # Helper: extrahiere Text-Block aus einem Element (inkl. <br>-getrennter Zeilen)
    def extract_block_text(el):
        # Wenn element hat <br>, jointe die Teile
        if el.find("br"):
            pieces = []
            for node in el.descendants:
                if getattr(node, "name", None) == "br":
                    pieces.append("\n")
                elif isinstance(node, str):
                    pieces.append(node)
            text = "".join(pieces)
        else:
            text = el.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # Sammle in document order: alle relevanten Block-Elemente innerhalb best_container
    for el in best_container.find_all(["h1","h2","h3","p","li","div","section"], recursive=True):
        # manche divs sind container-only ohne eigenständigen text -> skip wenn leer
        txt = extract_block_text(el)
        if not txt:
            continue
        # einfache noise-filter (eMail / urls / sehr kurzes Müll)
        low = txt.lower()
        if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", txt): 
            continue
        if "http://" in low or "https://" in low or low.startswith("www."):
            continue
        # filter typische UI-strings
        if any(k in low for k in ("anzeige", "nächster artikel", "kommentar schreiben", "anzeige", "zeig dein herz")):
            # aber wenn der block länger ist (echter Absatz), dann nicht zwangsläufig verwerfen
            if len(txt) < 80:
                continue

        # dedupe: exakte Duplikate vermeiden
        if txt in seen:
            continue

        # fuzzy dedupe: wenn sehr ähnlich (>0.95) zu einem kürzeren bereits aufgenommenen block -> skip
        too_similar = False
        for prev in seen[-15:]:
            if difflib.SequenceMatcher(None, prev, txt).ratio() > 0.95:
                too_similar = True
                break
        if too_similar:
            continue

        seen.append(txt)
        parts.append(txt)

    # Wenn das Ergebnis sehr kurz ist, erweitere Fallback: sammle alle <p> im Dokument (locker)
    if len("\n\n".join(parts)) < 80:
        paras = []
        for p in soup.find_all("p"):
            t = p.get_text(" ", strip=True)
            t = re.sub(r"\s+"," ", t).strip()
            if t and t not in seen:
                paras.append(t)
        # hänge nur hinzu, wenn deutlicher Mehrwert
        if paras:
            for t in paras:
                if t not in seen:
                    parts.append(t); seen.append(t)

    if not parts:
        return None

    # normalisiere mehrfachen Leerraum
    result = "\n\n".join(parts)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result

# -------------------------
# trafilatura / fallback
# -------------------------
def extract_with_trafilatura(html, base_url=None):
    try:
        res = trafilatura.extract(html, url=base_url, include_comments=False)
        if res and len(res.strip()) > 50:
            return clean_text(res)
    except Exception:
        pass
    return None

def extract_fallback_bs(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()
    candidate = soup.find("article") or soup.find("main") or soup.find("div", class_=lambda c: c and "content" in c.lower())
    if not candidate:
        candidate = soup.body or soup
    paras = []
    for p in candidate.find_all("p"):
        t = p.get_text(" ", strip=True)
        if t and len(t.split()) > 2:
            paras.append(t)
    if paras:
        return clean_text("\n\n".join(paras))
    meta = soup.find("meta", {"name":"description"}) or soup.find("meta", {"property":"og:description"})
    if meta and meta.get("content"):
        return clean_text(meta.get("content"))
    if soup.title and soup.title.string:
        return clean_text(soup.title.string)
    return None

# wrapper: liest html und probiert DOM -> trafilatura -> fallback
def extract_text_from_htmlfile(path, url=None):
    try:
        with open(path, "r", encoding=ENC) as f:
            html = f.read()
    except Exception as e:
        logging.warning("Kann HTML nicht lesen %s: %s", path, e)
        return None

    # 1) gezielte DOM-Extraktion
    txt = extract_from_article_dom(html, base_url=url)
    if txt:
        return txt

    # 2) trafilatura
    txt = extract_with_trafilatura(html, base_url=url)
    if txt:
        return txt

    # 3) fallback
    return extract_fallback_bs(html)

def update_row_text(conn, row_id, text):
    cur = conn.cursor()
    cur.execute("UPDATE articles SET text = ? WHERE id = ?", (text, row_id))
    conn.commit()

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="Alle Einträge neu extrahieren (überschreibt vorhandene Texte)")
    p.add_argument("--id", type=int, help="Nur Artikel mit dieser DB-ID verarbeiten")
    p.add_argument("--limit", type=int, default=None, help="Maximale Anzahl zu verarbeitender Einträge")
    return p.parse_args()

def main():
    args = parse_args()

    if not os.path.exists(DBPATH):
        logging.error("DB nicht gefunden: %s", DBPATH)
        return

    conn = sqlite3.connect(DBPATH)
    cur = conn.cursor()

    if args.id:
        cur.execute("SELECT id, url, html_path FROM articles WHERE id = ?", (args.id,))
    else:
        if args.force:
            cur.execute("SELECT id, url, html_path FROM articles ORDER BY id")
        else:
            cur.execute("SELECT id, url, html_path FROM articles WHERE text IS NULL OR trim(text) = '' ORDER BY id")

    rows = cur.fetchall()
    if args.limit:
        rows = rows[:args.limit]

    logging.info("Zu verarbeitende Einträge: %d", len(rows))
    for idx, (row_id, url, html_path) in enumerate(rows, start=1):
        logging.info("[%d/%d] id=%s url=%s", idx, len(rows), row_id, url)
        text = None
        if html_path and os.path.exists(html_path):
            text = extract_text_from_htmlfile(html_path, url=url)
        else:
            logging.info("  -> keine HTML-Datei vorhanden für id=%s (html_path=%s)", row_id, html_path)
            # optional: Fetch vom Web - nicht automatisch, da Login/Consent nötig
        if text:
            update_row_text(conn, row_id, text)
            logging.info("  -> Text gespeichert (len=%d)", len(text))
        else:
            logging.info("  -> Kein Text extrahiert")

    conn.close()
    logging.info("Fertig.")

if __name__ == "__main__":
    main()

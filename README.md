# Newspaper_Webscraper_simple
# Generic News Scraper

Dieses Projekt besteht aus zwei Python-Skripten, die zusammen Nachrichtenartikel von einer Website scrapen, lokal speichern und den Artikeltext extrahieren:

- `scrape_by_start.py` – lädt Artikel-Seiten von einem News-Listing und speichert HTML, Bilder und Metadaten.
- `update_texts.py` – liest die gespeicherten HTML-Dateien und extrahiert bereinigte Artikeltexte in eine SQLite-Datenbank.

> **Hinweis:** Die mitgelieferten Skripte sind absichtlich generisch gehalten. Die echte Ziel-URL und ggf. Cookies müssen lokal konfiguriert werden.

---

## Inhalte

- [Funktionen](#funktionen)
- [Voraussetzungen](#voraussetzungen)
- [Installation](#installation)
- [Konfiguration](#konfiguration)
- [Ordnerstruktur](#ordnerstruktur)
- [Scraper ausführen](#scraper-ausführen)
  - [1. Artikel und HTML-Dateien scrapen (`scrape_by_start.py`)](#1-artikel-und-html-dateien-scrapen-scrape_by_startpy)
  - [2. Artikeltexte extrahieren (`update_texts.py`)](#2-artikeltexte-extrahieren-update_texts-py)
- [Typische Anpassungen](#typische-anpassungen)
- [Hinweise zur Nutzung](#hinweise-zur-nutzung)

---

## Funktionen

### `scrape_by_start.py`

- Ruft eine News-Liste unter 
  `BASE + LISTING_PATH + "?start=N"` 
  für `N = START_FROM .. MAX_START` ab.
- Extrahiert **einen Headline-Link pro Listing-Seite** (konfigurierbar über CSS-Selektoren).
- Lädt jede Artikel-Seite und speichert:
  - Original-HTML in `data/html/`
  - Bilder in `data/images/`
  - Metadaten (URL, Titel, Datum, Autor, Text-Placeholder, HTML-Pfad) in `data/articles.db`.

### `update_texts.py`

- Öffnet die SQLite-Datenbank `data/articles.db`.
- Liest zugehörige HTML-Dateien.
- Extrahiert mit einer robusten Kombination aus:
  - DOM-basiertem Parsing (BeautifulSoup),
  - `trafilatura`,
  - Fallback-Parsing
  den Artikeltext.
- Speichert den bereinigten Text ins Feld `text` der Tabelle `articles`.

---

## Voraussetzungen

- **Python**: Version 3.9 oder höher (empfohlen: 3.10+)
- Betriebssystem: Linux, macOS oder Windows
- Git (optional, aber empfohlen)

Python-Abhängigkeiten (per `pip`):

- `requests`
- `beautifulsoup4`
- `python-slugify`
- `trafilatura`
- `lxml`
- `urllib3`

Beispiel für eine `requirements.txt`:

```txt
requests
beautifulsoup4
python-slugify
trafilatura
lxml
urllib3
```

---

## Installation

### Repository klonen (oder Projektordner anlegen)

```bash
git clone [https://github.com/DEINUSERNAME/DEIN-REPO.git](https://github.com/DEINUSERNAME/DEIN-REPO.git)
cd DEIN-REPO
# Falls das Projekt noch nicht auf GitHub liegt, kannst du die Dateien auch einfach in einen neuen Ordner kopieren.
```

### Python-Umgebung (virtuelles Environment) erstellen

```bash
python -m venv .venv
```

### Virtuelle Umgebung aktivieren

**Linux / macOS:**

```bash
source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
.venv\Scripts\Activate.ps1
```

### Abhängigkeiten installieren

Wenn du eine `requirements.txt` angelegt hast:

```bash
pip install -r requirements.txt
```

Alternativ direkt:

```bash
pip install requests beautifulsoup4 python-slugify trafilatura lxml urllib3
```

---

## Konfiguration

Die wichtigsten Einstellungen befinden sich in `scrape_by_start.py`:

```python
BASE = "[https://example.com](https://example.com)"         # Basis-URL (anpassen!)
LISTING_PATH = "/news/region.html"   # Pfad zur Listing-Seite (anpassen!)
START_FROM = 0                       # erster ?start= Wert
MAX_START = 100                      # letzter ?start= Wert
OUTDIR = "data"                      # Basis-Ausgabeverzeichnis
HTMLDIR = os.path.join(OUTDIR, "html")
IMAGEDIR = os.path.join(OUTDIR, "images")
DBFILE = os.path.join(OUTDIR, "articles.db")
USER_AGENT = "GenericNewsScraper/1.0"
COOKIES_FILE = "cookies.json"        # optional
```

### 1. Zielseite anpassen

**BASE** auf die Basis-URL der Zielseite setzen, z. B.:
```python
BASE = "[https://www.meine-news-seite.de](https://www.meine-news-seite.de)"
```
**LISTING_PATH** auf den Pfad zur Übersichtsseite setzen, z. B.:
```python
LISTING_PATH = "/region/mein-ort.html"
```

### 2. Start-Parameter einstellen

Viele News-Systeme blättern Listen mit einem Parameter wie `?start=0`, `?start=1`, …
Passe **START_FROM** und **MAX_START** an die Struktur der Zielseite an.

**Beispiel:**

```python
START_FROM = 0
MAX_START = 500
```
Tipp: Zum Testen lieber zuerst einen kleinen Bereich (z. B. 0–10) laufen lassen.

### 3. Cookies (optional, z. B. für Paywall / Consent)

Wenn die Seite nur mit bestimmten Cookies voll nutzbar ist:
1. Cookies mit einem Browser-Addon (z. B. als JSON) exportieren.
2. Datei als **`cookies.json`** ins Projektverzeichnis legen.
Die Funktion `load_cookies_into_session` lädt diese automatisch zu Beginn.

---

## Ordnerstruktur

Nach dem ersten Lauf sieht die Struktur typischerweise so aus:

```
DEIN-REPO/
├── scrape_by_start.py
├── update_texts.py
├── requirements.txt      (optional)
├── README.md
└── data/
    ├── html/             # gespeicherte Artikel-HTML-Dateien
    ├── images/           # heruntergeladene Bilder
    └── articles.db       # SQLite-Datenbank mit Metadaten + Text
```
Der Ordner `data/` wird beim ersten Start von `scrape_by_start.py` automatisch angelegt.

---

## Scraper ausführen

### 1. Artikel und HTML-Dateien scrapen (`scrape_by_start.py`)

Stelle sicher, dass deine virtuelle Umgebung aktiv ist und du im Projektordner bist:

```bash
python scrape_by_start.py
```

Das Skript:
* Prüft zunächst die `robots.txt` der Zielseite.
* Ruft für jeden *start*-Wert die Listing-Seite auf.
* Extrahiert aus jeder Listing-Seite den Artikel-Link.
* Lädt den Artikel, speichert HTML/Bilder und trägt die Metadaten in `data/articles.db` ein.

**Beispiel-Logausgabe:**

```log
2025-01-01 12:00:00 INFO Listing prüfen: [https://example.com/news/region.html?start=0](https://example.com/news/region.html?start=0)
2025-01-01 12:00:02 INFO Gefundene Links: 1
2025-01-01 12:00:03 INFO Artikel gespeichert: [https://example.com/news/artikel-123.html](https://example.com/news/artikel-123.html)
...
2025-01-01 12:01:00 INFO Fertig. Daten gespeichert in data
```
Falls keine Links mehr gefunden werden, bricht das Skript frühzeitig ab.

### 2. Artikeltexte extrahieren (`update_texts.py`)

`update_texts.py` arbeitet auf Basis der in `data/articles.db` gespeicherten Einträge und der HTML-Dateien in `data/html/`.

#### Standardfall: Nur Einträge ohne Text verarbeiten

```bash
python update_texts.py
```
* Lädt alle Datensätze, bei denen `text` leer ist oder nur aus Leerzeichen besteht.
* Extrahiert den Artikeltext aus der jeweiligen HTML-Datei.
* Speichert den bereinigten Text in `articles.text`.

#### Alle Einträge neu extrahieren (`--force`)

```bash
python update_texts.py --force
```
* Ignoriert bestehende Texte.
* Extrahiert für alle Datensätze den Text neu (überschreibt vorhandene Inhalte).

#### Einzelnen Artikel per ID verarbeiten (`--id`)

```bash
python update_texts.py --id 42
```
* Verarbeitet nur den Eintrag mit `id = 42`.

#### Anzahl der Einträge begrenzen (`--limit`)

```bash
python update_texts.py --limit 10
```
* Verarbeitet nur die ersten 10 passenden Einträge (z. B. zum Testen).

**Kombinationen sind möglich, z. B.:**

```bash
python update_texts.py --force --limit 20
```

---

## Typische Anpassungen

### CSS-Selektoren für Artikel-Links
In `parse_listing_for_links` in `scrape_by_start.py`:
Passe die Selektoren an die Struktur deiner Zielseite an (z. B. andere Klassen oder Tags).

### Content-Container selektieren
In `extract_from_article_dom` in `update_texts.py`:
Wenn die Seite andere Klassen/Strukturen verwendet, kannst du die Liste der `candidate_selectors` erweitern oder anpassen.

### Rate-Limiting
Über `RATE_BETWEEN_LISTINGS` und `RATE_BETWEEN_ARTICLES` kannst du die Wartezeit zwischen Anfragen konfigurieren, um die Zielseite nicht zu überlasten.

---

## Hinweise zur Nutzung

* **Prüfe vor dem Einsatz die Nutzungsbedingungen und die `robots.txt` der Zielseite.**
* **Verwende den Scraper verantwortungsvoll:**
    * moderate Anzahl von Requests,
    * ausreichende Pausen,
    * nur für zulässige Zwecke.
* **Wenn du das Projekt öffentlich auf GitHub bereitstellst:**
    * Verwende generische Platzhalter (wie hier gezeigt),
    * Hinterlege echte Ziel-URLs und Cookies nur lokal, nicht im Repo.

Viel Spaß beim Scrapen und Analysieren deiner News-Daten!

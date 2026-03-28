#!/usr/bin/env python3
"""
EPG Fetcher - Kostenlose Quellen (ohne Provider-Login)
Holt XMLTV-Daten von freien EPG-Quellen und merged sie zu einer Datei.
Quellen: epgshare01.online (DE + AT), TvProfil (Fallback)
"""
import os
import sys
import time
import gzip
import requests
import xml.etree.ElementTree as ET
from io import BytesIO
from datetime import datetime

# === Konfiguration ===
OUTPUT_FILE = "epg.xml"
MAX_RETRIES = 2
RETRY_DELAY = 15
REQUEST_TIMEOUT = 120

# EPG-Quellen (Reihenfolge = Prioritaet)
EPG_SOURCES = [
    {
        "name": "epgshare01 Deutschland",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz",
        "compressed": True,
        "required": False,
    },
    {
        "name": "epgshare01 Oesterreich",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_AT1.xml.gz",
        "compressed": True,
        "required": False,
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (EPG-Fetcher/2.0; github.com/iambern8/django-epg)",
    "Accept": "application/xml, application/gzip, */*",
    "Accept-Encoding": "gzip, deflate",
}


def fetch_source(source):
    """Einzelne EPG-Quelle herunterladen mit Retry-Logik."""
    name = source["name"]
    url = source["url"]
    compressed = source.get("compressed", False)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  [{name}] Versuch {attempt}/{MAX_RETRIES}...")
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()

            content = resp.content
            if compressed or url.endswith(".gz"):
                try:
                    content = gzip.decompress(content)
                except gzip.BadGzipFile:
                    print(f"  [{name}] Nicht gzip-komprimiert, verwende Rohdaten")

            # Pruefen ob valides XML
            xml_str = content.decode("utf-8", errors="replace")
            if "<tv" not in xml_str[:500]:
                print(f"  [{name}] WARNUNG: Kein gueltiges XMLTV-Format erkannt")
                return None

            size_mb = len(content) / (1024 * 1024)
            print(f"  [{name}] OK - {size_mb:.1f} MB heruntergeladen")
            return content

        except requests.exceptions.RequestException as e:
            print(f"  [{name}] Fehler bei Versuch {attempt}: {e}")
            if attempt < MAX_RETRIES:
                print(f"  [{name}] Warte {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)

    print(f"  [{name}] Alle Versuche fehlgeschlagen!")
    return None


def parse_xmltv(xml_bytes):
    """XMLTV-Daten parsen und Channels + Programmes extrahieren."""
    try:
        root = ET.fromstring(xml_bytes)
        channels = root.findall("channel")
        programmes = root.findall("programme")
        return channels, programmes
    except ET.ParseError as e:
        print(f"  XML-Parse-Fehler: {e}")
        return [], []


def merge_epg(all_sources_data):
    """Alle EPG-Quellen zu einer XMLTV-Datei zusammenfuehren."""
    seen_channel_ids = set()
    all_channels = []
    all_programmes = []

    for source_name, xml_bytes in all_sources_data:
        channels, programmes = parse_xmltv(xml_bytes)
        print(f"  [{source_name}] {len(channels)} Sender, {len(programmes)} Sendungen")

        # Channels hinzufuegen (Duplikate vermeiden)
        for ch in channels:
            ch_id = ch.get("id", "")
            if ch_id and ch_id not in seen_channel_ids:
                seen_channel_ids.add(ch_id)
                all_channels.append(ch)

        # Alle Programmes hinzufuegen
        all_programmes.extend(programmes)

    return all_channels, all_programmes


def build_xmltv(channels, programmes):
    """XMLTV-Dokument aus Channels und Programmes bauen."""
    root = ET.Element("tv")
    root.set("generator-info-name", "django-epg")
    root.set("generator-info-url", "https://github.com/iambern8/django-epg")
    root.set("date", datetime.utcnow().strftime("%Y%m%d%H%M%S"))

    for ch in channels:
        root.append(ch)
    for prog in programmes:
        root.append(prog)

    return root


def write_xmltv(root, filepath):
    """XMLTV-Dokument als Datei schreiben."""
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    with open(filepath, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(b'<!DOCTYPE tv SYSTEM "xmltv.dtd">\n')
        tree.write(f, encoding="UTF-8", xml_declaration=False)

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"\nDatei geschrieben: {filepath} ({size_mb:.1f} MB)")


def main():
    print("=" * 50)
    print("EPG Fetcher - Kostenlose Quellen")
    print("=" * 50)
    print(f"Zeitpunkt: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Quellen: {len(EPG_SOURCES)}")
    print()

    # Alle Quellen herunterladen
    print("1. EPG-Daten herunterladen...")
    successful_sources = []

    for source in EPG_SOURCES:
        xml_bytes = fetch_source(source)
        if xml_bytes:
            successful_sources.append((source["name"], xml_bytes))
        elif source.get("required", False):
            print(f"\nFEHLER: Pflichtquelle '{source['name']}' nicht erreichbar!")
            if os.path.exists(OUTPUT_FILE):
                print(f"Behalte alte {OUTPUT_FILE}")
                sys.exit(0)
            else:
                sys.exit(1)

    if not successful_sources:
        print("\nFEHLER: Keine einzige Quelle erfolgreich!")
        if os.path.exists(OUTPUT_FILE):
            print(f"Behalte alte {OUTPUT_FILE}")
            sys.exit(0)
        else:
            print(f"Keine alte {OUTPUT_FILE} vorhanden.")
            sys.exit(1)

    # EPG-Daten zusammenfuehren
    print(f"\n2. EPG-Daten zusammenfuehren ({len(successful_sources)} Quellen)...")
    channels, programmes = merge_epg(successful_sources)

    if not channels and not programmes:
        print("FEHLER: Keine Sender oder Sendungen nach dem Merge!")
        sys.exit(1)

    # XMLTV schreiben
    print(f"\n3. XMLTV-Datei schreiben...")
    root = build_xmltv(channels, programmes)
    write_xmltv(root, OUTPUT_FILE)

    # Zusammenfassung
    print(f"\n{'=' * 50}")
    print(f"ERGEBNIS:")
    print(f"  Quellen erfolgreich: {len(successful_sources)}/{len(EPG_SOURCES)}")
    print(f"  Sender gesamt: {len(channels)}")
    print(f"  Sendungen gesamt: {len(programmes)}")
    print(f"  Ausgabedatei: {OUTPUT_FILE}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()

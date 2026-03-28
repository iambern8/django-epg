#!/usr/bin/env python3
"""
EPG Fetcher für Strong8k IPTV (Xtream Codes)
Holt XMLTV-Daten vom Provider und speichert sie als epg_strong8k.xml
Zugangsdaten werden über Umgebungsvariablen übergeben (GitHub Secrets).
"""

import os
import sys
import time
import requests
import gzip
from io import BytesIO

# Zugangsdaten aus Umgebungsvariablen
XTREAM_HOST = os.environ.get("XTREAM_HOST")
XTREAM_USER = os.environ.get("XTREAM_USER")
XTREAM_PASS = os.environ.get("XTREAM_PASS")

OUTPUT_FILE = "epg_strong8k.xml"
MAX_RETRIES = 2
RETRY_DELAY = 30  # Sekunden


def validate_env():
      """Prüft ob alle nötigen Umgebungsvariablen gesetzt sind."""
      missing = []
      if not XTREAM_HOST:
                missing.append("XTREAM_HOST")
            if not XTREAM_USER:
                      missing.append("XTREAM_USER")
                  if not XTREAM_PASS:
                            missing.append("XTREAM_PASS")
                        if missing:
                                  print(f"FEHLER: Fehlende Umgebungsvariablen: {', '.join(missing)}")
                                  sys.exit(1)


def fetch_epg():
      """Holt EPG-Daten vom Xtream Codes Endpoint."""
    # Host bereinigen (kein trailing slash)
    host = XTREAM_HOST.rstrip("/")
    if not host.startswith("http"):
              host = f"http://{host}"

    url = f"{host}/xmltv.php?username={XTREAM_USER}&password={XTREAM_PASS}"

    print(f"Rufe EPG-Daten ab von: {host}/xmltv.php")
    print(f"User: {XTREAM_USER[:3]}***")

    for attempt in range(1, MAX_RETRIES + 2):
              try:
                            print(f"Versuch {attempt}/{MAX_RETRIES + 1}...")
                            response = requests.get(url, timeout=120, stream=True)
                            response.raise_for_status()

                  # Prüfen ob Antwort gzip-komprimiert ist
                            content = response.content
                            if content[:2] == b'\x1f\x8b':
                                              print("Antwort ist gzip-komprimiert, dekomprimiere...")
                                              content = gzip.decompress(content)

                            # Prüfen ob gültiges XML
                            xml_text = content.decode("utf-8", errors="replace")
                            if "<?xml" not in xml_text[:100] and "<tv" not in xml_text[:200]:
                                              print("WARNUNG: Antwort scheint kein gültiges XMLTV zu sein!")
                                              print(f"Erste 200 Zeichen: {xml_text[:200]}")
                                              if attempt <= MAX_RETRIES:
                                                                    print(f"Warte {RETRY_DELAY}s vor erneutem Versuch...")
                                                                    time.sleep(RETRY_DELAY)
                                                                    continue
                            else:
                                                  print("Alle Versuche fehlgeschlagen.")
                                                  return None

                            return xml_text

              except requests.exceptions.RequestException as e:
                            print(f"Fehler bei Versuch {attempt}: {e}")
                            if attempt <= MAX_RETRIES:
                                              print(f"Warte {RETRY_DELAY}s vor erneutem Versuch...")
                                              time.sleep(RETRY_DELAY)
              else:
                                print("Alle Versuche fehlgeschlagen.")
                                return None

          return None


def count_channels_and_programmes(xml_text):
      """Zählt Kanäle und Programme im XMLTV."""
    channels = xml_text.count("<channel ")
    programmes = xml_text.count("<programme ")
    return channels, programmes


def main():
      print("=" * 50)
    print("EPG Fetcher Strong8k")
    print("=" * 50)

    validate_env()
    xml_text = fetch_epg()

    if xml_text is None:
              # Bei Fehler: alte Datei behalten falls vorhanden
              if os.path.exists(OUTPUT_FILE):
                            print(f"WARNUNG: Fetch fehlgeschlagen. Behalte alte {OUTPUT_FILE}")
                            sys.exit(0)
    else:
            print(f"FEHLER: Fetch fehlgeschlagen und keine alte {OUTPUT_FILE} vorhanden.")
                  sys.exit(1)

    # EPG-Daten speichern
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
              f.write(xml_text)

    file_size = os.path.getsize(OUTPUT_FILE)
    channels, programmes = count_channels_and_programmes(xml_text)

    print(f"\nErfolgreich gespeichert: {OUTPUT_FILE}")
    print(f"Dateigröße: {file_size / 1024 / 1024:.1f} MB")
    print(f"Kanäle: {channels}")
    print(f"Programme: {programmes}")
    print("=" * 50)

    # Coverage-Check: Kanäle ohne Programme auflisten
    if channels > 0 and programmes == 0:
              print("WARNUNG: Keine Programmdaten gefunden!")


if __name__ == "__main__":
      main()

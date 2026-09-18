#!/usr/bin/env python3
from pathlib import Path
import re

MAIN = Path("Kamery-pogodowe.m3u8")
ONLINE = Path("ipcamlive/ipcamlive_online.m3u8")

def parse_entries(text):
    lines = text.splitlines()
    entries = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            extinf = lines[i].rstrip()
            url = ""
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if not candidate:
                    j += 1
                    continue
                if candidate.startswith("#"):
                    break
                url = candidate
                break
            if url:
                name = extinf.split(",", 1)[1].strip() if "," in extinf else ""
                entries.append({
                    "extinf": extinf,
                    "url": url,
                    "name": name,
                    "start": i,
                    "url_line": j,
                })
                i = j + 1
                continue
        i += 1
    return entries

if not MAIN.exists():
    raise SystemExit(f"Brak pliku: {MAIN}")

if not ONLINE.exists():
    raise SystemExit(f"Brak pliku: {ONLINE}")

main_text = MAIN.read_text(encoding="utf-8")
online_text = ONLINE.read_text(encoding="utf-8")

main_lines = main_text.splitlines()
main_entries = parse_entries(main_text)
online_entries = parse_entries(online_text)

# Indeksy obecnych wpisów po nazwie i URL.
main_by_name = {e["name"]: e for e in main_entries if e["name"]}
main_urls = {e["url"] for e in main_entries if e["url"]}

updated = 0
added = 0
skipped = 0

# Najpierw aktualizujemy istniejące wpisy po IDENTYCZNEJ nazwie.
for e in online_entries:
    name = e["name"]
    url = e["url"]

    if name in main_by_name:
        current = main_by_name[name]
        if current["url"] != url:
            main_lines[current["url_line"]] = url
            updated += 1
            main_urls.discard(current["url"])
            main_urls.add(url)
            current["url"] = url
        else:
            skipped += 1

# Po aktualizacji składamy ponownie tekst.
new_text = "\n".join(main_lines).rstrip() + "\n"

# Dodajemy wpisy, których nazwy nie występowały wcześniej.
append_blocks = []
existing_names = set(main_by_name)

for e in online_entries:
    name = e["name"]
    url = e["url"]

    if name in existing_names:
        continue

    # Jeśli identyczny URL już gdzieś jest, też nie duplikujemy.
    if url in main_urls:
        skipped += 1
        continue

    append_blocks.append(e["extinf"] + "\n" + url)
    existing_names.add(name)
    main_urls.add(url)
    added += 1

if append_blocks:
    new_text += (
        "\n"
        "# ======================================================================\n"
        "# IPCAMLIVE - DZIAŁAJĄCE KAMERY Z AUTOMATYCZNEGO TESTU\n"
        "# ======================================================================\n"
        + "\n".join(append_blocks)
        + "\n"
    )

MAIN.write_text(new_text, encoding="utf-8")

print("=" * 72)
print("MERGE IPCAMLIVE -> Kamery-pogodowe.m3u8")
print("=" * 72)
print("Kamery ONLINE w pliku źródłowym:", len(online_entries))
print("Zaktualizowane istniejące wpisy:", updated)
print("Dodane nowe wpisy:", added)
print("Pominięte / już aktualne:", skipped)
print("Razem wpisów IPCamLive rozpatrzonych:", len(online_entries))

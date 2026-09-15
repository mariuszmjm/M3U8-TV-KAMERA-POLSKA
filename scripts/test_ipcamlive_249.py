#!/usr/bin/env python3
import concurrent.futures
import csv
import pathlib
import time
from urllib.parse import quote, urljoin, urlparse

import requests

BASE_DIR = pathlib.Path(__file__).resolve().parent
INPUT_CSV = BASE_DIR / "ipcamlive_kandydaci_249.csv"

OUT_DIR = pathlib.Path("ipcamlive_results")
OUT_DIR.mkdir(exist_ok=True)

OUT_ALL = OUT_DIR / "ipcamlive_wyniki_wszystkie.csv"
OUT_ONLINE = OUT_DIR / "ipcamlive_online.csv"
OUT_M3U = OUT_DIR / "ipcamlive_online.m3u8"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36"
)

TIMEOUT = 12
WORKERS = 8
RETRIES = 3


def headers(alias):
    return {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": f"https://www.ipcamlive.com/{alias}",
        "Origin": "https://www.ipcamlive.com",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def read_candidates():
    if not INPUT_CSV.exists():
        raise SystemExit(
            f"Brak pliku {INPUT_CSV}. "
            "Umieść ipcamlive_kandydaci_249.csv w folderze scripts."
        )

    rows = []
    with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            alias = (row.get("alias") or "").strip()
            if not alias:
                continue
            rows.append({
                "alias": alias,
                "nazwa": (row.get("nazwa") or alias).strip(),
                "typ": (row.get("typ") or "").strip(),
                "poprzedni_status": (
                    row.get("status_z_ostatniego_testu") or ""
                ).strip(),
                "adres_strony": (
                    row.get("adres_strony")
                    or f"https://www.ipcamlive.com/{alias}"
                ).strip(),
            })
    return rows


def get_state(alias):
    endpoints = [
        (
            "https://www.ipcamlive.com/"
            "ajax/getcamerastreamstate.php"
            f"?cameraalias={quote(alias)}"
        ),
        (
            "https://ipcamlive.com/"
            "ajax/getcamerastreamstate.php"
            f"?cameraalias={quote(alias)}"
        ),
    ]

    last_error = "brak odpowiedzi"

    for attempt in range(1, RETRIES + 1):
        for endpoint in endpoints:
            try:
                r = requests.get(
                    endpoint,
                    headers=headers(alias),
                    timeout=TIMEOUT,
                    allow_redirects=True,
                )

                if r.status_code != 200:
                    last_error = f"HTTP {r.status_code}"
                    continue

                try:
                    data = r.json()
                except Exception as e:
                    last_error = f"JSONDecodeError: {type(e).__name__}"
                    continue

                details = data.get("details") or {}
                streaminfo = data.get("streaminfo") or {}

                address = details.get("address")
                streamid = details.get("streamid")

                if address and streamid:
                    return data, None

                connected = streaminfo.get("connected")
                available = details.get("streamavailable")

                if str(connected) == "0" or str(available) == "0":
                    return data, "OFFLINE"

                last_error = "Brak address lub streamid"

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"

        if attempt < RETRIES:
            time.sleep(1.5 * attempt)

    return None, last_error


def normalize_host(address):
    if not address:
        return None

    parsed = urlparse(address)
    if parsed.netloc:
        return parsed.netloc

    return (
        address.replace("https://", "")
        .replace("http://", "")
        .strip("/")
        .split("/")[0]
    )


def build_urls(address, streamid):
    host = normalize_host(address)
    if not host:
        return []

    return [
        f"https://{host}/streams/{streamid}/stream.m3u8",
        f"https://{host}/streams_storage/{streamid}/stream.m3u8",
    ]


def test_segment(session, url, alias):
    try:
        h = headers(alias)
        h["Range"] = "bytes=0-8191"

        r = session.get(
            url,
            headers=h,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        if r.status_code not in (200, 206):
            return False

        for chunk in r.iter_content(chunk_size=4096):
            if chunk:
                return True

    except Exception:
        pass

    return False


def test_hls(session, url, alias, depth=0):
    if depth > 4:
        return False, "za dużo poziomów HLS"

    try:
        r = session.get(
            url,
            headers=headers(alias),
            timeout=TIMEOUT,
            allow_redirects=True,
        )
    except Exception as e:
        return False, type(e).__name__

    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"

    text = r.text
    if "#EXTM3U" not in text:
        return False, "brak #EXTM3U"

    lines = [x.strip() for x in text.splitlines() if x.strip()]

    if any(x.startswith("#EXT-X-STREAM-INF") for x in lines):
        variants = []
        for i, line in enumerate(lines):
            if not line.startswith("#EXT-X-STREAM-INF"):
                continue
            if i + 1 >= len(lines):
                continue
            child = lines[i + 1]
            if child.startswith("#"):
                continue
            variants.append(urljoin(r.url, child))

        for child in variants:
            ok, info = test_hls(session, child, alias, depth + 1)
            if ok:
                return True, "master + segment OK"

        return False, "master bez działającego wariantu"

    segments = []
    for line in lines:
        if line.startswith("#"):
            continue
        if ".m3u8" in line.lower():
            continue
        segments.append(urljoin(r.url, line))

    if not segments:
        return False, "M3U8 bez segmentów"

    for segment in segments[-3:]:
        if test_segment(session, segment, alias):
            return True, "segment OK"

    return False, "segmenty nie działają"


def extract_stream_info(data):
    details = (data or {}).get("details") or {}
    streaminfo = (data or {}).get("streaminfo") or {}
    video = streaminfo.get("video") or {}

    width = video.get("width")
    height = video.get("height")

    resolution = ""
    if width and height:
        resolution = f"{width}x{height}"

    return {
        "address": details.get("address") or "",
        "streamid": details.get("streamid") or "",
        "connected": streaminfo.get("connected"),
        "available": details.get("streamavailable"),
        "resolution": resolution,
        "fps": video.get("fps") or "",
        "codec": video.get("format") or "",
    }


def check_one(candidate):
    alias = candidate["alias"]
    result = dict(candidate)
    result.update({
        "status": "BRAK",
        "resolution": "",
        "fps": "",
        "codec": "",
        "streamid": "",
        "server": "",
        "hls": "",
        "uwagi": "",
    })

    data, state_error = get_state(alias)

    if state_error == "OFFLINE":
        info = extract_stream_info(data)
        result.update({
            "status": "OFFLINE",
            "resolution": info["resolution"],
            "fps": info["fps"],
            "codec": info["codec"],
            "streamid": info["streamid"],
            "server": info["address"],
            "uwagi": "IPCamLive zgłasza offline",
        })
        return result

    if not data:
        result["status"] = "BRAK/BŁĄD"
        result["uwagi"] = state_error or "brak danych"
        return result

    info = extract_stream_info(data)

    result.update({
        "resolution": info["resolution"],
        "fps": info["fps"],
        "codec": info["codec"],
        "streamid": info["streamid"],
        "server": info["address"],
    })

    if not info["streamid"] or not info["address"]:
        result["status"] = "BRAK/BŁĄD"
        result["uwagi"] = "brak streamid/address"
        return result

    session = requests.Session()
    errors = []

    for url in build_urls(info["address"], info["streamid"]):
        ok, why = test_hls(session, url, alias)
        if ok:
            result["status"] = "ONLINE"
            result["hls"] = url
            result["uwagi"] = why
            return result
        errors.append(f"{url} -> {why}")

    result["status"] = "HLS BŁĄD"
    result["uwagi"] = " | ".join(errors)
    return result


def save_csv(path, rows):
    fields = [
        "status",
        "alias",
        "nazwa",
        "typ",
        "resolution",
        "fps",
        "codec",
        "streamid",
        "server",
        "hls",
        "poprzedni_status",
        "adres_strony",
        "uwagi",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def save_m3u(path, online):
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("#EXTM3U\n")
        for cam in online:
            name = cam["nazwa"].replace('"', "'")
            typ = cam["typ"].replace('"', "'")
            f.write(
                f'#EXTINF:-1 group-title="IPCamLive - {typ}",{name}\n'
            )
            f.write(cam["hls"] + "\n")


def main():
    candidates = read_candidates()

    print("#" * 96)
    print("TEST 249 KANDYDATÓW IPCAMLIVE")
    print("#" * 96)
    print("Liczba wpisów:", len(candidates))
    print("Równoległych testów:", WORKERS)
    print("Prób pobrania stanu na alias:", RETRIES)
    print()

    results = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=WORKERS
    ) as executor:
        future_map = {
            executor.submit(check_one, item): item
            for item in candidates
        }

        total = len(future_map)

        for n, future in enumerate(
            concurrent.futures.as_completed(future_map),
            start=1,
        ):
            candidate = future_map[future]

            try:
                row = future.result()
            except Exception as e:
                row = dict(candidate)
                row.update({
                    "status": "ERROR",
                    "resolution": "",
                    "fps": "",
                    "codec": "",
                    "streamid": "",
                    "server": "",
                    "hls": "",
                    "uwagi": repr(e),
                })

            results.append(row)

            print(
                f"[{n:03d}/{total:03d}] "
                f"{row['status']:<10} "
                f"{row['alias']:<28} "
                f"{row['nazwa']}"
            )

    order = {
        "ONLINE": 0,
        "OFFLINE": 1,
        "HLS BŁĄD": 2,
        "BRAK/BŁĄD": 3,
        "ERROR": 4,
    }

    results.sort(
        key=lambda x: (
            order.get(x["status"], 9),
            x["typ"].lower(),
            x["nazwa"].lower(),
        )
    )

    online = [x for x in results if x["status"] == "ONLINE"]

    save_csv(OUT_ALL, results)
    save_csv(OUT_ONLINE, online)
    save_m3u(OUT_M3U, online)

    counts = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    print()
    print("#" * 96)
    print("PODSUMOWANIE")
    print("#" * 96)
    for status in ["ONLINE", "OFFLINE", "HLS BŁĄD", "BRAK/BŁĄD", "ERROR"]:
        print(f"{status:<12}: {counts.get(status, 0)}")

    print()
    print("#" * 96)
    print("DZIAŁAJĄCE KAMERY")
    print("#" * 96)

    for n, cam in enumerate(online, start=1):
        print()
        print(f"[{n}] {cam['nazwa']}")
        print("Typ:", cam["typ"] or "?")
        print("Alias:", cam["alias"])
        print("Rozdzielczość:", cam["resolution"] or "?")
        print("FPS:", cam["fps"] or "?")
        print("Kodek:", cam["codec"] or "?")
        print("HLS:", cam["hls"])
        print("Strona:", cam["adres_strony"])

    print()
    print("#" * 96)
    print("PLIKI WYNIKOWE")
    print("#" * 96)
    print(OUT_ALL)
    print(OUT_ONLINE)
    print(OUT_M3U)


if __name__ == "__main__":
    main()

import pathlib
import re
from urllib.parse import urljoin

import requests


PLAYLIST_FILE = pathlib.Path("Kamery-pogodowe.m3u8")

SERVERS = [2, 3, 4]

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
    "Referer": "https://ibericam.com/",
    "Origin": "https://ibericam.com",
}

IBERICAM_RE = re.compile(
    r"https?://webcam-(\d+)\.ibericam\.com:5443/"
    r"live/streams/([^?\s]+)\.m3u8"
    r"(?:\?[^\s]*)?",
    re.IGNORECASE,
)


def get_camera_name(lines, index):

    if index <= 0:
        return "(nieznana kamera)"

    line = lines[index - 1]

    if not line.startswith("#EXTINF"):
        return "(nieznana kamera)"

    if "," not in line:
        return "(nieznana kamera)"

    return line.split(",", 1)[1].strip()


def test_segment(session, segment_url):

    try:

        headers = HEADERS.copy()

        # Nie pobieramy całego segmentu.
        headers["Range"] = "bytes=0-1023"

        response = session.get(
            segment_url,
            headers=headers,
            timeout=12,
            allow_redirects=True,
            stream=True,
        )

        return response.status_code in (
            200,
            206,
        )

    except Exception:
        return False


def check_hls(session, url, depth=0):

    """
    Sprawdza:
    - HTTP 200
    - #EXTM3U
    - master playlist
    - media playlist
    - rzeczywisty segment video

    Zwraca:
    {
        ok: bool,
        status: str,
        segments: int
    }
    """

    if depth > 2:

        return {
            "ok": False,
            "status": "ZA DUŻO POZIOMÓW",
            "segments": 0,
        }

    try:

        response = session.get(
            url,
            headers=HEADERS,
            timeout=15,
            allow_redirects=True,
        )

    except Exception as e:

        return {
            "ok": False,
            "status": f"ERROR: {e}",
            "segments": 0,
        }

    if response.status_code != 200:

        return {
            "ok": False,
            "status": (
                f"HTTP {response.status_code}"
            ),
            "segments": 0,
        }

    text = response.text

    if "#EXTM3U" not in text:

        return {
            "ok": False,
            "status": "BRAK #EXTM3U",
            "segments": 0,
        }

    playlist_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # --------------------------------------------
    # MASTER PLAYLIST
    # --------------------------------------------

    if any(
        line.startswith("#EXT-X-STREAM-INF")
        for line in playlist_lines
    ):

        children = []

        for index, line in enumerate(
            playlist_lines
        ):

            if not line.startswith(
                "#EXT-X-STREAM-INF"
            ):
                continue

            if index + 1 >= len(
                playlist_lines
            ):
                continue

            child = playlist_lines[
                index + 1
            ]

            if child.startswith("#"):
                continue

            children.append(
                urljoin(
                    response.url,
                    child
                )
            )

        for child_url in children:

            result = check_hls(
                session,
                child_url,
                depth + 1,
            )

            if result["ok"]:

                return result

        return {
            "ok": False,
            "status": (
                "MASTER BEZ DZIAŁAJĄCEGO "
                "WARIANTU"
            ),
            "segments": 0,
        }

    # --------------------------------------------
    # MEDIA PLAYLIST
    # --------------------------------------------

    segment_urls = []

    for line in playlist_lines:

        if line.startswith("#"):
            continue

        segment_urls.append(
            urljoin(
                response.url,
                line
            )
        )

    extinf_count = sum(
        1
        for line in playlist_lines
        if line.startswith("#EXTINF:")
    )

    if (
        not segment_urls
        or extinf_count == 0
    ):

        return {
            "ok": False,
            "status": (
                "M3U8 BEZ SEGMENTÓW"
            ),
            "segments": 0,
        }

    # Sprawdzamy maksymalnie pierwsze
    # trzy segmenty.
    #
    # Wystarczy, że jeden jest osiągalny.

    for segment_url in segment_urls[:3]:

        if test_segment(
            session,
            segment_url
        ):

            return {
                "ok": True,
                "status": "OK",
                "segments": extinf_count,
            }

    return {
        "ok": False,
        "status": (
            "PLAYLISTA JEST, "
            "ALE SEGMENTY NIE DZIAŁAJĄ"
        ),
        "segments": extinf_count,
    }


def build_url(server, slug):

    return (
        f"https://webcam-{server}."
        f"ibericam.com:5443/"
        f"live/streams/"
        f"{slug}.m3u8"
    )


def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    cameras = []

    for index, line in enumerate(lines):

        match = IBERICAM_RE.search(
            line
        )

        if not match:
            continue

        cameras.append({
            "line_index": index,
            "name": get_camera_name(
                lines,
                index
            ),
            "server": int(
                match.group(1)
            ),
            "slug": match.group(2),
            "url": line.strip(),
        })

    print()
    print("#" * 78)
    print(
        "AUTOMATYCZNA AKTUALIZACJA IBERICAM"
    )
    print("#" * 78)

    print(
        "Znalezionych kamer Ibericam:",
        len(cameras)
    )

    session = requests.Session()

    changed = False

    working_count = 0
    updated_count = 0
    unavailable_count = 0

    for number, camera in enumerate(
        cameras,
        start=1
    ):

        print()
        print("=" * 78)

        print(
            f"[{number}/{len(cameras)}]"
        )

        print(
            "KAMERA:",
            camera["name"]
        )

        print(
            "SLUG:",
            camera["slug"]
        )

        print(
            "OBECNY SERWER:",
            f"webcam-{camera['server']}"
        )

        print(
            "OBECNY URL:"
        )

        print(
            camera["url"]
        )

        # ----------------------------------------
        # 1. Najpierw sprawdzamy obecny URL.
        # ----------------------------------------

        current_result = check_hls(
            session,
            camera["url"],
        )

        print()
        print(
            "TEST OBECNEGO:"
        )

        print(
            current_result["status"],
            "| segmenty:",
            current_result["segments"],
        )

        if current_result["ok"]:

            print(
                ">>> OBECNY ADRES DZIAŁA - "
                "NIC NIE ZMIENIAM <<<"
            )

            working_count += 1

            continue

        # ----------------------------------------
        # 2. Obecny URL nie działa.
        #    Szukamy tego samego sluga
        #    na pozostałych serwerach.
        # ----------------------------------------

        print()
        print(
            ">>> OBECNY ADRES NIE DZIAŁA <<<"
        )

        replacement = None

        # Preferencja:
        # najpierw pozostałe serwery.
        #
        # Nie ma webcam-1, ponieważ test
        # wykazał brak DNS.

        for server in SERVERS:

            if server == camera["server"]:
                continue

            candidate = build_url(
                server,
                camera["slug"],
            )

            print()
            print(
                f"SPRAWDZAM webcam-{server}:"
            )

            print(candidate)

            result = check_hls(
                session,
                candidate,
            )

            print(
                result["status"],
                "| segmenty:",
                result["segments"],
            )

            if result["ok"]:

                replacement = candidate

                print()
                print(
                    ">>> ZNALEZIONO "
                    "DZIAŁAJĄCĄ ALTERNATYWĘ <<<"
                )

                break

        # ----------------------------------------
        # 3. Nie ma alternatywy.
        #    Stary wpis zostaje.
        # ----------------------------------------

        if not replacement:

            print()
            print(
                "BRAK DZIAŁAJĄCEJ "
                "ALTERNATYWY."
            )

            print(
                "Stary adres pozostaje "
                "bez zmian."
            )

            unavailable_count += 1

            continue

        # ----------------------------------------
        # 4. Podmiana tylko adresu.
        # ----------------------------------------

        line_index = camera[
            "line_index"
        ]

        old_url = lines[
            line_index
        ]

        lines[
            line_index
        ] = replacement

        print()
        print(
            "AKTUALIZUJĘ:"
        )

        print(
            camera["name"]
        )

        print(
            "STARY:"
        )

        print(
            old_url
        )

        print(
            "NOWY:"
        )

        print(
            replacement
        )

        changed = True
        updated_count += 1

    # --------------------------------------------
    # ZAPIS
    # --------------------------------------------

    if changed:

        PLAYLIST_FILE.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        print()
        print("#" * 78)

        print(
            "ZAPISANO ZMIANY W "
            "Kamery-pogodowe.m3u8"
        )

        print("#" * 78)

    else:

        print()
        print(
            "Brak zmian do zapisania."
        )

    print()
    print("#" * 78)
    print(
        "PODSUMOWANIE IBERICAM"
    )
    print("#" * 78)

    print(
        "Obecne działały:",
        working_count
    )

    print(
        "Zaktualizowane:",
        updated_count
    )

    print(
        "Brak działającej alternatywy:",
        unavailable_count
    )

    print("#" * 78)


if __name__ == "__main__":
    main()

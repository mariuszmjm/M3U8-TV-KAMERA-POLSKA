import pathlib
import re
import socket
from urllib.parse import urljoin

import requests


PLAYLIST_FILE = pathlib.Path(
    "Kamery-pogodowe.m3u8"
)

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
    "Referer": "https://www.webcamera.pl/",
    "Origin": "https://www.webcamera.pl",
}


# Przykład:
#
# https://hoktastream4.webcamera.pl/
# sopot_cam_caff26/
# sopot_cam_caff26.stream/
# playlist.m3u8
#
# Zapamiętujemy:
# - numer serwera
# - CAŁĄ dalszą część adresu
#
WEBCAMERA_RE = re.compile(
    r"https?://hoktastream"
    r"(?P<server>\d+)"
    r"\.webcamera\.pl"
    r"(?P<tail>/[^\s?#]+/playlist\.m3u8"
    r"(?:\?[^\s]*)?)",
    re.IGNORECASE,
)


def get_camera_name(lines, index):

    if index <= 0:
        return "(nieznana kamera)"

    line = lines[index - 1]

    if (
        not line.startswith("#EXTINF")
        or "," not in line
    ):
        return "(nieznana kamera)"

    return line.split(",", 1)[1].strip()


def discover_servers(observed_servers):

    """
    Sprawdza, które hosty:
      hoktastream1.webcamera.pl
      ...
      hoktastream9.webcamera.pl

    istnieją w DNS.

    Dzięki temu, jeżeli kiedyś pojawi się
    hoktastream5, skrypt może go wykryć.
    """

    found = set(observed_servers)

    print()
    print("Sprawdzam dostępne serwery WebCamera...")

    for number in range(1, 10):

        host = (
            f"hoktastream{number}."
            f"webcamera.pl"
        )

        try:

            socket.getaddrinfo(
                host,
                443,
            )

            found.add(number)

            print(
                f"  {host}: DNS OK"
            )

        except socket.gaierror:

            print(
                f"  {host}: brak DNS"
            )

    return sorted(found)


def test_segment(
    session,
    segment_url,
):

    try:

        headers = HEADERS.copy()

        # Nie pobieramy całego segmentu.
        headers["Range"] = "bytes=0-2047"

        response = session.get(
            segment_url,
            headers=headers,
            timeout=10,
            allow_redirects=True,
            stream=True,
        )

        return response.status_code in (
            200,
            206,
        )

    except Exception:
        return False


def check_hls(
    session,
    url,
    depth=0,
):

    """
    Sprawdza:
    - odpowiedź HTTP
    - #EXTM3U
    - master playlist
    - media playlist
    - rzeczywisty segment

    Zwraca słownik:
      ok
      status
      segments
    """

    if depth > 3:

        return {
            "ok": False,
            "status": "ZA DUŻO POZIOMÓW",
            "segments": 0,
        }

    try:

        response = session.get(
            url,
            headers=HEADERS,
            timeout=12,
            allow_redirects=True,
        )

    except Exception as e:

        return {
            "ok": False,
            "status": (
                f"ERROR: "
                f"{type(e).__name__}"
            ),
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

    # -----------------------------------------
    # MASTER PLAYLIST
    # -----------------------------------------

    if any(
        line.startswith(
            "#EXT-X-STREAM-INF"
        )
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

            if (
                index + 1
                >= len(playlist_lines)
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
                    child,
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
                "MASTER BEZ "
                "DZIAŁAJĄCEGO WARIANTU"
            ),
            "segments": 0,
        }

    # -----------------------------------------
    # MEDIA PLAYLIST
    # -----------------------------------------

    extinf_count = sum(
        1
        for line in playlist_lines
        if line.startswith("#EXTINF:")
    )

    segments = []

    for line in playlist_lines:

        if line.startswith("#"):
            continue

        # Gdyby pojawiła się kolejna
        # playlista, nie traktujemy jej
        # jako segmentu.
        if ".m3u8" in line.lower():
            continue

        segments.append(
            urljoin(
                response.url,
                line,
            )
        )

    if (
        extinf_count == 0
        or not segments
    ):

        return {
            "ok": False,
            "status": (
                "M3U8 BEZ SEGMENTÓW"
            ),
            "segments": 0,
        }

    # LIVE:
    # najlepiej sprawdzić najnowsze
    # segmenty.

    for segment_url in segments[-3:]:

        if test_segment(
            session,
            segment_url,
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


def build_url(server, tail):

    return (
        f"https://hoktastream{server}."
        f"webcamera.pl"
        f"{tail}"
    )


def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    # Kluczem jest dalsza część adresu.
    #
    # Czyli np.:
    #
    # /sopot_cam_caff26/
    # sopot_cam_caff26.stream/
    # playlist.m3u8
    #
    # Dzięki temu numer serwera
    # może się dowolnie zmienić.

    cameras = {}

    observed_servers = set()

    for index, line in enumerate(lines):

        match = WEBCAMERA_RE.search(
            line
        )

        if not match:
            continue

        server = int(
            match.group("server")
        )

        tail = match.group("tail")

        observed_servers.add(server)

        if tail not in cameras:
            cameras[tail] = []

        cameras[tail].append({
            "line_index": index,
            "name": get_camera_name(
                lines,
                index,
            ),
            "server": server,
            "url": line.strip(),
        })

    print()
    print("#" * 78)
    print(
        "AUTOMATYCZNA AKTUALIZACJA "
        "WEBCAMERA.PL"
    )
    print("#" * 78)

    print(
        "Unikalnych kamer WebCamera:",
        len(cameras)
    )

    print(
        "Wszystkich wpisów WebCamera:",
        sum(
            len(entries)
            for entries in cameras.values()
        )
    )

    print(
        "Serwery występujące w M3U:",
        sorted(observed_servers)
    )

    servers = discover_servers(
        observed_servers
    )

    print()
    print(
        "Serwery do sprawdzania:",
        servers
    )

    session = requests.Session()

    changed = False

    working_count = 0
    moved_count = 0
    failed_count = 0
    changed_entries = 0

    for number, (
        tail,
        entries,
    ) in enumerate(
        cameras.items(),
        start=1,
    ):

        print()
        print("=" * 78)

        print(
            f"[{number}/{len(cameras)}]"
        )

        for entry in entries:

            print(
                "KAMERA:",
                entry["name"]
            )

            print(
                "SERWER:",
                f"hoktastream"
                f"{entry['server']}"
            )

            print(
                "OBECNY URL:"
            )

            print(
                entry["url"]
            )

        # ---------------------------------------
        # Najpierw sprawdzamy wszystkie
        # istniejące URL-e tej samej kamery.
        # ---------------------------------------

        unique_old_urls = []

        for entry in entries:

            if (
                entry["url"]
                not in unique_old_urls
            ):
                unique_old_urls.append(
                    entry["url"]
                )

        working_url = None

        for old_url in unique_old_urls:

            print()
            print(
                "Sprawdzam obecny adres:"
            )

            print(old_url)

            result = check_hls(
                session,
                old_url,
            )

            print(
                result["status"],
                "| segmenty:",
                result["segments"],
            )

            if result["ok"]:

                working_url = old_url
                break

        # ---------------------------------------
        # DZIAŁA
        # ---------------------------------------

        if working_url:

            print()
            print(
                ">>> OBECNY SERWER DZIAŁA - "
                "NIC NIE ZMIENIAM <<<"
            )

            working_count += 1

            # Jeżeli ta sama kamera występuje
            # kilka razy z różnymi hostami,
            # ujednolicamy do działającego URL.

            for entry in entries:

                index = entry[
                    "line_index"
                ]

                if (
                    lines[index]
                    != working_url
                ):

                    print(
                        "Ujednolicam duplikat:"
                    )

                    print(
                        " ",
                        entry["name"]
                    )

                    lines[index] = (
                        working_url
                    )

                    changed = True
                    changed_entries += 1

            continue

        # ---------------------------------------
        # NIE DZIAŁA
        # ---------------------------------------

        print()
        print(
            ">>> OBECNY SERWER "
            "NIE DZIAŁA <<<"
        )

        current_servers = {
            entry["server"]
            for entry in entries
        }

        replacement = None

        for server in servers:

            if server in current_servers:
                continue

            candidate = build_url(
                server,
                tail,
            )

            print()
            print(
                f"Sprawdzam "
                f"hoktastream{server}:"
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
                    "DZIAŁAJĄCY SERWER <<<"
                )

                break

        # ---------------------------------------
        # Żaden serwer nie działa.
        # Nie usuwamy starego wpisu.
        # ---------------------------------------

        if not replacement:

            print()
            print(
                "BRAK DZIAŁAJĄCEGO "
                "SERWERA."
            )

            print(
                "Stary wpis pozostaje "
                "bez zmian."
            )

            failed_count += 1

            continue

        # ---------------------------------------
        # Podmieniamy wszystkie wystąpienia
        # tej samej kamery.
        # ---------------------------------------

        moved_this_camera = False

        for entry in entries:

            index = entry[
                "line_index"
            ]

            old_url = lines[index]

            if old_url == replacement:
                continue

            print()
            print(
                "AKTUALIZUJĘ:"
            )

            print(
                entry["name"]
            )

            print(
                "STARY:"
            )

            print(old_url)

            print(
                "NOWY:"
            )

            print(replacement)

            lines[index] = replacement

            changed = True
            changed_entries += 1
            moved_this_camera = True

        if moved_this_camera:
            moved_count += 1

    # -------------------------------------------
    # ZAPIS
    # -------------------------------------------

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
        "PODSUMOWANIE WEBCAMERA.PL"
    )
    print("#" * 78)

    print(
        "Już działały:",
        working_count
    )

    print(
        "Przeniesione na inny serwer:",
        moved_count
    )

    print(
        "Zmienione wpisy M3U:",
        changed_entries
    )

    print(
        "Brak działającego serwera:",
        failed_count
    )

    print("#" * 78)


if __name__ == "__main__":
    main()

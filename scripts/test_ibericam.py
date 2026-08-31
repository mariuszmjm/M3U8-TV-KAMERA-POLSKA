import pathlib
import re
from urllib.parse import urljoin

import requests


PLAYLIST_FILE = pathlib.Path("Kamery-pogodowe.m3u8")

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

# Przykład:
#
# https://webcam-4.ibericam.com:5443/live/streams/granada.m3u8

IBERICAM_RE = re.compile(
    r"https?://webcam-(\d+)\.ibericam\.com:5443/"
    r"live/streams/([^?\s]+)\.m3u8",
    re.IGNORECASE,
)

SERVERS = [1, 2, 3, 4]


def camera_name(lines, index):

    if index <= 0:
        return "(nieznana kamera)"

    line = lines[index - 1]

    if not line.startswith("#EXTINF"):
        return "(nieznana kamera)"

    if "," not in line:
        return "(nieznana kamera)"

    return line.split(",", 1)[1].strip()


def check_media_playlist(session, url):

    """
    Zwraca:
      OK / MASTER / EMPTY / HTTP xxx / ERROR
    """

    try:

        response = session.get(
            url,
            headers=HEADERS,
            timeout=15,
            allow_redirects=True,
        )

    except Exception as e:

        return {
            "status": "ERROR",
            "detail": str(e),
            "final_url": url,
            "segments": 0,
        }

    if response.status_code != 200:

        return {
            "status": f"HTTP {response.status_code}",
            "detail": "",
            "final_url": response.url,
            "segments": 0,
        }

    text = response.text.strip()

    if "#EXTM3U" not in text:

        return {
            "status": "NOT_M3U8",
            "detail": "",
            "final_url": response.url,
            "segments": 0,
        }

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # ------------------------------------------------------
    # MASTER PLAYLIST
    # ------------------------------------------------------

    if any(
        line.startswith("#EXT-X-STREAM-INF")
        for line in lines
    ):

        children = []

        for i, line in enumerate(lines):

            if not line.startswith(
                "#EXT-X-STREAM-INF"
            ):
                continue

            if i + 1 >= len(lines):
                continue

            child = lines[i + 1]

            if child.startswith("#"):
                continue

            children.append(
                urljoin(
                    response.url,
                    child
                )
            )

        for child_url in children:

            child_result = check_media_playlist(
                session,
                child_url
            )

            if child_result["status"] == "OK":

                child_result["master"] = (
                    response.url
                )

                return child_result

        return {
            "status": "MASTER_NO_MEDIA",
            "detail": (
                f"wariantów: {len(children)}"
            ),
            "final_url": response.url,
            "segments": 0,
        }

    # ------------------------------------------------------
    # MEDIA PLAYLIST
    # ------------------------------------------------------

    segments = []

    for line in lines:

        if line.startswith("#"):
            continue

        lower = line.lower()

        # HLS może mieć .ts, .m4s itd.
        if (
            ".ts" in lower
            or ".m4s" in lower
            or ".mp4" in lower
            or ".aac" in lower
        ):
            segments.append(line)

    # Czasami rozszerzenie segmentu jest nietypowe.
    # Dlatego #EXTINF także traktujemy
    # jako mocny znak żywej playlisty.

    extinf_count = sum(
        1
        for line in lines
        if line.startswith("#EXTINF:")
    )

    if segments or extinf_count > 0:

        return {
            "status": "OK",
            "detail": "",
            "final_url": response.url,
            "segments": max(
                len(segments),
                extinf_count,
            ),
        }

    return {
        "status": "EMPTY",
        "detail": (
            "M3U8 istnieje, ale brak segmentów"
        ),
        "final_url": response.url,
        "segments": 0,
    }


def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    cameras = []

    for index, line in enumerate(lines):

        match = IBERICAM_RE.search(line)

        if not match:
            continue

        current_server = int(
            match.group(1)
        )

        slug = match.group(2)

        cameras.append({
            "name": camera_name(
                lines,
                index
            ),
            "slug": slug,
            "current_server": current_server,
            "current_url": line.strip(),
        })

    print()
    print("#" * 80)
    print("TEST IBERICAM")
    print("#" * 80)

    print(
        "Znalezionych kamer Ibericam:",
        len(cameras)
    )

    print()

    session = requests.Session()

    working_current = 0
    alternate_found = 0
    completely_dead = 0

    for number, camera in enumerate(
        cameras,
        start=1
    ):

        print()
        print("=" * 80)

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
            f"webcam-{camera['current_server']}"
        )

        print(
            "OBECNY URL:"
        )

        print(
            camera["current_url"]
        )

        results = {}

        # Najpierw obecny serwer,
        # później pozostałe.

        server_order = [
            camera["current_server"]
        ]

        for server in SERVERS:

            if server not in server_order:
                server_order.append(server)

        for server in server_order:

            candidate = (
                f"https://webcam-{server}."
                f"ibericam.com:5443/"
                f"live/streams/"
                f"{camera['slug']}.m3u8"
            )

            result = check_media_playlist(
                session,
                candidate
            )

            results[server] = result

            print()

            print(
                f"webcam-{server}:",
                result["status"],
                f"| segmenty: "
                f"{result['segments']}"
            )

            if (
                result["final_url"]
                != candidate
            ):

                print(
                    "  FINAL URL:"
                )

                print(
                    " ",
                    result["final_url"]
                )

            if result["detail"]:

                print(
                    "  INFO:",
                    result["detail"]
                )

        current_result = results[
            camera["current_server"]
        ]

        working_servers = [
            server
            for server, result
            in results.items()
            if result["status"] == "OK"
        ]

        print()
        print("-" * 80)

        if current_result["status"] == "OK":

            working_current += 1

            print(
                "WYNIK: OBECNY ADRES DZIAŁA"
            )

            if len(working_servers) > 1:

                print(
                    "Działają także serwery:",
                    ", ".join(
                        f"webcam-{s}"
                        for s in working_servers
                        if s
                        != camera["current_server"]
                    )
                )

        elif working_servers:

            alternate_found += 1

            print(
                "WYNIK: OBECNY ADRES NIE DZIAŁA"
            )

            print(
                "ALE DZIAŁA ALTERNATYWA:"
            )

            for server in working_servers:

                print(
                    " ",
                    f"https://webcam-{server}."
                    f"ibericam.com:5443/"
                    f"live/streams/"
                    f"{camera['slug']}.m3u8"
                )

        else:

            completely_dead += 1

            print(
                "WYNIK: BRAK DZIAŁAJĄCEGO "
                "SERWERA 1-4"
            )

    print()
    print("#" * 80)
    print("PODSUMOWANIE IBERICAM")
    print("#" * 80)

    print(
        "Obecny adres działa:",
        working_current
    )

    print(
        "Obecny nie działa, "
        "ale znaleziono alternatywę:",
        alternate_found
    )

    print(
        "Brak działającego serwera:",
        completely_dead
    )

    print("#" * 80)


if __name__ == "__main__":
    main()

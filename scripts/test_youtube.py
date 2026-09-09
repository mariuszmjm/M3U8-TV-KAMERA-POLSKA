import json
import subprocess
import sys
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import requests


VIDEO_URL = "https://www.youtube.com/watch?v=5uZa3-RMFos"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36"
)


def get_info():
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--dump-single-json",
        VIDEO_URL,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("BŁĄD yt-dlp:")
        print(result.stderr)
        sys.exit(1)

    return json.loads(result.stdout)


def show_expiry(url):
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        expire = params.get("expire", [None])[0]

        if expire:
            dt = datetime.fromtimestamp(
                int(expire)
            )

            print(
                "Ważność URL do około:",
                dt.strftime("%Y-%m-%d %H:%M:%S")
            )

    except Exception:
        pass


def test_m3u8(url):
    print()
    print("TEST HLS:")
    print(url)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
    }

    try:
        r = requests.get(
            url,
            headers=headers,
            timeout=20,
            allow_redirects=True,
        )

    except Exception as e:
        print("BŁĄD:", repr(e))
        return False

    print("HTTP:", r.status_code)
    print(
        "Content-Type:",
        r.headers.get("Content-Type")
    )

    if r.status_code != 200:
        return False

    if "#EXTM3U" not in r.text:
        print("Brak #EXTM3U")
        return False

    print(">>> PLAYLISTA M3U8 DZIAŁA <<<")

    lines = [
        x.strip()
        for x in r.text.splitlines()
        if x.strip()
    ]

    print()
    print("Pierwsze linie playlisty:")

    for line in lines[:15]:
        print(line)

    return True


def main():
    print("#" * 76)
    print("TEST YOUTUBE LIVE -> HLS")
    print("#" * 76)

    print()
    print("YouTube:")
    print(VIDEO_URL)

    info = get_info()

    print()
    print("TYTUŁ:")
    print(info.get("title"))

    print()
    print(
        "IS LIVE:",
        info.get("is_live")
    )

    print(
        "LIVE STATUS:",
        info.get("live_status")
    )

    formats = info.get("formats", [])

    hls = []

    for f in formats:
        protocol = str(
            f.get("protocol", "")
        ).lower()

        url = f.get("url")

        if not url:
            continue

        if (
            "m3u8" in protocol
            or ".m3u8" in url.lower()
            or "manifest/hls" in url.lower()
        ):
            hls.append(f)

    print()
    print(
        "Formatów HLS znalezionych:",
        len(hls)
    )

    if not hls:
        print()
        print(
            "BRAK HLS."
        )
        print(
            "YouTube prawdopodobnie udostępnia "
            "ten stream jako DASH albo inną "
            "formę strumienia."
        )
        return

    # Preferujemy format z audio + video.
    hls.sort(
        key=lambda f: (
            f.get("vcodec") != "none",
            f.get("acodec") != "none",
            f.get("height") or 0,
        ),
        reverse=True,
    )

    for i, f in enumerate(hls[:10], 1):

        print()
        print("-" * 76)

        print(
            f"HLS #{i}"
        )

        print(
            "format_id:",
            f.get("format_id")
        )

        print(
            "rozdzielczość:",
            f.get("resolution")
        )

        print(
            "video:",
            f.get("vcodec")
        )

        print(
            "audio:",
            f.get("acodec")
        )

        print(
            "protocol:",
            f.get("protocol")
        )

        url = f.get("url")

        print()
        print("URL:")
        print(url)

        show_expiry(url)

        if test_m3u8(url):

            print()
            print("#" * 76)
            print(
                "DZIAŁAJĄCY ADRES DO TESTU "
                "W M3U-IP.TV:"
            )
            print()
            print(url)
            print()
            print(
                "Skopiuj go od razu po "
                "zakończeniu Action."
            )
            print("#" * 76)

            return

    print()
    print(
        "Znaleziono formaty HLS, ale żaden "
        "nie przeszedł testu."
    )


if __name__ == "__main__":
    main()

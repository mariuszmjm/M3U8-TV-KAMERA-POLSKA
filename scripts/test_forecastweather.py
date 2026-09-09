import pathlib
import re
import time
import hashlib
from urllib.parse import urljoin

import requests
import urllib3


urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

PLAYLIST_FILE = pathlib.Path(
    "Kamery-pogodowe.m3u8"
)

WAIT_SECONDS = 20

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
    "Referer": "https://www.forecastweather.gr/",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

FORECAST_RE = re.compile(
    r"https?://streaming\.forecastweather\.gr"
    r":8090/live/"
    r"([^/?#\s]+)/playlist\.m3u8"
    r"(?:\?[^\s]*)?",
    re.IGNORECASE,
)


def camera_name(lines, index):

    if index <= 0:
        return "(nieznana kamera)"

    line = lines[index - 1]

    if (
        not line.startswith("#EXTINF")
        or "," not in line
    ):
        return "(nieznana kamera)"

    return line.split(",", 1)[1].strip()


def get_playlist(session, url):

    try:

        response = session.get(
            url,
            headers=HEADERS,
            timeout=15,
            allow_redirects=True,
            verify=False,
        )

        if response.status_code != 200:

            return None, (
                f"HTTP {response.status_code}"
            )

        if "#EXTM3U" not in response.text:

            return None, "BRAK #EXTM3U"

        return response, "OK"

    except Exception as e:

        return None, (
            f"{type(e).__name__}: {e}"
        )


def resolve_media_playlist(
    session,
    url,
    depth=0,
):

    if depth > 3:
        return None

    response, status = get_playlist(
        session,
        url,
    )

    if response is None:
        return {
            "ok": False,
            "status": status,
        }

    lines = [
        x.strip()
        for x in response.text.splitlines()
        if x.strip()
    ]

    # MASTER PLAYLIST

    if any(
        x.startswith("#EXT-X-STREAM-INF")
        for x in lines
    ):

        variants = []

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

            variants.append(
                urljoin(
                    response.url,
                    child,
                )
            )

        for child in variants:

            result = resolve_media_playlist(
                session,
                child,
                depth + 1,
            )

            if result and result.get("ok"):
                return result

        return {
            "ok": False,
            "status": (
                "MASTER BEZ DZIAŁAJĄCEGO "
                "WARIANTU"
            ),
        }

    # MEDIA PLAYLIST

    sequence = None
    program_date_time = None

    for line in lines:

        if line.startswith(
            "#EXT-X-MEDIA-SEQUENCE:"
        ):

            try:
                sequence = int(
                    line.split(":", 1)[1]
                )
            except Exception:
                pass

        if line.startswith(
            "#EXT-X-PROGRAM-DATE-TIME:"
        ):
            program_date_time = (
                line.split(":", 1)[1]
            )

    segments = []

    for line in lines:

        if line.startswith("#"):
            continue

        if ".m3u8" in line.lower():
            continue

        segments.append(
            urljoin(
                response.url,
                line,
            )
        )

    if not segments:

        return {
            "ok": False,
            "status": "BRAK SEGMENTÓW",
        }

    last_segment = segments[-1]

    # Pobieramy kawałek ostatniego segmentu
    # i robimy jego hash.

    segment_hash = None
    segment_status = None

    try:

        h = HEADERS.copy()
        h["Range"] = "bytes=0-65535"

        r = session.get(
            last_segment,
            headers=h,
            timeout=15,
            verify=False,
            allow_redirects=True,
        )

        segment_status = r.status_code

        if r.status_code in (200, 206):

            segment_hash = hashlib.sha256(
                r.content[:65536]
            ).hexdigest()

    except Exception as e:

        segment_status = str(e)

    return {
        "ok": (
            segment_hash is not None
        ),
        "status": (
            "OK"
            if segment_hash
            else "SEGMENT NIE DZIAŁA"
        ),
        "media_url": response.url,
        "sequence": sequence,
        "segments": segments,
        "last_segment": last_segment,
        "hash": segment_hash,
        "program_date_time": (
            program_date_time
        ),
        "segment_status": (
            segment_status
        ),
    }


def snapshot(session, cameras):

    result = {}

    for camera in cameras:

        print()
        print(
            "Sprawdzam:",
            camera["name"],
        )

        data = resolve_media_playlist(
            session,
            camera["url"],
        )

        result[
            camera["stream_id"]
        ] = data

        print(
            " Status:",
            data.get("status")
        )

        if data.get("ok"):

            print(
                " Media sequence:",
                data.get("sequence")
            )

            print(
                " Segmentów:",
                len(
                    data.get(
                        "segments",
                        []
                    )
                )
            )

            print(
                " Ostatni segment:"
            )

            print(
                " ",
                data.get(
                    "last_segment"
                )
            )

            print(
                " Hash:",
                data.get("hash")
            )

            if data.get(
                "program_date_time"
            ):

                print(
                    " Program-Date-Time:",
                    data[
                        "program_date_time"
                    ]
                )

    return result


def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    cameras = []

    seen = set()

    for index, line in enumerate(lines):

        match = FORECAST_RE.search(
            line
        )

        if not match:
            continue

        stream_id = match.group(1)

        if stream_id in seen:
            continue

        seen.add(stream_id)

        cameras.append({
            "name": camera_name(
                lines,
                index,
            ),
            "stream_id": stream_id,
            "url": line.strip(),
        })

    print()
    print("#" * 80)
    print(
        "TEST RZECZYWISTEGO LIVE "
        "FORECASTWEATHER.GR"
    )
    print("#" * 80)

    print(
        "Znalezionych kamer:",
        len(cameras)
    )

    session = requests.Session()

    print()
    print("=" * 80)
    print("POMIAR NR 1")
    print("=" * 80)

    first = snapshot(
        session,
        cameras,
    )

    print()
    print(
        f"Czekam {WAIT_SECONDS} sekund..."
    )

    time.sleep(WAIT_SECONDS)

    print()
    print("=" * 80)
    print("POMIAR NR 2")
    print("=" * 80)

    second = snapshot(
        session,
        cameras,
    )

    moving = 0
    frozen = 0
    offline = 0

    print()
    print("#" * 80)
    print("WYNIKI")
    print("#" * 80)

    for camera in cameras:

        sid = camera["stream_id"]

        a = first.get(sid, {})
        b = second.get(sid, {})

        print()
        print(
            "KAMERA:",
            camera["name"]
        )

        if (
            not a.get("ok")
            or not b.get("ok")
        ):

            print(
                ">>> OFFLINE / BŁĄD <<<"
            )

            print(
                "Pomiar 1:",
                a.get("status")
            )

            print(
                "Pomiar 2:",
                b.get("status")
            )

            offline += 1
            continue

        seq_changed = (
            a.get("sequence")
            != b.get("sequence")
        )

        segment_changed = (
            a.get("last_segment")
            != b.get("last_segment")
        )

        hash_changed = (
            a.get("hash")
            != b.get("hash")
        )

        time_changed = (
            a.get("program_date_time")
            != b.get("program_date_time")
        )

        print(
            "Sequence:",
            a.get("sequence"),
            "->",
            b.get("sequence"),
        )

        print(
            "Zmienił się segment:",
            segment_changed
        )

        print(
            "Zmienił się hash:",
            hash_changed
        )

        if (
            a.get("program_date_time")
            or b.get("program_date_time")
        ):

            print(
                "Zmienił się czas HLS:",
                time_changed
            )

        if (
            seq_changed
            or segment_changed
            or hash_changed
            or time_changed
        ):

            print(
                ">>> TRANSMISJA "
                "ODŚWIEŻA SIĘ <<<"
            )

            moving += 1

        else:

            print(
                ">>> UWAGA: "
                "TRANSMISJA STOI <<<"
            )

            frozen += 1

    print()
    print("#" * 80)
    print(
        "PODSUMOWANIE FORECASTWEATHER LIVE"
    )
    print("#" * 80)

    print(
        "Odświeża się:",
        moving
    )

    print(
        "Stoi / stare segmenty:",
        frozen
    )

    print(
        "Offline / błąd:",
        offline
    )

    print("#" * 80)


if __name__ == "__main__":
    main()

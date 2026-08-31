import asyncio
import pathlib
import re
from urllib.parse import urljoin

import requests
from playwright.async_api import async_playwright


PLAYLIST_FILE = pathlib.Path("Kamery-pogodowe.m3u8")

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36"
)

IDOKEP_RE = re.compile(
    r"https?://cam\.idokep\.hu/live/"
    r"([^/\s?#]+)/"
    r"([^\s?#]+\.m3u8)"
    r"(?:\?[^\s]*)?",
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


def headers_for(page_url):

    return {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": page_url,
        "Origin": "https://www.idokep.hu",
    }


def test_segment(
    session,
    url,
    page_url,
):

    try:

        headers = headers_for(page_url)
        headers["Range"] = "bytes=0-1023"

        response = session.get(
            url,
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


def check_hls(
    session,
    url,
    page_url,
    depth=0,
):

    if depth > 3:

        return {
            "ok": False,
            "status": "ZA DUŻO POZIOMÓW",
            "segments": 0,
        }

    try:

        response = session.get(
            url,
            headers=headers_for(page_url),
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

    # ----------------------------------------
    # MASTER PLAYLIST
    # ----------------------------------------

    if any(
        line.startswith("#EXT-X-STREAM-INF")
        for line in playlist_lines
    ):

        children = []

        for i, line in enumerate(
            playlist_lines
        ):

            if not line.startswith(
                "#EXT-X-STREAM-INF"
            ):
                continue

            if i + 1 >= len(
                playlist_lines
            ):
                continue

            child = playlist_lines[i + 1]

            if child.startswith("#"):
                continue

            children.append(
                urljoin(
                    response.url,
                    child,
                )
            )

        for child in children:

            result = check_hls(
                session,
                child,
                page_url,
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

    # ----------------------------------------
    # MEDIA PLAYLIST
    # ----------------------------------------

    extinf_count = sum(
        1
        for line in playlist_lines
        if line.startswith("#EXTINF:")
    )

    segments = []

    for line in playlist_lines:

        if line.startswith("#"):
            continue

        # Pomijamy ewentualne dalsze playlisty.
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

    # Sprawdzamy maksymalnie
    # trzy ostatnie segmenty.
    #
    # Przy LIVE ostatnie są zwykle
    # najbardziej aktualne.

    for segment in segments[-3:]:

        if test_segment(
            session,
            segment,
            page_url,
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


async def capture_from_page(
    browser,
    slug,
):

    page_url = (
        "https://www.idokep.hu/"
        f"webkamera/{slug}"
    )

    context = await browser.new_context(
        user_agent=USER_AGENT,
        locale="hu-HU",
        viewport={
            "width": 1280,
            "height": 800,
        },
    )

    page = await context.new_page()

    found = []

    def inspect_request(request):

        url = request.url

        if ".m3u8" not in url.lower():
            return

        if "idokep.hu" not in url.lower():
            return

        if url not in found:

            found.append(url)

            print(
                "  PRZECHWYCONO:"
            )

            print(
                "   ",
                url
            )

    page.on(
        "request",
        inspect_request,
    )

    try:

        await page.goto(
            page_url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        await page.wait_for_timeout(
            3000
        )

        # Próba uruchomienia video,
        # jeżeli autoplay nie wystartował.

        try:

            await page.evaluate(
                """
                () => {
                    const videos =
                        document.querySelectorAll(
                            'video'
                        );

                    for (const video of videos) {
                        video.muted = true;

                        video.play()
                            .catch(() => {});
                    }
                }
                """
            )

        except Exception:
            pass

        # Dajemy playerowi czas.
        await page.wait_for_timeout(
            10000
        )

    except Exception as e:

        print(
            "  BŁĄD strony:",
            e
        )

    finally:

        await context.close()

    return found


async def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    cameras = {}

    for index, line in enumerate(lines):

        match = IDOKEP_RE.search(
            line
        )

        if not match:
            continue

        slug = match.group(1)

        if slug not in cameras:

            cameras[slug] = {
                "name": get_camera_name(
                    lines,
                    index,
                ),
                "slug": slug,
                "current_url": line.strip(),
            }

    print()
    print("#" * 80)
    print("TEST IDŐKÉP")
    print("#" * 80)

    print(
        "Znalezionych kamer Időkép:",
        len(cameras)
    )

    session = requests.Session()

    index_ok = 0
    s_orig_ok = 0
    other_ok = 0
    offline = 0

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy="
                "no-user-gesture-required"
            ],
        )

        for number, camera in enumerate(
            cameras.values(),
            start=1,
        ):

            slug = camera["slug"]

            page_url = (
                "https://www.idokep.hu/"
                f"webkamera/{slug}"
            )

            index_url = (
                "https://cam.idokep.hu/"
                f"live/{slug}/index.m3u8"
            )

            s_orig_url = (
                "https://cam.idokep.hu/"
                f"live/{slug}/s_orig.m3u8"
            )

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
                slug
            )

            print(
                "STRONA:"
            )

            print(page_url)

            print()
            print(
                "OBECNY URL:"
            )

            print(
                camera["current_url"]
            )

            current_result = check_hls(
                session,
                camera["current_url"],
                page_url,
            )

            print(
                "OBECNY:",
                current_result["status"],
                "| segmenty:",
                current_result["segments"],
            )

            print()
            print(
                "INDEX:"
            )

            print(index_url)

            index_result = check_hls(
                session,
                index_url,
                page_url,
            )

            print(
                index_result["status"],
                "| segmenty:",
                index_result["segments"],
            )

            print()
            print(
                "S_ORIG:"
            )

            print(s_orig_url)

            s_orig_result = check_hls(
                session,
                s_orig_url,
                page_url,
            )

            print(
                s_orig_result["status"],
                "| segmenty:",
                s_orig_result["segments"],
            )

            print()
            print(
                "PRZECHWYTUJĘ ZE STRONY..."
            )

            captured = await capture_from_page(
                browser,
                slug,
            )

            captured_results = []

            for url in captured:

                result = check_hls(
                    session,
                    url,
                    page_url,
                )

                captured_results.append(
                    (url, result)
                )

                print()
                print(
                    "CAPTURED:"
                )

                print(url)

                print(
                    result["status"],
                    "| segmenty:",
                    result["segments"],
                )

            working_captured = [
                url
                for url, result
                in captured_results
                if result["ok"]
            ]

            print()
            print("-" * 80)

            if index_result["ok"]:

                print(
                    "WYNIK: INDEX.M3U8 DZIAŁA"
                )

                index_ok += 1

            elif s_orig_result["ok"]:

                print(
                    "WYNIK: INDEX NIE DZIAŁA, "
                    "ALE S_ORIG DZIAŁA"
                )

                s_orig_ok += 1

            elif working_captured:

                print(
                    "WYNIK: INDEX I S_ORIG "
                    "NIE DZIAŁAJĄ,"
                )

                print(
                    "ALE STRONA UŻYWA "
                    "INNEGO DZIAŁAJĄCEGO HLS:"
                )

                for url in working_captured:
                    print(
                        " ",
                        url
                    )

                other_ok += 1

            else:

                print(
                    "WYNIK: BRAK "
                    "DZIAŁAJĄCEGO HLS"
                )

                offline += 1

        await browser.close()

    print()
    print("#" * 80)
    print("PODSUMOWANIE IDŐKÉP")
    print("#" * 80)

    print(
        "index.m3u8 działa:",
        index_ok
    )

    print(
        "index nie działa, "
        "ale s_orig działa:",
        s_orig_ok
    )

    print(
        "działa tylko inny HLS "
        "przechwycony ze strony:",
        other_ok
    )

    print(
        "brak działającego HLS:",
        offline
    )

    print("#" * 80)


asyncio.run(main())

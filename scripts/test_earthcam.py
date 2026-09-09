import asyncio
import pathlib
import re
from datetime import datetime
from urllib.parse import (
    urljoin,
    urlparse,
    urlunparse,
    parse_qs,
)

import requests
from playwright.async_api import async_playwright


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


# --------------------------------------------------
# RĘCZNE ADRESY DO TESTU
# --------------------------------------------------
#
# Ten URL podałeś wcześniej.
# Jeśli token już wygasł, to też jest cenna informacja.
#
MANUAL_URLS = [
    (
        "EarthCam 7132",
        "https://videos-3.earthcam.com/"
        "fecnetwork/7132.flv/playlist.m3u8"
        "?t=suFkKMnfT%2B7NQuL5FdDHhFVCTAUovyKsltg7eHatVdD1M0SyMx6GVct0inHBTqTL"
        "&td=202609090738"
    ),
]


OFFICIAL_PAGES = {
    "7132.flv":
        "https://www.earthcam.com/"
        "cams/dc/washingtonmonument/"
        "?cam=wamo",
}


EARTHCAM_RE = re.compile(
    r"https?://"
    r"(?:(?:videos-\d+)|(?:video\d+))"
    r"\.earthcam\.com/"
    r"fecnetwork/"
    r"([^/\s?#]+\.flv)"
    r"/playlist\.m3u8"
    r"(?:\?[^\s]*)?",
    re.IGNORECASE,
)


def get_name(lines, index):

    if index <= 0:
        return "(nieznana kamera)"

    previous = lines[index - 1]

    if (
        previous.startswith("#EXTINF")
        and "," in previous
    ):
        return previous.split(",", 1)[1].strip()

    return "(nieznana kamera)"


def strip_query(url):

    parsed = urlparse(url)

    return urlunparse(
        parsed._replace(
            query=""
        )
    )


def get_stream_id(url):

    match = re.search(
        r"/fecnetwork/"
        r"([^/]+\.flv)"
        r"/playlist\.m3u8",
        url,
        re.IGNORECASE,
    )

    if match:
        return match.group(1)

    return None


def print_token_info(url):

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    token = query.get(
        "t",
        [None]
    )[0]

    td = query.get(
        "td",
        [None]
    )[0]

    print(
        "  Parametr t:",
        "TAK" if token else "NIE"
    )

    if token:
        print(
            "  Długość tokenu:",
            len(token)
        )

    print(
        "  Parametr td:",
        td or "BRAK"
    )

    if (
        td
        and re.fullmatch(
            r"\d{12}",
            td
        )
    ):

        try:

            dt = datetime.strptime(
                td,
                "%Y%m%d%H%M"
            )

            print(
                "  td wygląda jak data/czas:",
                dt.strftime(
                    "%Y-%m-%d %H:%M"
                )
            )

        except Exception:
            pass


def headers(referer):

    return {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": referer,
        "Origin":
            "https://www.earthcam.com",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def inherit_query(parent_url, child_url):

    parent = urlparse(parent_url)
    child = urlparse(child_url)

    if child.query:
        return child_url

    if not parent.query:
        return child_url

    return urlunparse(
        child._replace(
            query=parent.query
        )
    )


def test_segment(
    session,
    url,
    referer,
):

    try:

        h = headers(referer)
        h["Range"] = "bytes=0-8191"

        response = session.get(
            url,
            headers=h,
            timeout=12,
            allow_redirects=True,
            stream=True,
        )

        return (
            response.status_code
            in (200, 206)
        )

    except Exception:
        return False


def check_hls(
    session,
    url,
    referer,
    depth=0,
):

    if depth > 4:
        return {
            "ok": False,
            "status":
                "ZA DUŻO POZIOMÓW",
            "segments": 0,
        }

    try:

        response = session.get(
            url,
            headers=headers(referer),
            timeout=15,
            allow_redirects=True,
        )

    except Exception as e:

        return {
            "ok": False,
            "status":
                f"ERROR: {type(e).__name__}",
            "segments": 0,
        }

    if response.status_code != 200:

        return {
            "ok": False,
            "status":
                f"HTTP {response.status_code}",
            "segments": 0,
        }

    text = response.text

    if "#EXTM3U" not in text:

        return {
            "ok": False,
            "status": "BRAK #EXTM3U",
            "segments": 0,
        }

    lines = [
        x.strip()
        for x in text.splitlines()
        if x.strip()
    ]

    # ------------------------------------------
    # MASTER PLAYLIST
    # ------------------------------------------

    if any(
        x.startswith(
            "#EXT-X-STREAM-INF"
        )
        for x in lines
    ):

        candidates = []

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

            absolute = urljoin(
                response.url,
                child
            )

            candidates.append(
                absolute
            )

            inherited = inherit_query(
                response.url,
                absolute
            )

            if inherited not in candidates:
                candidates.append(
                    inherited
                )

        for candidate in candidates:

            result = check_hls(
                session,
                candidate,
                referer,
                depth + 1,
            )

            if result["ok"]:
                return result

        return {
            "ok": False,
            "status":
                "MASTER BEZ "
                "DZIAŁAJĄCEGO WARIANTU",
            "segments": 0,
        }

    # ------------------------------------------
    # MEDIA PLAYLIST
    # ------------------------------------------

    extinf = sum(
        1
        for x in lines
        if x.startswith("#EXTINF:")
    )

    segments = []

    for line in lines:

        if line.startswith("#"):
            continue

        if ".m3u8" in line.lower():
            continue

        segment = urljoin(
            response.url,
            line
        )

        segments.append(segment)

    if not segments:

        return {
            "ok": False,
            "status": "BRAK SEGMENTÓW",
            "segments": 0,
        }

    for segment in segments[-3:]:

        variants = [
            segment,
            inherit_query(
                response.url,
                segment
            ),
        ]

        checked = set()

        for variant in variants:

            if variant in checked:
                continue

            checked.add(variant)

            if test_segment(
                session,
                variant,
                referer,
            ):

                return {
                    "ok": True,
                    "status": "OK",
                    "segments": extinf,
                }

    return {
        "ok": False,
        "status":
            "PLAYLISTA JEST, "
            "ALE SEGMENTY NIE DZIAŁAJĄ",
        "segments": extinf,
    }


async def capture_fresh(
    browser,
    stream,
    official_page,
):

    print()
    print(
        "Otwieram oficjalną stronę:"
    )
    print(
        official_page
    )

    context = await browser.new_context(
        user_agent=USER_AGENT,
        locale="en-US",
        viewport={
            "width": 1280,
            "height": 800,
        },
    )

    page = await context.new_page()

    found = []

    def inspect(request):

        url = request.url
        lower = url.lower()

        if ".m3u8" not in lower:
            return

        if "earthcam.com" not in lower:
            return

        if "/fecnetwork/" not in lower:
            return

        if url not in found:

            found.append(url)

            print()
            print(
                "PRZECHWYCONO:"
            )
            print(url)

    page.on(
        "request",
        inspect
    )

    try:

        await page.goto(
            official_page,
            wait_until=
                "domcontentloaded",
            timeout=60000,
        )

        await page.wait_for_timeout(
            4000
        )

        try:

            await page.evaluate(
                """
                () => {
                    const videos =
                        document.querySelectorAll(
                            'video'
                        );

                    for (
                        const video
                        of videos
                    ) {
                        video.muted = true;

                        video.play()
                            .catch(() => {});
                    }
                }
                """
            )

        except Exception:
            pass

        # Klikamy możliwe Play

        try:

            elements = page.locator(
                "button, [role='button']"
            )

            count = await elements.count()

            for i in range(
                min(count, 30)
            ):

                el = elements.nth(i)

                try:

                    text = (
                        await el.inner_text()
                    ).lower()

                    aria = (
                        await el.get_attribute(
                            "aria-label"
                        )
                        or ""
                    ).lower()

                    title = (
                        await el.get_attribute(
                            "title"
                        )
                        or ""
                    ).lower()

                    if (
                        "play" in text
                        or "play" in aria
                        or "play" in title
                    ):

                        await el.click(
                            timeout=1500
                        )

                except Exception:
                    pass

        except Exception:
            pass

        await page.wait_for_timeout(
            15000
        )

    except Exception as e:

        print(
            "BŁĄD STRONY:",
            type(e).__name__,
            str(e),
        )

    finally:

        await context.close()

    return found


def load_cameras():

    cameras = []
    seen = set()

    if PLAYLIST_FILE.exists():

        text = PLAYLIST_FILE.read_text(
            encoding="utf-8"
        )

        lines = text.splitlines()

        for index, line in enumerate(lines):

            match = EARTHCAM_RE.search(
                line
            )

            if not match:
                continue

            url = match.group(0)

            parsed = urlparse(url)
            params = parse_qs(
                parsed.query
            )

            # Tutaj interesują nas tylko
            # tokenizowane EarthCam.
            if (
                "t" not in params
                and "td" not in params
            ):
                continue

            if url in seen:
                continue

            seen.add(url)

            cameras.append({
                "name":
                    get_name(
                        lines,
                        index
                    ),
                "url": url,
                "source": "M3U",
            })

    # Dodajemy ręczne przykłady,
    # jeżeli jeszcze nie występują w M3U.

    for name, url in MANUAL_URLS:

        if url in seen:
            continue

        seen.add(url)

        cameras.append({
            "name": name,
            "url": url,
            "source": "RĘCZNY TEST",
        })

    return cameras


async def main():

    cameras = load_cameras()

    print()
    print("#" * 78)
    print(
        "TEST TOKENIZOWANYCH EARTHCAM"
    )
    print("#" * 78)

    print(
        "Znalezionych/testowanych:",
        len(cameras)
    )

    if not cameras:
        return

    session = requests.Session()

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy="
                "no-user-gesture-required"
            ],
        )

        for number, camera in enumerate(
            cameras,
            start=1,
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
                "ŹRÓDŁO:",
                camera["source"]
            )

            print()
            print(
                "OBECNY TOKENIZOWANY URL:"
            )

            print(
                camera["url"]
            )

            print()

            print_token_info(
                camera["url"]
            )

            stream = get_stream_id(
                camera["url"]
            )

            print(
                "STREAM ID:",
                stream
            )

            official_page = (
                OFFICIAL_PAGES.get(
                    stream
                )
            )

            referer = (
                official_page
                or
                "https://www.earthcam.com/"
            )

            # ----------------------------------
            # TEST TOKENU
            # ----------------------------------

            print()
            print(
                "TEST Z TOKENEM:"
            )

            token_result = check_hls(
                session,
                camera["url"],
                referer,
            )

            print(
                token_result["status"],
                "| segmenty:",
                token_result["segments"],
            )

            # ----------------------------------
            # TEST BEZ TOKENU
            # ----------------------------------

            plain_url = strip_query(
                camera["url"]
            )

            print()
            print(
                "TEST BEZ TOKENU:"
            )

            print(
                plain_url
            )

            plain_result = check_hls(
                session,
                plain_url,
                referer,
            )

            print(
                plain_result["status"],
                "| segmenty:",
                plain_result["segments"],
            )

            if (
                token_result["ok"]
                and not plain_result["ok"]
            ):

                print()
                print(
                    ">>> TOKEN JEST "
                    "WYMAGANY <<<"
                )

            elif (
                plain_result["ok"]
            ):

                print()
                print(
                    ">>> TOKEN NIE JEST "
                    "OBECNIE POTRZEBNY <<<"
                )

            # ----------------------------------
            # PRZECHWYCENIE ŚWIEŻEGO
            # ----------------------------------

            if not official_page:

                print()
                print(
                    "Brak przypisanej "
                    "oficjalnej strony."
                )

                print(
                    "Nie mogę automatycznie "
                    "pobrać nowego tokenu."
                )

                continue

            captured = await capture_fresh(
                browser,
                stream,
                official_page,
            )

            if not captured:

                print()
                print(
                    ">>> NIE PRZECHWYCONO "
                    "ŚWIEŻEGO HLS <<<"
                )

                continue

            working = []

            for candidate in captured:

                print()
                print("-" * 78)

                print(
                    "KANDYDAT:"
                )

                print(candidate)

                print_token_info(
                    candidate
                )

                result = check_hls(
                    session,
                    candidate,
                    official_page,
                )

                print(
                    "TEST:",
                    result["status"],
                    "| segmenty:",
                    result["segments"],
                )

                if result["ok"]:
                    working.append(
                        candidate
                    )

            if not working:

                print()
                print(
                    ">>> ŻADEN "
                    "PRZECHWYCONY HLS "
                    "NIE DZIAŁA <<<"
                )

                continue

            print()
            print("#" * 78)

            print(
                "DZIAŁAJĄCE ŚWIEŻE HLS:"
            )

            for candidate in working:

                print()
                print(candidate)

            print()
            print(
                "SKOPIUJ PIERWSZY ADRES "
                "I SPRAWDŹ GO W "
                "M3U-IP.TV PO "
                "ZAKOŃCZENIU ACTION."
            )

            print("#" * 78)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import pathlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

PLAYLIST_FILE = pathlib.Path(
    "Kamery-pogodowe.m3u8"
)

BASE = "https://www.forecastweather.gr"
CAMERAS_HOME = (
    "https://www.forecastweather.gr/kameres.html"
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
}

# np.
# https://streaming.forecastweather.gr:8090/
# live/voloskeraiaote/playlist.m3u8

FORECAST_RE = re.compile(
    r"https?://streaming\.forecastweather\.gr"
    r":8090/live/"
    r"([^/?#\s]+)/playlist\.m3u8"
    r"(?:\?[^\s]*)?",
    re.IGNORECASE,
)

STREAM_IN_HTML_RE = re.compile(
    r"https?://streaming\.forecastweather\.gr"
    r":8090/live/"
    r"([^/'\"?<>\s]+)/playlist\.m3u8",
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


def get_text(session, url, timeout=15):

    try:

        response = session.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True,
            verify=False,
        )

        if response.status_code != 200:
            return None

        return response.text

    except Exception:
        return None


def test_segment(session, url, referer):

    try:

        headers = HEADERS.copy()
        headers["Referer"] = referer
        headers["Range"] = "bytes=0-1023"

        response = session.get(
            url,
            headers=headers,
            timeout=12,
            allow_redirects=True,
            verify=False,
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
    referer=BASE,
    depth=0,
):

    if depth > 3:

        return {
            "ok": False,
            "status": "ZA DUŻO POZIOMÓW",
            "segments": 0,
        }

    try:

        headers = HEADERS.copy()
        headers["Referer"] = referer

        response = session.get(
            url,
            headers=headers,
            timeout=15,
            allow_redirects=True,
            verify=False,
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

    plines = [
        x.strip()
        for x in text.splitlines()
        if x.strip()
    ]

    # MASTER

    if any(
        x.startswith("#EXT-X-STREAM-INF")
        for x in plines
    ):

        children = []

        for i, line in enumerate(plines):

            if not line.startswith(
                "#EXT-X-STREAM-INF"
            ):
                continue

            if i + 1 >= len(plines):
                continue

            child = plines[i + 1]

            if child.startswith("#"):
                continue

            children.append(
                urljoin(
                    response.url,
                    child
                )
            )

        for child in children:

            result = check_hls(
                session,
                child,
                referer,
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

    # MEDIA

    extinf_count = sum(
        1
        for line in plines
        if line.startswith("#EXTINF:")
    )

    segments = []

    for line in plines:

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

    if (
        not segments
        or extinf_count == 0
    ):

        return {
            "ok": False,
            "status": "M3U8 BEZ SEGMENTÓW",
            "segments": 0,
        }

    # sprawdzamy najnowsze segmenty

    for segment in segments[-3:]:

        if test_segment(
            session,
            segment,
            referer,
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


def forecast_page_link(url):

    try:
        parsed = urlparse(url)

        if (
            parsed.netloc
            != "www.forecastweather.gr"
        ):
            return False

        path = parsed.path.lower()

        if "/kameres/" not in path:
            return False

        if not path.endswith(".html"):
            return False

        return True

    except Exception:
        return False


def extract_links(html, base_url):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    urls = set()

    for anchor in soup.find_all(
        "a",
        href=True
    ):

        url = urljoin(
            base_url,
            anchor["href"]
        )

        if forecast_page_link(url):
            urls.add(url)

    return urls


def discover_camera_pages(session):

    print()
    print(
        "Pobieram katalog kamer "
        "ForecastWeather..."
    )

    home_html = get_text(
        session,
        CAMERAS_HOME
    )

    if not home_html:

        print(
            "Nie udało się pobrać "
            "katalogu kamer."
        )

        return []

    first_level = extract_links(
        home_html,
        CAMERAS_HOME
    )

    print(
        "Linków pierwszego poziomu:",
        len(first_level)
    )

    all_pages = set(first_level)

    # Przeglądamy strony regionów,
    # aby znaleźć strony konkretnych kamer.

    with ThreadPoolExecutor(
        max_workers=10
    ) as executor:

        futures = {
            executor.submit(
                get_text,
                session,
                url,
            ): url
            for url in first_level
        }

        for future in as_completed(futures):

            url = futures[future]

            try:
                html = future.result()
            except Exception:
                continue

            if not html:
                continue

            all_pages.update(
                extract_links(
                    html,
                    url
                )
            )

    print(
        "Łącznie znalezionych "
        "stron kamer/regionów:",
        len(all_pages)
    )

    return sorted(all_pages)


def map_streams_to_pages(
    session,
    pages,
    wanted_streams,
):

    mapping = {}

    wanted = set(wanted_streams)

    print()
    print(
        "Szukam strumieni na "
        "oficjalnych stronach..."
    )

    def inspect_page(url):

        html = get_text(
            session,
            url,
            timeout=15,
        )

        if not html:
            return url, []

        found = STREAM_IN_HTML_RE.findall(
            html
        )

        return url, found

    with ThreadPoolExecutor(
        max_workers=12
    ) as executor:

        futures = [
            executor.submit(
                inspect_page,
                url
            )
            for url in pages
        ]

        for future in as_completed(futures):

            try:
                url, found = future.result()
            except Exception:
                continue

            for stream_id in found:

                if stream_id not in wanted:
                    continue

                if stream_id not in mapping:

                    mapping[stream_id] = url

                    print(
                        "  MAPA:",
                        stream_id
                    )

                    print(
                        "   ",
                        url
                    )

    return mapping


async def capture_from_page(
    browser,
    page_url,
):

    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={
            "width": 1280,
            "height": 800,
        },
    )

    page = await context.new_page()

    found = []

    def inspect_request(request):

        url = request.url

        lower = url.lower()

        if ".m3u8" not in lower:
            return

        if (
            "forecastweather.gr"
            not in lower
        ):
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
        inspect_request
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

        try:

            await page.evaluate(
                """
                () => {
                    const videos =
                        document.querySelectorAll(
                            'video'
                        );

                    for (const v of videos) {
                        v.muted = true;
                        v.play().catch(() => {});
                    }
                }
                """
            )

        except Exception:
            pass

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

    cameras = []

    seen = set()

    for index, line in enumerate(lines):

        match = FORECAST_RE.search(
            line
        )

        if not match:
            continue

        stream_id = match.group(1)

        if (
            stream_id,
            line.strip()
        ) in seen:
            continue

        seen.add(
            (
                stream_id,
                line.strip()
            )
        )

        cameras.append({
            "name": camera_name(
                lines,
                index
            ),
            "stream_id": stream_id,
            "url": line.strip(),
        })

    print()
    print("#" * 80)
    print("TEST FORECASTWEATHER.GR")
    print("#" * 80)

    print(
        "Znalezionych kamer:",
        len(cameras)
    )

    session = requests.Session()

    # Najpierw testujemy obecne HLS.

    for camera in cameras:

        camera["current_result"] = (
            check_hls(
                session,
                camera["url"],
            )
        )

    # Szukamy odpowiadających stron
    # w oficjalnym katalogu.

    pages = discover_camera_pages(
        session
    )

    mapping = map_streams_to_pages(
        session,
        pages,
        [
            c["stream_id"]
            for c in cameras
        ],
    )

    same_hls = 0
    other_hls = 0
    direct_only = 0
    offline = 0
    no_page = 0

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
            print("=" * 80)

            print(
                f"[{number}/{len(cameras)}]"
            )

            print(
                "KAMERA:",
                camera["name"]
            )

            print(
                "STREAM ID:",
                camera["stream_id"]
            )

            print(
                "OBECNY URL:"
            )

            print(
                camera["url"]
            )

            result = camera[
                "current_result"
            ]

            print(
                "OBECNY HLS:",
                result["status"],
                "| segmenty:",
                result["segments"],
            )

            source_page = mapping.get(
                camera["stream_id"]
            )

            if not source_page:

                print()
                print(
                    "Nie znaleziono "
                    "oficjalnej strony kamery."
                )

                if result["ok"]:
                    direct_only += 1
                else:
                    no_page += 1

                continue

            print()
            print(
                "OFICJALNA STRONA:"
            )

            print(source_page)

            print()
            print(
                "Przechwytuję player..."
            )

            captured = await capture_from_page(
                browser,
                source_page,
            )

            working = []

            for captured_url in captured:

                captured_result = check_hls(
                    session,
                    captured_url,
                    source_page,
                )

                print()
                print(
                    "CAPTURED:"
                )

                print(captured_url)

                print(
                    captured_result["status"],
                    "| segmenty:",
                    captured_result[
                        "segments"
                    ],
                )

                if captured_result["ok"]:

                    working.append(
                        captured_url
                    )

            print()
            print("-" * 80)

            if working:

                normalized_current = (
                    camera["url"]
                    .split("?", 1)[0]
                )

                same = any(
                    url.split("?", 1)[0]
                    == normalized_current
                    for url in working
                )

                if same:

                    print(
                        "WYNIK: STRONA UŻYWA "
                        "TEGO SAMEGO HLS"
                    )

                    same_hls += 1

                else:

                    print(
                        "WYNIK: STRONA UŻYWA "
                        "INNEGO DZIAŁAJĄCEGO HLS"
                    )

                    for url in working:
                        print(
                            " ",
                            url
                        )

                    other_hls += 1

            else:

                if result["ok"]:

                    print(
                        "WYNIK: BEZPOŚREDNI HLS "
                        "DZIAŁA, ALE PLAYER "
                        "NIC NIE PRZECHWYCIŁ"
                    )

                    direct_only += 1

                else:

                    print(
                        "WYNIK: KAMERA "
                        "PRAWDOPODOBNIE OFFLINE"
                    )

                    offline += 1

        await browser.close()

    print()
    print("#" * 80)
    print(
        "PODSUMOWANIE FORECASTWEATHER"
    )
    print("#" * 80)

    print(
        "Strona używa tego samego HLS:",
        same_hls
    )

    print(
        "Strona używa innego HLS:",
        other_hls
    )

    print(
        "Działa tylko bezpośredni HLS:",
        direct_only
    )

    print(
        "Prawdopodobnie offline:",
        offline
    )

    print(
        "Brak dopasowanej strony "
        "i HLS nie działa:",
        no_page
    )

    print("#" * 80)


asyncio.run(main())

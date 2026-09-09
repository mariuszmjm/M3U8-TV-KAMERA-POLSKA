import asyncio
import pathlib
import re
from urllib.parse import (
    urljoin,
    urlparse,
    urlunparse,
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

# Obsługujemy np.:
#
# https://videos-3.earthcam.com/
# fecnetwork/7132.flv/playlist.m3u8?t=...&td=...
#
# oraz starsze:
#
# https://video3.earthcam.com/...
#
EARTHCAM_RE = re.compile(
    r"https?://"
    r"(?P<host>"
    r"(?:videos-\d+|video\d+)"
    r"\.earthcam\.com"
    r")"
    r"/fecnetwork/"
    r"(?P<stream>"
    r"[^/\s?#]+\.flv"
    r")"
    r"/playlist\.m3u8"
    r"(?:\?[^\s]*)?",
    re.IGNORECASE,
)


# Dla 7132 znamy oficjalną stronę.
# Kolejne można później dopisać,
# jeżeli będą potrzebne.
OFFICIAL_PAGES = {
    "7132.flv":
        "https://www.earthcam.com/"
        "cams/dc/washingtonmonument/"
        "?cam=wamo",

    "15041.flv":
        "https://www.earthcam.com/"
        "cams/hungary/budapest/"
        "?cam=hotelvictoria",

    "4369.flv":
        "https://www.earthcam.com/"
        "cams/jamaica/negril/"
        "?cam=rickscafe",
}


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


def browser_headers(referer):

    return {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": referer,
        "Origin": "https://www.earthcam.com",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def carry_query(parent_url, child_url):

    """
    Jeżeli EarthCam wymaga tokenu również
    w podrzędnym M3U8 lub segmencie,
    próbujemy zachować query rodzica.
    """

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

    candidates = [url]

    # Spróbujemy również wariantu
    # z tokenem odziedziczonym z playlisty.
    # Duplikaty zostaną pominięte później.

    for candidate in list(candidates):

        try:

            headers = browser_headers(
                referer
            )

            headers["Range"] = (
                "bytes=0-4095"
            )

            response = session.get(
                candidate,
                headers=headers,
                timeout=12,
                allow_redirects=True,
                stream=True,
            )

            if response.status_code in (
                200,
                206,
            ):
                return True

        except Exception:
            pass

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
            headers=browser_headers(
                referer
            ),
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
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # ----------------------------------
    # MASTER PLAYLIST
    # ----------------------------------

    if any(
        line.startswith(
            "#EXT-X-STREAM-INF"
        )
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

            child_url = urljoin(
                response.url,
                child,
            )

            children.append(
                child_url
            )

            with_query = carry_query(
                response.url,
                child_url,
            )

            if (
                with_query
                not in children
            ):
                children.append(
                    with_query
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
            "status":
                "MASTER BEZ "
                "DZIAŁAJĄCEGO WARIANTU",
            "segments": 0,
        }

    # ----------------------------------
    # MEDIA PLAYLIST
    # ----------------------------------

    extinf_count = sum(
        1
        for line in lines
        if line.startswith("#EXTINF:")
    )

    segments = []

    for line in lines:

        if line.startswith("#"):
            continue

        if ".m3u8" in line.lower():
            continue

        segment = urljoin(
            response.url,
            line,
        )

        segments.append(segment)

    if (
        extinf_count == 0
        or not segments
    ):

        return {
            "ok": False,
            "status":
                "M3U8 BEZ SEGMENTÓW",
            "segments": 0,
        }

    # Najnowsze segmenty LIVE.

    for segment in segments[-3:]:

        candidates = [
            segment,
            carry_query(
                response.url,
                segment
            ),
        ]

        checked = set()

        for candidate in candidates:

            if candidate in checked:
                continue

            checked.add(candidate)

            if test_segment(
                session,
                candidate,
                referer,
            ):

                return {
                    "ok": True,
                    "status": "OK",
                    "segments":
                        extinf_count,
                }

    return {
        "ok": False,
        "status":
            "PLAYLISTA JEST, "
            "ALE SEGMENTY NIE DZIAŁAJĄ",
        "segments": extinf_count,
    }


def player_pages(stream):

    pages = []

    # Jeśli znamy oficjalną stronę,
    # próbujemy jej jako pierwszej.

    if stream in OFFICIAL_PAGES:

        pages.append(
            OFFICIAL_PAGES[stream]
        )

    # EarthCam używa również własnego
    # playera do osadzania strumienia.
    #
    # To jest bardzo przydatne,
    # ponieważ potrzebujemy tylko
    # nazwy strumienia, np. 7132.flv.

    container = (
        "https://www.earthcam.com/"
        "cams/includes/twittercards/"
        "container.php"
        f"?name={stream}"
        "&w=728"
        "&h=410"
    )

    if container not in pages:
        pages.append(container)

    return pages


async def capture_hls(
    browser,
    stream,
):

   
    for source_page in player_pages(
        stream
    ):

        print()
        print(
            "  Otwieram:"
        )

        print(
            " ",
            source_page
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

        def inspect_request(request):

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
                source_page,
                wait_until=
                    "domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(
                4000
            )

            # Próbujemy wystartować video,
            # jeżeli autoplay jest wyłączony.

            try:

                await page.evaluate(
                    """
                    () => {
                        const videos =
                            document
                            .querySelectorAll(
                                'video'
                            );

                        for (
                            const video
                            of videos
                        ) {
                            video.muted = true;

                            video.play()
                                .catch(
                                    () => {}
                                );
                        }
                    }
                    """
                )

            except Exception:
                pass

            # Próba kliknięcia przycisku
            # Play, jeśli taki istnieje.

            try:

                buttons = page.locator(
                    "button"
                )

                count = await buttons.count()

                for i in range(
                    min(count, 20)
                ):

                    button = (
                        buttons.nth(i)
                    )

                    try:

                        text = (
                            await button
                            .inner_text()
                        ).lower()

                        aria = (
                            await button
                            .get_attribute(
                                "aria-label"
                            )
                            or ""
                        ).lower()

                        if (
                            "play" in text
                            or "play" in aria
                        ):

                            await button.click(
                                timeout=2000
                            )

                    except Exception:
                        pass

            except Exception:
                pass

            await page.wait_for_timeout(
                12000
            )

        except Exception as e:

            print(
                "  BŁĄD strony:",
                type(e).__name__,
            )

        finally:

            await context.close()

        if found:

            # Preferujemy dokładne
            # playlist.m3u8 z tokenem.

            tokenized = [
                url
                for url in found
                if (
                    "playlist.m3u8?"
                    in url.lower()
                )
            ]

            candidates = (
                tokenized
                + [
                    url
                    for url in found
                    if url not in tokenized
                ]
            )

            return (
                candidates,
                source_page,
            )

    return [], None


async def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    cameras = []

    seen = set()

    for index, line in enumerate(lines):

        match = EARTHCAM_RE.search(
            line
        )

        if not match:
            continue

        url = match.group(0)
        stream = match.group("stream")
        host = match.group("host")

        key = (
            stream,
            url,
        )

        if key in seen:
            continue

        seen.add(key)

        cameras.append({
            "name":
                get_camera_name(
                    lines,
                    index
                ),
            "url": url,
            "stream": stream,
            "host": host,
        })

    print()
    print("#" * 78)
    print("TEST EARTHCAM")
    print("#" * 78)

    print(
        "Znalezionych kamer EarthCam:",
        len(cameras)
    )

    session = requests.Session()

    current_ok = 0
    fresh_ok = 0
    fresh_failed = 0
    no_capture = 0

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
                "STREAM:",
                camera["stream"]
            )

            print(
                "OBECNY URL:"
            )

            print(
                camera["url"]
            )

            parsed = urlparse(
                camera["url"]
            )

            print(
                "TOKEN W URL:",
                (
                    "TAK"
                    if parsed.query
                    else "NIE"
                )
            )

            # Referer dla 7132 = oficjalna strona.
            # Dla innych użyjemy playera.

            pages = player_pages(
                camera["stream"]
            )

            referer = pages[0]

            result = check_hls(
                session,
                camera["url"],
                referer,
            )

            print()
            print(
                "OBECNY HLS:",
                result["status"],
                "| segmenty:",
                result["segments"],
            )

            if result["ok"]:
                current_ok += 1

            # Jeżeli URL jest tokenizowany
            # albo nie działa,
            # próbujemy uzyskać świeży.

            if (
                parsed.query
                or not result["ok"]
            ):

                print()
                print(
                    ">>> PRÓBUJĘ UZYSKAĆ "
                    "ŚWIEŻY HLS <<<"
                )

                (
                    captured,
                    source_page,
                ) = await capture_hls(
                    browser,
                    camera["stream"],
                )

                if not captured:

                    print()
                    print(
                        "NIE PRZECHWYCONO "
                        "NOWEGO HLS."
                    )

                    no_capture += 1
                    continue

                working = None

                for candidate in captured:

                    print()
                    print(
                        "TEST NOWEGO:"
                    )

                    print(candidate)

                    fresh_result = (
                        check_hls(
                            session,
                            candidate,
                            source_page,
                        )
                    )

                    print(
                        fresh_result[
                            "status"
                        ],
                        "| segmenty:",
                        fresh_result[
                            "segments"
                        ],
                    )

                    if fresh_result["ok"]:

                        working = candidate
                        break

                if working:

                    fresh_ok += 1

                    print()
                    print(
                        ">>> ŚWIEŻY HLS "
                        "DZIAŁA <<<"
                    )

                    print()
                    print(
                        "URL DO TESTU "
                        "W M3U-IP.TV:"
                    )

                    print(working)

                    # Porównanie tokenu.

                    if (
                        working
                        != camera["url"]
                    ):

                        print()
                        print(
                            "TOKEN/URL JEST "
                            "INNY NIŻ W M3U."
                        )

                else:

                    fresh_failed += 1

                    print()
                    print(
                        "PRZECHWYCONO HLS, "
                        "ALE TEST NIE PRZESZEDŁ."
                    )

        await browser.close()

    print()
    print("#" * 78)
    print("PODSUMOWANIE EARTHCAM")
    print("#" * 78)

    print(
        "Obecne HLS działają:",
        current_ok
    )

    print(
        "Świeże HLS przechwycone "
        "i działają:",
        fresh_ok
    )

    print(
        "Przechwycone, ale nie działają:",
        fresh_failed
    )

    print(
        "Nie udało się przechwycić:",
        no_capture
    )

    print("#" * 78)


if __name__ == "__main__":
    asyncio.run(main())

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


# Rozpoznaje zarówno:
#
# .../slug/index.m3u8
# .../slug/live-xxxxxxxxxx.m3u8
#
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


def page_url(slug):

    return (
        "https://www.idokep.hu/"
        f"webkamera/{slug}"
    )


def headers_for(slug):

    return {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": page_url(slug),
        "Origin": "https://www.idokep.hu",
    }


def test_segment(
    session,
    url,
    slug,
):

    try:

        headers = headers_for(slug)
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
    slug,
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
            headers=headers_for(slug),
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

    # ------------------------------------------------
    # MASTER PLAYLIST
    # ------------------------------------------------

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
                slug,
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

    # ------------------------------------------------
    # MEDIA PLAYLIST
    # ------------------------------------------------

    extinf_count = sum(
        1
        for line in playlist_lines
        if line.startswith("#EXTINF:")
    )

    segments = []

    for line in playlist_lines:

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
        extinf_count == 0
        or not segments
    ):

        return {
            "ok": False,
            "status": "M3U8 BEZ SEGMENTÓW",
            "segments": 0,
        }

    # Dla LIVE najlepiej sprawdzać
    # najświeższe segmenty.

    for segment in segments[-3:]:

        if test_segment(
            session,
            segment,
            slug,
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


async def capture_fresh_hls(
    browser,
    slug,
    session,
):

    source_page = page_url(slug)

    # Dwie próby, gdyby kamera/player
    # uruchomił się z opóźnieniem.

    for attempt in range(1, 3):

        print(
            f"  Próba przechwycenia "
            f"{attempt}/2"
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

            lower = url.lower()

            if ".m3u8" not in lower:
                return

            if "cam.idokep.hu/live/" not in lower:
                return

            expected = (
                f"/live/{slug.lower()}/"
            )

            if expected not in lower:
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

            print(
                "  STRONA:",
                source_page
            )

            await page.goto(
                source_page,
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

        if not found:

            print(
                "  Nie przechwycono M3U8."
            )

            continue

        # Preferujemy dynamiczne:
        #
        # live-XXXXXXXXXX.m3u8

        dynamic = [
            url
            for url in found
            if re.search(
                r"/live-[A-Za-z0-9_-]+\.m3u8",
                url,
                re.IGNORECASE,
            )
        ]

        candidates = (
            dynamic
            + [
                url
                for url in found
                if url not in dynamic
            ]
        )

        # Sprawdzamy każdy kandydat.
        # Zwracamy pierwszy naprawdę działający.

        for candidate in candidates:

            result = check_hls(
                session,
                candidate,
                slug,
            )

            print(
                "  TEST:",
                candidate
            )

            print(
                "  ",
                result["status"],
                "| segmenty:",
                result["segments"],
            )

            if result["ok"]:
                return candidate

    return None


async def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    # slug -> wszystkie wystąpienia
    # tej kamery w M3U.

    cameras = {}

    for index, line in enumerate(lines):

        match = IDOKEP_RE.search(
            line
        )

        if not match:
            continue

        slug = match.group(1)

        if slug not in cameras:
            cameras[slug] = []

        cameras[slug].append({
            "line_index": index,
            "name": get_camera_name(
                lines,
                index,
            ),
            "url": line.strip(),
        })

    print()
    print("#" * 78)
    print(
        "AUTOMATYCZNA AKTUALIZACJA IDŐKÉP"
    )
    print("#" * 78)

    print(
        "Unikalnych kamer Időkép:",
        len(cameras)
    )

    print(
        "Wszystkich wpisów Időkép:",
        sum(
            len(entries)
            for entries in cameras.values()
        )
    )

    session = requests.Session()

    changed = False

    working_count = 0
    refreshed_count = 0
    error_count = 0
    changed_entries = 0

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy="
                "no-user-gesture-required"
            ],
        )

        for slug, entries in cameras.items():

            print()
            print("=" * 78)

            print(
                "SLUG:",
                slug
            )

            for entry in entries:

                print(
                    "KAMERA:",
                    entry["name"]
                )

                print(
                    "OBECNY URL:"
                )

                print(
                    entry["url"]
                )

            # ----------------------------------------
            # Sprawdzamy obecne adresy.
            # ----------------------------------------

            working_url = None

            unique_urls = []

            for entry in entries:

                if (
                    entry["url"]
                    not in unique_urls
                ):
                    unique_urls.append(
                        entry["url"]
                    )

            for old_url in unique_urls:

                print()
                print(
                    "Sprawdzam obecny HLS:"
                )

                print(old_url)

                result = check_hls(
                    session,
                    old_url,
                    slug,
                )

                print(
                    result["status"],
                    "| segmenty:",
                    result["segments"],
                )

                if result["ok"]:

                    working_url = old_url
                    break

            # ----------------------------------------
            # Jeżeli obecny działa - nic nie robimy.
            # ----------------------------------------

            if working_url:

                print(
                    ">>> OBECNY HLS DZIAŁA <<<"
                )

                working_count += 1

                # Jeśli ten sam slug występuje
                # kilka razy, ujednolicamy URL.

                for entry in entries:

                    index = entry[
                        "line_index"
                    ]

                    if (
                        lines[index]
                        != working_url
                    ):

                        lines[index] = (
                            working_url
                        )

                        changed = True
                        changed_entries += 1

                continue

            # ----------------------------------------
            # Obecny HLS nie działa.
            # Pobieramy świeży ze strony.
            # ----------------------------------------

            print()
            print(
                ">>> POTRZEBNE ODŚWIEŻENIE <<<"
            )

            fresh_url = await capture_fresh_hls(
                browser,
                slug,
                session,
            )

            if not fresh_url:

                print()
                print(
                    "BŁĄD: nie znaleziono "
                    "działającego HLS."
                )

                print(
                    "Stary wpis pozostaje "
                    "bez zmian."
                )

                error_count += 1
                continue

            print()
            print(
                "NOWY URL:"
            )

            print(fresh_url)

            # Ostatni test przed zapisem.

            final_result = check_hls(
                session,
                fresh_url,
                slug,
            )

            if not final_result["ok"]:

                print(
                    "BŁĄD: nowy URL przestał "
                    "działać przed zapisem."
                )

                error_count += 1
                continue

            updated_this_slug = False

            for entry in entries:

                index = entry[
                    "line_index"
                ]

                old_url = lines[index]

                if old_url == fresh_url:
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

                print(fresh_url)

                lines[index] = fresh_url

                changed = True
                changed_entries += 1
                updated_this_slug = True

            if updated_this_slug:
                refreshed_count += 1

        await browser.close()

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
        "PODSUMOWANIE IDŐKÉP"
    )
    print("#" * 78)

    print(
        "Już działały:",
        working_count
    )

    print(
        "Odświeżone kamery:",
        refreshed_count
    )

    print(
        "Zmienione wpisy M3U:",
        changed_entries
    )

    print(
        "Błędy/offline:",
        error_count
    )

    print("#" * 78)


asyncio.run(main())

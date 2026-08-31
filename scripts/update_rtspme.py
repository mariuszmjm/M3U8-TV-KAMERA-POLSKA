import asyncio
import pathlib
import re
import urllib.request

from playwright.async_api import async_playwright


PLAYLIST_FILE = pathlib.Path("Kamery-pogodowe.m3u8")


# Przykład:
#
# https://lo.rtsp.me/ABC/1788178203/hls/SBAYGier.m3u8?ip=20.83.159.21
#
# Z tego wyciągamy stałe ID:
# SBAYGier

RTSPME_RE = re.compile(
    r"https?://[^/\s]*rtsp\.me/"
    r"[^\s]+?/hls/"
    r"([A-Za-z0-9_-]+)\.m3u8"
    r"(?:\?[^\s]*)?",
    re.IGNORECASE,
)


USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36"
)


def get_camera_name(lines, index):

    if index <= 0:
        return "(nieznana kamera)"

    previous = lines[index - 1]

    if not previous.startswith("#EXTINF"):
        return "(nieznana kamera)"

    if "," not in previous:
        return "(nieznana kamera)"

    return previous.split(",", 1)[1].strip()


def test_hls(url, camera_id):

    embed_url = (
        f"https://rtsp.me/embed/{camera_id}/"
    )

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                "Referer": embed_url,
                "Origin": "https://rtsp.me",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:

            data = response.read(
                8192
            ).decode(
                "utf-8",
                errors="ignore",
            )

        return "#EXTM3U" in data

    except Exception as e:

        print(
            "  Test obecnego HLS:",
            type(e).__name__,
            str(e),
        )

        return False


async def capture_fresh_hls(
    browser,
    camera_id,
):

    embed_url = (
        f"https://rtsp.me/embed/{camera_id}/"
    )

    # Dwie próby.
    # Niektóre kamery RTSP.ME mogą uruchamiać
    # player dopiero po kilku sekundach.

    for attempt in range(1, 3):

        print(
            f"  Próba pobrania świeżego HLS "
            f"{attempt}/2"
        )

        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={
                "width": 1280,
                "height": 720,
            },
        )

        page = await context.new_page()

        found = []

        def inspect_request(request):

            url = request.url

            lower_url = url.lower()

            if ".m3u8" not in lower_url:
                return

            if "rtsp.me" not in lower_url:
                return

            if (
                f"/hls/{camera_id.lower()}.m3u8"
                not in lower_url
            ):
                return

            if url not in found:

                found.append(url)

                print(
                    "  PRZECHWYCONO:"
                )

                print(
                    " ",
                    url
                )

        page.on(
            "request",
            inspect_request,
        )

        try:

            print(
                "  EMBED:",
                embed_url
            )

            await page.goto(
                embed_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            # Spróbuj uruchomić VIDEO.

            await page.wait_for_timeout(
                2500
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

            # Próbujemy również kliknąć player,
            # jeśli autoplay został zablokowany.

            selectors = [
                "video",
                "[class*='play']",
                "[class*='Play']",
                "button",
            ]

            for selector in selectors:

                try:

                    locator = (
                        page
                        .locator(selector)
                        .first
                    )

                    if await locator.is_visible(
                        timeout=1000
                    ):

                        await locator.click(
                            force=True,
                            timeout=2000,
                        )

                        await page.wait_for_timeout(
                            1000
                        )

                except Exception:
                    pass

            # RTSP.ME czasami potrzebuje
            # kilkunastu sekund.

            await page.wait_for_timeout(
                12000
            )

        except Exception as e:

            print(
                "  BŁĄD playera:",
                e
            )

        finally:

            await context.close()

        if found:

            # Bierzemy ostatni przechwycony URL.
            # Zachowujemy CAŁY adres,
            # w tym ?ip=...

            return found[-1]

        print(
            "  Brak HLS w tej próbie."
        )

    return None


async def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    # camera_id -> lista wystąpień w M3U
    #
    # To ważne, bo ten sam stream może
    # występować w liście więcej niż raz.

    cameras = {}

    for index, line in enumerate(lines):

        match = RTSPME_RE.search(
            line
        )

        if not match:
            continue

        camera_id = match.group(1)

        camera_name = get_camera_name(
            lines,
            index
        )

        if camera_id not in cameras:

            cameras[camera_id] = []

        cameras[camera_id].append({
            "line_index": index,
            "name": camera_name,
            "url": line.strip(),
        })

    print()
    print("#" * 78)
    print("AUTOMATYCZNA AKTUALIZACJA RTSP.ME")
    print("#" * 78)

    print(
        "Unikalnych kamer RTSP.ME:",
        len(cameras)
    )

    print(
        "Wszystkich wpisów RTSP.ME:",
        sum(
            len(items)
            for items in cameras.values()
        )
    )

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

        for camera_id, entries in cameras.items():

            print()
            print("=" * 78)

            print(
                "ID:",
                camera_id
            )

            for entry in entries:

                print(
                    "KAMERA:",
                    entry["name"]
                )

                print(
                    "OBECNY URL:",
                    entry["url"]
                )

            # ------------------------------------------------
            # 1. Najpierw sprawdzamy wszystkie istniejące
            #    adresy tego samego ID.
            # ------------------------------------------------

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

                if test_hls(
                    old_url,
                    camera_id,
                ):

                    print(
                        "  OK - obecny HLS działa."
                    )

                    working_url = old_url

                    break

                else:

                    print(
                        "  HLS nie działa."
                    )

            # ------------------------------------------------
            # 2. Jeżeli jakiś istniejący URL działa,
            #    nie generujemy nowego.
            # ------------------------------------------------

            if working_url:

                working_count += 1

                # Jeżeli ten sam ID występuje kilka razy,
                # a wpisy mają różne URL,
                # ujednolicamy je do działającego adresu.

                for entry in entries:

                    index = entry["line_index"]

                    if (
                        lines[index]
                        != working_url
                    ):

                        print(
                            "  Ujednolicam duplikat:"
                        )

                        print(
                            "   ",
                            entry["name"]
                        )

                        lines[index] = (
                            working_url
                        )

                        changed = True
                        changed_entries += 1

                continue

            # ------------------------------------------------
            # 3. Stary URL nie działa.
            #    Pobieramy świeży przez embed/ID.
            # ------------------------------------------------

            print()
            print(
                ">>> POTRZEBNE ODŚWIEŻENIE <<<"
            )

            fresh_url = await capture_fresh_hls(
                browser,
                camera_id,
            )

            if not fresh_url:

                print()
                print(
                    "BŁĄD: nie udało się uzyskać "
                    "nowego HLS."
                )

                print(
                    "Stare wpisy pozostają "
                    "bez zmian."
                )

                error_count += 1

                continue

            print()
            print(
                "NOWY URL:"
            )

            print(
                fresh_url
            )

            # ------------------------------------------------
            # 4. Koniecznie testujemy świeży URL.
            # ------------------------------------------------

            if not test_hls(
                fresh_url,
                camera_id,
            ):

                print()
                print(
                    "BŁĄD: świeży HLS został "
                    "przechwycony, ale nie działa."
                )

                print(
                    "Stare wpisy pozostają "
                    "bez zmian."
                )

                error_count += 1

                continue

            print(
                "TEST NOWEGO HLS: OK"
            )

            # ------------------------------------------------
            # 5. Podmieniamy WSZYSTKIE wystąpienia
            #    tego ID w M3U.
            #
            #    Zachowujemy ?ip=...
            # ------------------------------------------------

            updated_this_id = False

            for entry in entries:

                index = entry["line_index"]

                old_url = lines[index]

                if old_url == fresh_url:
                    continue

                print()
                print(
                    "AKTUALIZUJĘ:"
                )

                print(
                    "  ",
                    entry["name"]
                )

                print(
                    "STARY:"
                )

                print(
                    "  ",
                    old_url
                )

                print(
                    "NOWY:"
                )

                print(
                    "  ",
                    fresh_url
                )

                lines[index] = fresh_url

                changed = True
                updated_this_id = True
                changed_entries += 1

            if updated_this_id:

                refreshed_count += 1

        await browser.close()

    # --------------------------------------------------------
    # Zapis M3U
    # --------------------------------------------------------

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
    print("PODSUMOWANIE RTSP.ME")
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
        "Błędy:",
        error_count
    )

    print("#" * 78)


asyncio.run(main())

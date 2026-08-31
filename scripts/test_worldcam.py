import asyncio
import pathlib
import re
import urllib.request
from playwright.async_api import async_playwright


PLAYLIST_FILE = pathlib.Path("Kamery-pogodowe.m3u8")


# Rozpoznaje np.:
# https://s1.worldcam.live:8082/gniezno3/index.m3u8?token=...
# https://s1.worldcam.live:8082/grajewo/index.m3u8

WORLDCAM_RE = re.compile(
    r"https?://[^/\s]*worldcam\.live(?::\d+)?/"
    r"([^/?#\s]+)/index\.m3u8(?:\?[^\s]*)?",
    re.IGNORECASE,
)


def camera_name_from_extinf(line):
    """
    Pobiera nazwę kamery z linii #EXTINF.
    """
    if "," in line:
        return line.split(",", 1)[1].strip()

    return "Nieznana kamera"


def test_hls(url, camera_id):
    """
    Sprawdza, czy obecny adres M3U8 nadal działa.
    """

    page_url = (
        f"https://worldcam.live/pl/webcam/{camera_id}"
    )

    try:

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "*/*",
                "Referer": page_url,
            },
        )

        with urllib.request.urlopen(
            req,
            timeout=15
        ) as response:

            data = response.read(
                4096
            ).decode(
                "utf-8",
                errors="ignore"
            )

            if "#EXTM3U" in data:
                return True

    except Exception as e:

        print(
            "Obecny HLS nie działa:",
            str(e)
        )

    return False


def find_worldcam_entries(lines):
    """
    Automatycznie wyszukuje wszystkie wpisy WorldCam
    w pliku M3U8.
    """

    entries = []

    for i, line in enumerate(lines):

        match = WORLDCAM_RE.search(
            line.strip()
        )

        if not match:
            continue

        camera_id = match.group(1)

        if i > 0:
            name = camera_name_from_extinf(
                lines[i - 1]
            )
        else:
            name = camera_id

        entries.append(
            {
                "line_index": i,
                "camera_id": camera_id,
                "name": name,
                "current_url": line.strip(),
            }
        )

    return entries


async def get_fresh_worldcam_url(
    browser,
    camera_id
):

    page_url = (
        f"https://worldcam.live/pl/webcam/{camera_id}"
    )

    page = await browser.new_page()

    found_urls = []

    def check_request(request):

        url = request.url

        if (
            f"/{camera_id}/index.m3u8" in url
            and "token=" in url
        ):

            if url not in found_urls:

                found_urls.append(url)

                print()
                print("Przechwycono:")
                print(url)

    page.on(
        "request",
        check_request
    )

    try:

        print()
        print("Otwieram stronę WorldCam:")
        print(page_url)

        await page.goto(
            page_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        # Czekamy na uruchomienie playera
        await page.wait_for_timeout(
            6000
        )

        # Jeśli token pojawił się od razu,
        # nie trzeba nic więcej robić.

        if found_urls:
            return found_urls[-1]

        # Jeśli pojawi się komunikat:
        # "Sesja oglądania wygasła"
        # próbujemy kliknąć "Oglądaj dalej".

        try:

            button = page.get_by_text(
                "Oglądaj dalej",
                exact=False
            )

            if await button.count() > 0:

                print(
                    "Klikam: Oglądaj dalej"
                )

                await button.first.click()

                await page.wait_for_timeout(
                    7000
                )

        except Exception as e:

            print(
                "Nie udało się użyć "
                "przycisku Oglądaj dalej:",
                e
            )

        if found_urls:

            return found_urls[-1]

        raise RuntimeError(
            "Strona nie wygenerowała "
            "nowego adresu M3U8 z tokenem."
        )

    finally:

        await page.close()


async def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    entries = find_worldcam_entries(
        lines
    )

    print()
    print("#" * 72)
    print("AUTOMATYCZNA KONTROLA WORLDCAM")
    print("#" * 72)

    print()
    print(
        "Znaleziono kamer WorldCam:",
        len(entries)
    )

    changed = False
    ok_count = 0
    updated_count = 0
    error_count = 0

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required"
            ]
        )

        for entry in entries:

            camera_id = entry["camera_id"]
            name = entry["name"]
            current_url = entry["current_url"]
            line_index = entry["line_index"]

            print()
            print("=" * 72)
            print("KAMERA:", name)
            print("ID:", camera_id)
            print("OBECNY URL:")
            print(current_url)
            print("-" * 72)

            # =================================================
            # KROK 1
            # Najpierw sprawdzamy obecny adres.
            # Jeśli działa - zostawiamy go w spokoju.
            # =================================================

            print(
                "Sprawdzam obecny strumień..."
            )

            if test_hls(
                current_url,
                camera_id
            ):

                print(
                    "OK - obecny adres nadal działa."
                )

                ok_count += 1

                continue

            # =================================================
            # KROK 2
            # Obecny adres nie działa.
            # Dopiero teraz uruchamiamy WorldCam.
            # =================================================

            print()
            print(
                "Adres nie działa."
            )

            print(
                "Próbuję uzyskać nowy token..."
            )

            try:

                new_url = (
                    await get_fresh_worldcam_url(
                        browser,
                        camera_id
                    )
                )

                print()
                print("NOWY URL:")
                print(new_url)

                # =============================================
                # KROK 3
                # Sprawdzamy nowo uzyskany URL,
                # zanim zapiszemy go do M3U.
                # =============================================

                print()
                print(
                    "Testuję nowy URL..."
                )

                if not test_hls(
                    new_url,
                    camera_id
                ):

                    print(
                        "BŁĄD: nowy URL został "
                        "znaleziony, ale nie działa."
                    )

                    error_count += 1

                    continue

                # Wszystko OK - podmieniamy.

                lines[line_index] = new_url

                changed = True
                updated_count += 1

                print()
                print(
                    ">>> ADRES ZOSTAŁ "
                    "AUTOMATYCZNIE "
                    "ZAKTUALIZOWANY <<<"
                )

            except Exception as e:

                error_count += 1

                print()
                print(
                    "NIE UDAŁO SIĘ "
                    "ODŚWIEŻYĆ KAMERY:"
                )

                print(e)

                # Bardzo ważne:
                # nie kasujemy starego wpisu.
                # Przechodzimy do kolejnej kamery.

                continue

        await browser.close()

    # =====================================================
    # ZAPIS
    # =====================================================

    if changed:

        PLAYLIST_FILE.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8"
        )

        print()
        print("#" * 72)
        print(
            "ZAPISANO ZMIANY W "
            "Kamery-pogodowe.m3u8"
        )
        print("#" * 72)

    else:

        print()
        print(
            "Nie było zmian do zapisania."
        )

    # =====================================================
    # PODSUMOWANIE
    # =====================================================

    print()
    print("#" * 72)
    print("PODSUMOWANIE WORLDCAM")
    print("#" * 72)

    print(
        "Znalezione kamery:",
        len(entries)
    )

    print(
        "Działające bez zmian:",
        ok_count
    )

    print(
        "Automatycznie naprawione:",
        updated_count
    )

    print(
        "Błędy:",
        error_count
    )

    print("#" * 72)


asyncio.run(main())

import asyncio
import pathlib
import re
import urllib.request
from urllib.parse import urlparse

from playwright.async_api import async_playwright


PLAYLIST_FILE = pathlib.Path("Kamery-pogodowe.m3u8")


PAGES = {
    "Gdynia": {
        "url": "https://www.peregrinus.pl/pl/gdynia",
        "cameras": [
            "Gdynia PGE EC LIVE",
            "Gdynia PGE EC LIVE 2",
            "Gdynia PGE EC LIVE 3",
        ],
    },

    "Toruń": {
        "url": "https://www.peregrinus.pl/pl/torun",
        "cameras": [
            "Toruń PGE EC LIVE 1",
            "Toruń PGE EC LIVE 2",
            "Toruń PGE EC LIVE 3",
        ],
    },

    "Lublin": {
        "url": "https://www.peregrinus.pl/pl/lublin",
        "cameras": [
            "Lublin PGE EC LIVE 1",
            "Lublin PGE EC LIVE 2",
            "Lublin PGE EC LIVE 3",
        ],
    },
}


UUID_HTML_RE = re.compile(
    r"^/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.html$"
)


def test_hls(url, referer):

    try:

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "*/*",
                "Referer": referer,
            },
        )

        with urllib.request.urlopen(
            req,
            timeout=20
        ) as response:

            text = response.read(
                4096
            ).decode(
                "utf-8",
                errors="ignore",
            )

            return "#EXTM3U" in text

    except Exception as e:

        print(
            "  BŁĄD TESTU HLS:",
            e
        )

        return False


def find_camera_line(
    lines,
    camera_name
):

    for i, line in enumerate(lines):

        if not line.startswith("#EXTINF"):
            continue

        if "," not in line:
            continue

        name = (
            line.split(",", 1)[1]
            .strip()
        )

        if name == camera_name:

            if i + 1 >= len(lines):

                raise RuntimeError(
                    f"Brak adresu pod wpisem: "
                    f"{camera_name}"
                )

            return i + 1

    raise RuntimeError(
        f'Nie znaleziono wpisu '
        f'"{camera_name}" w pliku M3U.'
    )


def iframe_to_stream_url(
    iframe_url
):

    parsed = urlparse(
        iframe_url
    )

    match = UUID_HTML_RE.match(
        parsed.path
    )

    if not match:
        return None

    uuid = match.group(1)

    # Korzystamy z tego samego serwera,
    # na którym znajduje się iframe.
    # Obecnie jest to sokoly.ovh.

    return (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"/memfs/{uuid}.m3u8"
    )


async def get_streams_from_page(
    page,
    place,
    page_url
):

    print()
    print("=" * 72)
    print(
        "LOKALIZACJA:",
        place
    )
    print(
        "STRONA:",
        page_url
    )
    print("=" * 72)

    await page.goto(
        page_url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    await page.wait_for_timeout(
        5000
    )

    # Pobieramy iframe'y dokładnie
    # w kolejności występującej
    # na stronie.

    iframe_srcs = (
        await page
        .locator("iframe")
        .evaluate_all(
            """
            els => els
                .map(e => e.src)
                .filter(Boolean)
            """
        )
    )

    stream_urls = []

    for iframe_url in iframe_srcs:

        stream_url = (
            iframe_to_stream_url(
                iframe_url
            )
        )

        if not stream_url:
            continue

        if stream_url in stream_urls:
            continue

        stream_urls.append(
            stream_url
        )

        print()
        print("IFRAME:")
        print(iframe_url)

        print("M3U8:")
        print(stream_url)

    if len(stream_urls) != 3:

        raise RuntimeError(
            f"{place}: oczekiwano "
            f"3 kamer, znaleziono "
            f"{len(stream_urls)}."
        )

    return stream_urls


async def main():

    text = (
        PLAYLIST_FILE
        .read_text(
            encoding="utf-8"
        )
    )

    lines = text.splitlines()

    changed = False

    updated_count = 0
    unchanged_count = 0
    error_count = 0

    print()
    print("#" * 72)
    print(
        "AUTOMATYCZNA AKTUALIZACJA "
        "PEREGRINUS"
    )
    print("#" * 72)

    async with async_playwright() as p:

        browser = (
            await p.chromium.launch(
                headless=True
            )
        )

        for place, config in PAGES.items():

            context = (
                await browser.new_context()
            )

            page = (
                await context.new_page()
            )

            try:

                stream_urls = (
                    await get_streams_from_page(
                        page,
                        place,
                        config["url"],
                    )
                )

                # Łączymy:
                #
                # iframe 1 -> LIVE 1
                # iframe 2 -> LIVE 2
                # iframe 3 -> LIVE 3

                for camera_name, new_url in zip(
                    config["cameras"],
                    stream_urls,
                ):

                    print()
                    print("-" * 72)

                    print(
                        "KAMERA:",
                        camera_name
                    )

                    print(
                        "NOWY URL:",
                        new_url
                    )

                    # Najpierw sprawdzamy,
                    # czy nowy HLS faktycznie działa.

                    if not test_hls(
                        new_url,
                        config["url"],
                    ):

                        print(
                            "  BŁĄD: wygenerowany "
                            "HLS nie działa."
                        )

                        print(
                            "  Stary adres "
                            "pozostaje bez zmian."
                        )

                        error_count += 1

                        continue

                    url_line = (
                        find_camera_line(
                            lines,
                            camera_name,
                        )
                    )

                    old_url = (
                        lines[url_line]
                    )

                    print(
                        "STARY URL:",
                        old_url
                    )

                    if old_url == new_url:

                        print(
                            "  OK - adres "
                            "bez zmian."
                        )

                        unchanged_count += 1

                        continue

                    lines[url_line] = (
                        new_url
                    )

                    changed = True
                    updated_count += 1

                    print(
                        "  >>> ADRES "
                        "ZAKTUALIZOWANY <<<"
                    )

            except Exception as e:

                error_count += 1

                print()
                print(
                    f"BŁĄD dla lokalizacji "
                    f"{place}:"
                )

                print(e)

            finally:

                await context.close()

        await browser.close()

    if changed:

        PLAYLIST_FILE.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
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
            "Nie było zmian "
            "do zapisania."
        )

    print()
    print("#" * 72)
    print(
        "PODSUMOWANIE PEREGRINUS"
    )
    print("#" * 72)

    print(
        "Zaktualizowane:",
        updated_count
    )

    print(
        "Bez zmian:",
        unchanged_count
    )

    print(
        "Błędy:",
        error_count
    )

    print("#" * 72)


asyncio.run(main())

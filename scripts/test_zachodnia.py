import urllib3

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)
import asyncio
import requests
from playwright.async_api import async_playwright


PAGE = "https://embed.karkonosze.online/ssl/chojnik"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36"
)


def test_hls(url):
    print()
    print("TEST HLS:")
    print(url)

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": PAGE,
        "Accept": "*/*",
    }

    try:
        r = requests.get(
    url,
    headers=headers,
    timeout=20,
    allow_redirects=True,
    verify=False,
)
        )
    except Exception as e:
        print("BŁĄD:", repr(e))
        return False

    print("HTTP:", r.status_code)

    if r.status_code != 200:
        return False

    if "#EXTM3U" not in r.text:
        print("Brak #EXTM3U")
        return False

    print("PLAYLISTA M3U8: OK")

    lines = [
        x.strip()
        for x in r.text.splitlines()
        if x.strip()
    ]

    segments = [
        x for x in lines
        if not x.startswith("#")
    ]

    print("Elementów playlisty:", len(segments))

    return True


async def main():
    print("#" * 78)
    print("TEST ZACHODNIA.TV / WOWZA TOKEN")
    print("#" * 78)

    found = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required"
            ],
        )

        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={
                "width": 1280,
                "height": 800,
            },
        )

        page = await context.new_page()

        def inspect(request):
            url = request.url
            lower = url.lower()

            if ".m3u8" not in lower:
                return

            if "zachodnia.tv" not in lower:
                return

            if url not in found:
                found.append(url)

                print()
                print("PRZECHWYCONO:")
                print(url)

        page.on("request", inspect)

        print()
        print("Otwieram:")
        print(PAGE)

        try:
            await page.goto(
                PAGE,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(5000)

            # Próba uruchomienia video
            try:
                await page.evaluate(
                    """
                    () => {
                        document
                        .querySelectorAll('video')
                        .forEach(v => {
                            v.muted = true;
                            v.play().catch(() => {});
                        });
                    }
                    """
                )
            except Exception:
                pass

            await page.wait_for_timeout(15000)

        finally:
            await context.close()
            await browser.close()

    print()
    print("#" * 78)
    print("WYNIK")
    print("#" * 78)

    if not found:
        print("Nie przechwycono żadnego M3U8.")
        return

    playlist_urls = [
        u for u in found
        if "playlist.m3u8" in u.lower()
    ]

    if not playlist_urls:
        playlist_urls = found

    for url in playlist_urls:

        print()
        print("-" * 78)

        if "wowzatokenstarttime=" in url:
            print("TOKEN WOWZA: TAK")
        else:
            print("TOKEN WOWZA: NIE")

        if test_hls(url):

            print()
            print("#" * 78)
            print("ŚWIEŻY URL DO TESTU W M3U-IP.TV:")
            print()
            print(url)
            print()
            print(
                "Skopiuj ten adres OD RAZU po zakończeniu Action."
            )
            print("#" * 78)

            return


if __name__ == "__main__":
    asyncio.run(main())

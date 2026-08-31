import asyncio
from playwright.async_api import async_playwright


PAGE_URL = "https://worldcam.live/pl/webcam/gniezno3"
CAMERA_ID = "gniezno3"


async def main():

    found_urls = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        def check_request(request):

            url = request.url

            if (
                ".m3u8" in url
                and CAMERA_ID in url
            ):

                if url not in found_urls:

                    found_urls.append(url)

                    print()
                    print("=" * 70)
                    print("ZNALEZIONO M3U8:")
                    print(url)
                    print("=" * 70)
                    print()

        page.on(
            "request",
            check_request
        )

        print("Otwieram:")
        print(PAGE_URL)

        await page.goto(
            PAGE_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        # czekamy, aż player zacznie pobierać transmisję
        await page.wait_for_timeout(10000)

        # Jeżeli strona pokazuje przycisk
        # "Oglądaj dalej", próbujemy go kliknąć.

        try:

            button = page.get_by_text(
                "Oglądaj dalej",
                exact=False
            )

            if await button.count() > 0:

                print("Klikam: Oglądaj dalej")

                await button.first.click()

                await page.wait_for_timeout(
                    10000
                )

        except Exception as e:

            print(
                "Nie udało się kliknąć przycisku:",
                e
            )

        await browser.close()

    print()
    print("#" * 70)

    if found_urls:

        print("ZNALEZIONE ADRESY WORLDCAM:")

        for url in found_urls:
            print(url)

    else:

        print("NIE ZNALEZIONO M3U8.")

    print("#" * 70)


asyncio.run(main())

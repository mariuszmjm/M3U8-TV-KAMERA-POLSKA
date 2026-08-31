import asyncio
from collections import defaultdict
from playwright.async_api import async_playwright


PAGES = {
    "Gdynia": "https://www.peregrinus.pl/pl/gdynia",
    "Toruń": "https://www.peregrinus.pl/pl/torun",
    "Lublin": "https://www.peregrinus.pl/pl/lublin",
}


async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required"
            ]
        )

        for place, page_url in PAGES.items():

            print()
            print("#" * 80)
            print("LOKALIZACJA:", place)
            print("STRONA:", page_url)
            print("#" * 80)

            context = await browser.new_context()

            page = await context.new_page()

            found = []
            found_by_frame = defaultdict(list)

            def inspect_request(request):

                url = request.url

                if ".m3u8" not in url.lower():
                    return

                try:
                    frame_url = request.frame.url
                except Exception:
                    frame_url = "(nieznana ramka)"

                item = (
                    frame_url,
                    url
                )

                if item not in found:
                    found.append(item)

                if url not in found_by_frame[frame_url]:
                    found_by_frame[frame_url].append(url)

            page.on(
                "request",
                inspect_request
            )

            try:

                await page.goto(
                    page_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )

                # Dajemy iframe'om czas na uruchomienie playerów
                await page.wait_for_timeout(20000)

                print()
                print("IFRAME NA STRONIE:")
                print()

                frames = page.frames

                for number, frame in enumerate(
                    frames,
                    start=1
                ):

                    print(
                        f"FRAME #{number}:",
                        frame.url
                    )

            except Exception as e:

                print()
                print("BŁĄD OTWIERANIA STRONY:")
                print(e)

            print()
            print("=" * 80)
            print("ZNALEZIONE M3U8")
            print("=" * 80)

            if not found:

                print(
                    "Nie znaleziono żadnego M3U8."
                )

            else:

                for number, (frame_url, stream_url) in enumerate(
                    found,
                    start=1
                ):

                    print()
                    print(
                        f"M3U8 #{number}"
                    )

                    print("RAMKA:")
                    print(frame_url)

                    print("STREAM:")
                    print(stream_url)

                    if (
                        "sokoly.edu.pl/memfs/"
                        in stream_url
                    ):

                        print(
                            ">>> TO JEST MEMFS PEREGRINUSA <<<"
                        )

            print()
            print("=" * 80)
            print("PODSUMOWANIE:", place)
            print("=" * 80)

            unique_streams = []

            for _, url in found:

                if url not in unique_streams:
                    unique_streams.append(url)

            print(
                "Liczba unikalnych M3U8:",
                len(unique_streams)
            )

            peregrinus_streams = [
                url
                for url in unique_streams
                if (
                    "sokoly.edu.pl/memfs/"
                    in url
                )
            ]

            print(
                "Liczba memfs sokoly.edu.pl:",
                len(peregrinus_streams)
            )

            print()

            for number, url in enumerate(
                peregrinus_streams,
                start=1
            ):

                print(
                    f"KAMERA {number}:"
                )

                print(url)

            await context.close()

        await browser.close()


asyncio.run(main())

import asyncio
import hashlib
from playwright.async_api import async_playwright


CAMERAS = {
    "Rodos - Brama Morska":
        "https://www.skylinewebcams.com/pl/webcam/ellada/naigaio/dodecanisa/rhodes-sea-gate.html",

    "Nowy Sącz":
        "https://www.skylinewebcams.com/pl/webcam/poland/lesser-poland-voivodeship/nowy-sacz/streets.html",

    "Lima - Miraflores":
        "https://www.skylinewebcams.com/pl/webcam/peru/lima/lima/miraflores.html",
}


async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required"
            ]
        )

        for camera_name, page_url in CAMERAS.items():

            print()
            print("#" * 80)
            print("KAMERA:", camera_name)
            print("STRONA:", page_url)
            print("#" * 80)

            # Każda kamera dostaje całkowicie
            # oddzielną sesję przeglądarki.
            context = await browser.new_context()

            page = await context.new_page()

            results = []
            tasks = []

            async def inspect_response(response):

                url = response.url

                if ".m3u8" not in url.lower():
                    return

                try:
                    headers = await response.request.all_headers()
                except Exception:
                    headers = {}

                referer = headers.get("referer", "")
                origin = headers.get("origin", "")
                cookie = headers.get("cookie", "")

                try:
                    body = await response.body()

                    text = body.decode(
                        "utf-8",
                        errors="ignore"
                    )

                    sha = hashlib.sha256(
                        body
                    ).hexdigest()[:16]

                except Exception as e:

                    text = (
                        "Nie udało się pobrać "
                        f"zawartości: {e}"
                    )

                    sha = "BRAK"

                results.append({
                    "url": url,
                    "referer": referer,
                    "origin": origin,
                    "cookie": bool(cookie),
                    "sha": sha,
                    "text": text,
                })

            def on_response(response):

                task = asyncio.create_task(
                    inspect_response(response)
                )

                tasks.append(task)

            page.on(
                "response",
                on_response
            )

            try:

                await page.goto(
                    page_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )

                # Czekamy na uruchomienie odtwarzacza.
                await page.wait_for_timeout(
                    15000
                )

                # Dodatkowe oczekiwanie,
                # jeżeli player ładuje playlisty wolniej.
                await page.wait_for_timeout(
                    5000
                )

            except Exception as e:

                print(
                    "BŁĄD otwierania strony:",
                    e
                )

            if tasks:

                await asyncio.gather(
                    *tasks,
                    return_exceptions=True
                )

            print()
            print(
                "LICZBA PRZECHWYCONYCH M3U8:",
                len(results)
            )

            print()

            for number, result in enumerate(
                results,
                start=1
            ):

                print("-" * 80)

                print(
                    f"M3U8 #{number}"
                )

                print("URL:")
                print(result["url"])

                print()
                print("REFERER:")
                print(
                    result["referer"]
                    or "(brak)"
                )

                print()
                print("ORIGIN:")
                print(
                    result["origin"]
                    or "(brak)"
                )

                print()
                print(
                    "COOKIE:",
                    "TAK"
                    if result["cookie"]
                    else "NIE"
                )

                print()
                print(
                    "SHA256 PLAYLISTY:",
                    result["sha"]
                )

                print()
                print(
                    "POCZĄTEK PLAYLISTY:"
                )

                lines = [
                    line
                    for line
                    in result["text"].splitlines()
                    if line.strip()
                ]

                for line in lines[:20]:
                    print(line)

                print()

            await context.close()

        await browser.close()


asyncio.run(main())

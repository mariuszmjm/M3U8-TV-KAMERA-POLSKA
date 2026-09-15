import asyncio
import re

import requests
import urllib3
from playwright.async_api import async_playwright


PAGE = "https://embed.karkonosze.online/ssl/chojnik"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36"
)

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


KEYWORDS = (
    "wowzatoken",
    "playlist.m3u8",
    "webcam10.zachodnia.tv",
    "jelenia_chojnik",
)


def contains_interesting(text):
    lower = text.lower()

    return any(
        keyword.lower() in lower
        for keyword in KEYWORDS
    )


def show_matches(title, text):
    if not contains_interesting(text):
        return False

    print()
    print("=" * 78)
    print(title)
    print("=" * 78)

    lines = text.splitlines()

    found = False

    for line in lines:
        if contains_interesting(line):
            print(line[:1500])
            found = True

    return found


async def main():

    print("#" * 78)
    print("OSTATNI TEST ZACHODNIA.TV")
    print("#" * 78)

    print()
    print("CEL:")
    print(
        "Sprawdzamy, czy token Wowza można uzyskać "
        "bez pełnej przeglądarki."
    )

    # -------------------------------------------------
    # TEST 1 - zwykłe pobranie HTML
    # -------------------------------------------------

    print()
    print("#" * 78)
    print("1. ZWYKŁE POBRANIE HTML")
    print("#" * 78)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
    }

    html_has_token = False

    try:
        response = requests.get(
            PAGE,
            headers=headers,
            timeout=20,
            verify=False,
            allow_redirects=True,
        )

        print("HTTP:", response.status_code)
        print("Rozmiar HTML:", len(response.text))

        html_has_token = show_matches(
            "ZNALEZIONO W SUROWYM HTML",
            response.text,
        )

        if not html_has_token:
            print()
            print(
                "W surowym HTML nie znaleziono "
                "tokena ani adresu HLS."
            )

    except Exception as e:
        print("BŁĄD HTTP:", repr(e))

    # -------------------------------------------------
    # TEST 2 - przeglądarka
    # -------------------------------------------------

    print()
    print("#" * 78)
    print("2. ANALIZA PRZEGLĄDARKI")
    print("#" * 78)

    hls_urls = []
    xhr_urls = []

    token_in_api = False
    token_in_script = False
    token_in_dom = False

    response_tasks = []

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

        # -----------------------------------------
        # Wszystkie requesty
        # -----------------------------------------

        def inspect_request(request):
            url = request.url
            rtype = request.resource_type

            if ".m3u8" in url.lower():
                if url not in hls_urls:
                    hls_urls.append(url)

                    print()
                    print("HLS REQUEST:")
                    print(url)

            if rtype in ("xhr", "fetch"):
                if url not in xhr_urls:
                    xhr_urls.append(url)

                    print()
                    print(
                        f"{rtype.upper()} REQUEST:"
                    )
                    print(url)

        page.on(
            "request",
            inspect_request
        )

        # -----------------------------------------
        # Analiza odpowiedzi API / JS
        # -----------------------------------------

        async def inspect_response(response):
            nonlocal token_in_api
            nonlocal token_in_script

            try:
                request = response.request
                rtype = request.resource_type
                url = response.url

                content_type = (
                    response.headers.get(
                        "content-type",
                        ""
                    ).lower()
                )

                interesting_type = (
                    rtype in (
                        "xhr",
                        "fetch",
                        "script",
                    )
                    or "json" in content_type
                    or "javascript" in content_type
                    or "text/" in content_type
                )

                if not interesting_type:
                    return

                body = await response.text()

                if len(body) > 2_000_000:
                    return

                if not contains_interesting(body):
                    return

                print()
                print("=" * 78)
                print(
                    "CIEKAWA ODPOWIEDŹ:"
                )
                print(
                    "Typ:",
                    rtype
                )
                print(
                    "HTTP:",
                    response.status
                )
                print(
                    "URL:"
                )
                print(url)
                print("=" * 78)

                # Pokazujemy tylko okolice słów kluczowych

                lower = body.lower()

                for keyword in KEYWORDS:

                    pos = lower.find(
                        keyword.lower()
                    )

                    if pos == -1:
                        continue

                    start = max(
                        0,
                        pos - 500
                    )

                    end = min(
                        len(body),
                        pos + 1500
                    )

                    print()
                    print(
                        f"--- {keyword} ---"
                    )
                    print(
                        body[start:end]
                    )

                if rtype in (
                    "xhr",
                    "fetch",
                ):
                    token_in_api = True

                if rtype == "script":
                    token_in_script = True

            except Exception:
                pass

        def response_callback(response):
            task = asyncio.create_task(
                inspect_response(response)
            )
            response_tasks.append(task)

        page.on(
            "response",
            response_callback
        )

        print()
        print("Otwieram:")
        print(PAGE)

        try:
            await page.goto(
                PAGE,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(
                5000
            )

            # Próba uruchomienia video

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
                15000
            )

            # -------------------------------------
            # DOM po wykonaniu JavaScript
            # -------------------------------------

            try:
                dom = await page.content()

                if contains_interesting(dom):

                    token_in_dom = True

                    show_matches(
                        "TOKEN/HLS W DOM "
                        "PO WYKONANIU JAVASCRIPT",
                        dom,
                    )

            except Exception:
                pass

            # Poczekaj na analizę odpowiedzi

            if response_tasks:
                await asyncio.gather(
                    *response_tasks,
                    return_exceptions=True,
                )

        finally:
            await context.close()
            await browser.close()

    # -------------------------------------------------
    # PODSUMOWANIE
    # -------------------------------------------------

    print()
    print("#" * 78)
    print("PODSUMOWANIE")
    print("#" * 78)

    print()
    print(
        "Token/HLS w zwykłym HTML:",
        "TAK" if html_has_token else "NIE"
    )

    print(
        "Token/HLS w odpowiedzi XHR/API:",
        "TAK" if token_in_api else "NIE"
    )

    print(
        "Token/HLS w pliku JavaScript:",
        "TAK" if token_in_script else "NIE"
    )

    print(
        "Token/HLS dopiero w DOM:",
        "TAK" if token_in_dom else "NIE"
    )

    print(
        "Przechwyconych HLS:",
        len(hls_urls)
    )

    print(
        "Przechwyconych XHR/FETCH:",
        len(xhr_urls)
    )

    print()

    if html_has_token:
        print(
            "WYNIK: BARDZO DOBRY."
        )
        print(
            "Token jest dostępny zwykłym żądaniem HTTP."
        )
        print(
            "Cloudflare Worker powinien być możliwy."
        )

    elif token_in_api:
        print(
            "WYNIK: DOBRY."
        )
        print(
            "Token lub dane HLS przychodzą "
            "z osobnego API/XHR."
        )
        print(
            "Jeśli endpoint jest prosty, Worker "
            "powinien dać się zrobić."
        )

    elif token_in_script:
        print(
            "WYNIK: POŚREDNI."
        )
        print(
            "Mechanizm znajduje się w JavaScript."
        )
        print(
            "Sprawdzimy, czy jest prosty. "
            "Jeśli nie - odpuszczamy."
        )

    elif hls_urls:
        print(
            "WYNIK: NIEKORZYSTNY."
        )
        print(
            "Przeglądarka wygenerowała działający HLS, "
            "ale nie znaleźliśmy prostego źródła tokenu."
        )
        print(
            "Zgodnie z założeniem: odpuszczamy Zachodnia.tv."
        )

    else:
        print(
            "WYNIK: BRAK UŻYTECZNEGO MECHANIZMU."
        )
        print(
            "Odpuszczamy Zachodnia.tv."
        )

    print("#" * 78)


if __name__ == "__main__":
    asyncio.run(main())

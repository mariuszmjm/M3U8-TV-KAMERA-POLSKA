import asyncio
import pathlib
import re
import urllib.request

from playwright.async_api import async_playwright


PLAYLIST_FILE = pathlib.Path(
    "Kamery-pogodowe.m3u8"
)


RTSPME_RE = re.compile(
    r"https?://[^/\s]*rtsp\.me/"
    r"[^\s]+?/hls/"
    r"([A-Za-z0-9_-]+)\.m3u8"
    r"(?:\?[^\s]*)?",
    re.IGNORECASE,
)


def get_camera_name(lines, index):

    if index == 0:
        return "(nieznana kamera)"

    previous = lines[index - 1]

    if not previous.startswith("#EXTINF"):
        return "(nieznana kamera)"

    if "," not in previous:
        return "(nieznana kamera)"

    return previous.split(
        ",",
        1
    )[1].strip()


def test_hls(url, referer):

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/140.0 Safari/537.36",

                "Accept": "*/*",

                "Referer": referer,
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:

            data = response.read(
                8192
            ).decode(
                "utf-8",
                errors="ignore"
            )

        return "#EXTM3U" in data

    except Exception as e:

        print(
            "Błąd testu HLS:",
            e
        )

        return False


async def get_fresh_hls(
    browser,
    camera_id
):

    embed_url = (
        f"https://rtsp.me/embed/"
        f"{camera_id}/"
    )

    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0 Safari/537.36"
        )
    )

    page = await context.new_page()

    found = []

    def inspect_request(request):

        url = request.url

        if ".m3u8" not in url.lower():
            return

        if "rtsp.me" not in url.lower():
            return

        if (
            f"/hls/{camera_id}.m3u8"
            not in url
        ):
            return

        if url not in found:
            found.append(url)

    page.on(
        "request",
        inspect_request
    )

    try:

        print(
            "EMBED:",
            embed_url
        )

        await page.goto(
            embed_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        await page.wait_for_timeout(
            3000
        )

        # Spróbuj uruchomić VIDEO,
        # jeśli player nie wystartuje sam.

        try:

            await page.evaluate(
                """
                () => {
                    const video =
                        document.querySelector('video');

                    if (video) {
                        video.muted = true;
                        video.play().catch(() => {});
                    }
                }
                """
            )

        except Exception:
            pass

        # Spróbuj kliknąć element playera.

        selectors = [
            "video",
            "button",
            "[class*='play']",
            "[class*='Play']",
        ]

        for selector in selectors:

            try:

                locator = page.locator(
                    selector
                ).first

                if await locator.is_visible(
                    timeout=1000
                ):

                    await locator.click(
                        timeout=2000,
                        force=True
                    )

                    await page.wait_for_timeout(
                        1500
                    )

            except Exception:
                pass

        # Dajemy playerowi czas na wygenerowanie HLS.

        await page.wait_for_timeout(
            12000
        )

    except Exception as e:

        print(
            "BŁĄD PLAYERA:",
            e
        )

    finally:

        await context.close()

    if not found:
        return None

    # Najnowszy przechwycony adres.

    return found[-1]


async def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    cameras = []

    seen_ids = set()

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

        if camera_id in seen_ids:

            print()
            print(
                "DUPLIKAT ID:",
                camera_id,
                "-",
                camera_name
            )

            continue

        seen_ids.add(
            camera_id
        )

        cameras.append({
            "name": camera_name,
            "id": camera_id,
            "old_url": line.strip(),
        })

    print()
    print("#" * 76)
    print("TEST RTSP.ME")
    print("#" * 76)

    print(
        "Znalezionych unikalnych kamer:",
        len(cameras)
    )

    print()

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy="
                "no-user-gesture-required"
            ]
        )

        success = 0
        errors = 0

        for camera in cameras:

            print()
            print("=" * 76)

            print(
                "KAMERA:",
                camera["name"]
            )

            print(
                "ID:",
                camera["id"]
            )

            print(
                "STARY URL:"
            )

            print(
                camera["old_url"]
            )

            fresh_url = await get_fresh_hls(
                browser,
                camera["id"]
            )

            if not fresh_url:

                print()
                print(
                    "NIE ZNALEZIONO NOWEGO HLS"
                )

                errors += 1

                continue

            print()
            print(
                "NOWY URL:"
            )

            print(
                fresh_url
            )

            print()
            print(
                "ADRES SIĘ ZMIENIŁ:",
                (
                    "TAK"
                    if fresh_url
                    != camera["old_url"]
                    else "NIE"
                )
            )

            embed_url = (
                "https://rtsp.me/embed/"
                f"{camera['id']}/"
            )

            working = test_hls(
                fresh_url,
                embed_url
            )

            print(
                "TEST #EXTM3U:",
                (
                    "OK"
                    if working
                    else "BŁĄD"
                )
            )

            if working:
                success += 1
            else:
                errors += 1

        await browser.close()

    print()
    print("#" * 76)
    print("PODSUMOWANIE RTSP.ME")
    print("#" * 76)

    print(
        "Działa:",
        success
    )

    print(
        "Błędy:",
        errors
    )

    print("#" * 76)


asyncio.run(main())

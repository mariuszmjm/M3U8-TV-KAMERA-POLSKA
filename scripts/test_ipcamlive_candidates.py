import concurrent.futures
import json
import sys
from urllib.parse import quote, urljoin, urlparse

import requests


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36"
)

TIMEOUT = 10
WORKERS = 6


# ============================================================
# KANDYDACI IPCAMLIVE
# ============================================================

CAMERAS = {
    "wiezowieczachod":
        "Polska - Bolesławiec - panorama",

    "riminieyecom":
        "Włochy - Rimini",

    "znpvkamera2":
        "Słowenia - Planina nad Vrhniko",

    "53f1a5f94b1d0":
        "Węgry - Dombóvár",

    "falken":
        "Kamera sokołów",

    "wellsjettycam":
        "Wells - Jetty Cam",

    "vihtiskicenter2":
        "Finlandia - Vihti Ski Center",

    "662e60647a0a5":
        "Szkocja - Tayport Harbour 360",

    "68e63bc7e1b23":
        "Anglia - Littlehampton Harbour North",

    "6654f97b9fdf3":
        "Anglia - Pagham Beach",

    "cotswold":
        "Anglia - Cotswold Airport",

    "airportbrac":
        "Chorwacja - lotnisko Brac",

    "kovacine":
        "Chorwacja - Kovacine",

    "hotelkalle":
        "Estonia - Ontika - bocian",

    "644e316350948":
        "Wyspy Owcze - kamera pogodowa",

    "62da90f20979d":
        "Włochy - Ischia - Maronti",

    "lidosiriowebcam":
        "Włochy - Gaeta - Lido Sirio",

    "bagnoflavio":
        "Włochy - Bagno Flavio",

    "hotelgabriella":
        "Włochy - Diano Marina",

    "lidosparesort":
        "Włochy - Albissola Marina",

    "campingondina":
        "Włochy - Cervo - Camping Ondina",

    "6149f4deaa509":
        "Hiszpania - Llafranc - plaża",

    "6149f4976134f":
        "Hiszpania - Llafranc - port",

    "porttorre":
        "Hiszpania - Port Torredembarra",

    "615eaf594fe2":
        "Hiszpania - Jávea Golf",

    "rayol":
        "Francja - Plage du Canadel",

    "otport":
        "Francja - Saintes-Maries-de-la-Mer",

    "dagilberto":
        "Grecja - Rodos",

    "664206ddb66f4":
        "Grecja - Kleitoria - plac",

    "6064ac4276104":
        "Bułgaria - Burgas - jezioro",

    "hotelelegance":
        "Bułgaria - Nesebyr",

    "saliste2":
        "Rumunia - Saliste - Piata Junilor",

    "59b196fb5acdb":
        "Węgry - Fedemes",

    "belcekizbeachclub":
        "Turcja - Belcekiz Beach",

    "merlinbeach":
        "Tajlandia - Phuket - Tri-Trang Beach",

    "57053402af5ea":
        "Botswana - Chobe River",

    "nahoonbeach0sw0low":
        "RPA - Nahoon Beach",

    "6690f8f74882c":
        "RPA - Ladysmith Airport",

    "69421e5731fe2":
        "Australia - Darwin Harbour",

    "sunbayulstimate":
        "Portoryko - Sunbay Marina",

    "pdrbridgeweather":
        "Portoryko - Puerto Del Rey",

    "oldsaybrook":
        "USA - Old Saybrook - rybołów",

    "acb92fbd0c3c":
        "USA - Seneca Lake Pier",

    "572100e287461":
        "USA - Bay Head Yacht Club",

    "647220b9d946a":
        "USA - Stone Harbor Yacht Club",

    "62fe39146c821":
        "USA - Stone Harbor Beach South",

    "609ee11fb2084":
        "USA - Stone Harbor - 96th Street",

    "5thavebeach":
        "USA - 5th Avenue Beach",

    "bridgebay":
        "USA - Bridge Bay - Shasta Lake",

    "64543e68da21a":
        "USA - Pine Grove Resort",

    "snowcam1":
        "USA - Lost Lake Woods",

    "63cb127a0a4f9":
        "USA - Royal Mountain",

    "sdwxcam":
        "USA - Stuarts Draft Weather",

    "633f81d3bf9da":
        "USA - Wolf River Resorts",

    "louisvillesailing":
        "USA - Louisville Sailing Club",

    "lakeviewlakecam":
        "USA - Lake View",

    "69c2eaaa29eb3":
        "USA - Wicomico River",

    "rorc":
        "Rileys River Cam",

    "otters":
        "Kamera wydr",

    "cedarcoveresort":
        "Cedar Cove Resort",

    "ozogolfclub":
        "Ozo Golf Club",

    "laurelwoodgreen":
        "Laurelwood Golf - green",

    "laurelwoodview":
        "Laurelwood Golf - panorama",

    "jky47s3rdft73mek111a":
        "USA - Ventura Harbor Entrance",

    "sandpipercovebeach":
        "USA - Sandpiper Cove Beach",

    "60a827ec8277b":
        "Szkocja - Fairlie Coastal Oyster Cam",

    "64a202e285e55":
        "Harmony Grove Village Weather",

    "5bfd8be9978fc":
        "Weather Cam",

    "bukowachata":
        "Polska - Jugów - Góry Sowie",
}


def headers(alias):
    return {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer":
            f"https://www.ipcamlive.com/{alias}",
        "Origin":
            "https://www.ipcamlive.com",
    }


# ============================================================
# POBRANIE STANU KAMERY
# ============================================================

def get_state(alias):

    urls = [
        (
            "https://www.ipcamlive.com/"
            "ajax/getcamerastreamstate.php"
            f"?cameraalias={quote(alias)}"
        ),

        (
            "https://ipcamlive.com/"
            "ajax/getcamerastreamstate.php"
            f"?cameraalias={quote(alias)}"
        ),
    ]

    last_error = None

    for url in urls:

        try:

            r = requests.get(
                url,
                headers=headers(alias),
                timeout=TIMEOUT,
            )

            if r.status_code != 200:
                last_error = (
                    f"HTTP {r.status_code}"
                )
                continue

            data = r.json()

            details = data.get(
                "details"
            )

            if details:
                return data, None

            last_error = (
                "brak details"
            )

        except Exception as e:

            last_error = (
                type(e).__name__
            )

    return None, last_error


# ============================================================
# TEST SEGMENTU
# ============================================================

def test_segment(
    session,
    url,
    alias,
):

    try:

        h = headers(alias)

        h["Range"] = "bytes=0-4095"

        r = session.get(
            url,
            headers=h,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        if r.status_code not in (
            200,
            206,
        ):
            return False

        # Nie pobieramy całego filmu.
        # Wystarczy kawałek segmentu.

        for chunk in r.iter_content(
            chunk_size=2048
        ):
            if chunk:
                return True

        return False

    except Exception:
        return False


# ============================================================
# GŁĘBOKI TEST HLS
# ============================================================

def test_hls(
    session,
    url,
    alias,
    depth=0,
):

    if depth > 4:
        return False, "za dużo poziomów"

    try:

        r = session.get(
            url,
            headers=headers(alias),
            timeout=TIMEOUT,
            allow_redirects=True,
        )

    except Exception as e:

        return (
            False,
            type(e).__name__,
        )

    if r.status_code != 200:

        return (
            False,
            f"HTTP {r.status_code}",
        )

    text = r.text

    if "#EXTM3U" not in text:

        return (
            False,
            "brak #EXTM3U",
        )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # ----------------------------------------
    # MASTER PLAYLIST
    # ----------------------------------------

    if any(
        line.startswith(
            "#EXT-X-STREAM-INF"
        )
        for line in lines
    ):

        children = []

        for i, line in enumerate(lines):

            if not line.startswith(
                "#EXT-X-STREAM-INF"
            ):
                continue

            if i + 1 >= len(lines):
                continue

            child = lines[i + 1]

            if child.startswith("#"):
                continue

            children.append(
                urljoin(
                    r.url,
                    child
                )
            )

        for child in children:

            good, info = test_hls(
                session,
                child,
                alias,
                depth + 1,
            )

            if good:
                return (
                    True,
                    "master + segment OK",
                )

        return (
            False,
            "master bez działającego wariantu",
        )

    # ----------------------------------------
    # MEDIA PLAYLIST
    # ----------------------------------------

    segments = []

    for line in lines:

        if line.startswith("#"):
            continue

        if ".m3u8" in line.lower():
            continue

        segments.append(
            urljoin(
                r.url,
                line
            )
        )

    if not segments:

        return (
            False,
            "M3U8 bez segmentów",
        )

    # Testujemy najnowsze segmenty.

    for segment in segments[-3:]:

        if test_segment(
            session,
            segment,
            alias,
        ):
            return (
                True,
                "segment OK",
            )

    return (
        False,
        "segmenty nie działają",
    )


# ============================================================
# BUDOWANIE MOŻLIWYCH URL
# ============================================================

def build_urls(
    address,
    streamid,
):

    parsed = urlparse(address)

    host = parsed.netloc

    if not host:
        host = (
            address
            .replace("http://", "")
            .replace("https://", "")
            .strip("/")
        )

    base = (
        f"https://{host}"
    )

    return [
        (
            f"{base}/streams/"
            f"{streamid}/stream.m3u8"
        ),

        (
            f"{base}/streams_storage/"
            f"{streamid}/stream.m3u8"
        ),
    ]


# ============================================================
# TEST JEDNEJ KAMERY
# ============================================================

def check_camera(item):

    alias, name = item

    result = {
        "alias": alias,
        "name": name,
        "status": "UNKNOWN",
        "hls": None,
        "resolution": "",
        "fps": "",
        "codec": "",
        "server": "",
        "streamid": "",
        "info": "",
    }

    data, error = get_state(alias)

    if not data:

        result["status"] = "BRAK"
        result["info"] = error or "brak danych"

        return result

    details = (
        data.get("details")
        or {}
    )

    streaminfo = (
        data.get("streaminfo")
        or {}
    )

    streamid = details.get(
        "streamid"
    )

    address = details.get(
        "address"
    )

    available = str(
        details.get(
            "streamavailable",
            ""
        )
    )

    connected = str(
        streaminfo.get(
            "connected",
            ""
        )
    )

    result["streamid"] = (
        streamid or ""
    )

    result["server"] = (
        address or ""
    )

    video = (
        streaminfo.get("video")
        or {}
    )

    width = video.get(
        "width"
    )

    height = video.get(
        "height"
    )

    if width and height:
        result["resolution"] = (
            f"{width}x{height}"
        )

    result["fps"] = str(
        video.get("fps") or ""
    )

    result["codec"] = str(
        video.get("format") or ""
    )

    if (
        available == "0"
        or connected == "0"
    ):
        result["status"] = "OFFLINE"
        result["info"] = (
            "IPCamLive zgłasza offline"
        )

        return result

    if not streamid or not address:

        result["status"] = "BRAK HLS"
        result["info"] = (
            "brak streamid/address"
        )

        return result

    session = requests.Session()

    urls = build_urls(
        address,
        streamid,
    )

    errors = []

    for url in urls:

        good, info = test_hls(
            session,
            url,
            alias,
        )

        if good:

            result["status"] = "ONLINE"
            result["hls"] = url
            result["info"] = info

            return result

        errors.append(
            f"{url} -> {info}"
        )

    result["status"] = "HLS BŁĄD"
    result["info"] = " | ".join(
        errors
    )

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("#" * 90)
    print(
        "TEST KANDYDATÓW IPCAMLIVE"
    )
    print("#" * 90)

    print(
        "Liczba kandydatów:",
        len(CAMERAS)
    )

    print(
        "Równoległych testów:",
        WORKERS
    )

    print()

    results = []

    with (
        concurrent.futures
        .ThreadPoolExecutor(
            max_workers=WORKERS
        )
    ) as executor:

        futures = {
            executor.submit(
                check_camera,
                item,
            ): item
            for item in CAMERAS.items()
        }

        completed = 0

        for future in (
            concurrent.futures
            .as_completed(futures)
        ):

            completed += 1

            try:
                result = future.result()

            except Exception as e:

                alias, name = (
                    futures[future]
                )

                result = {
                    "alias": alias,
                    "name": name,
                    "status": "ERROR",
                    "hls": None,
                    "resolution": "",
                    "fps": "",
                    "codec": "",
                    "server": "",
                    "streamid": "",
                    "info":
                        repr(e),
                }

            results.append(result)

            print(
                f"[{completed:02d}/"
                f"{len(CAMERAS):02d}] "
                f"{result['status']:<9} "
                f"{result['alias']:<25} "
                f"{result['name']}"
            )

    # ========================================================
    # SORTOWANIE
    # ========================================================

    online = [
        x for x in results
        if x["status"] == "ONLINE"
    ]

    offline = [
        x for x in results
        if x["status"] == "OFFLINE"
    ]

    errors = [
        x for x in results
        if x["status"] not in (
            "ONLINE",
            "OFFLINE",
        )
    ]

    online.sort(
        key=lambda x:
            x["name"].lower()
    )

    # ========================================================
    # PODSUMOWANIE
    # ========================================================

    print()
    print("#" * 90)
    print("PODSUMOWANIE")
    print("#" * 90)

    print(
        "ONLINE + działający HLS:",
        len(online)
    )

    print(
        "OFFLINE:",
        len(offline)
    )

    print(
        "BRAK / BŁĘDY:",
        len(errors)
    )

    # ========================================================
    # ONLINE
    # ========================================================

    print()
    print("#" * 90)
    print(
        "DZIAŁAJĄCE KAMERY IPCAMLIVE"
    )
    print("#" * 90)

    for n, cam in enumerate(
        online,
        start=1,
    ):

        print()
        print(
            f"[{n}] {cam['name']}"
        )

        print(
            "Alias:",
            cam["alias"]
        )

        print(
            "Rozdzielczość:",
            cam["resolution"]
            or "?"
        )

        print(
            "FPS:",
            cam["fps"]
            or "?"
        )

        print(
            "Kodek:",
            cam["codec"]
            or "?"
        )

        print(
            "Stream ID:",
            cam["streamid"]
        )

        print(
            "HLS:"
        )

        print(
            cam["hls"]
        )

    # ========================================================
    # GOTOWY FRAGMENT M3U
    # ========================================================

    print()
    print("#" * 90)
    print(
        "GOTOWY FRAGMENT M3U - "
        "TYLKO DZIAŁAJĄCE"
    )
    print("#" * 90)

    print()

    for cam in online:

        safe_name = (
            cam["name"]
            .replace('"', "'")
        )

        print(
            '#EXTINF:-1 '
            'group-title="IPCamLive",'
            f'{safe_name}'
        )

        print(
            cam["hls"]
        )

    # ========================================================
    # ALIASY DO UPDATE_IPCAMLIVE.PY
    # ========================================================

    print()
    print("#" * 90)
    print(
        "ALIASY ONLINE - DO EWENTUALNEGO "
        "DODANIA DO update_ipcamlive.py"
    )
    print("#" * 90)

    print()
    print("CAMERAS = {")

    for cam in online:

        name = (
            cam["name"]
            .replace('"', '\\"')
        )

        alias = cam["alias"]

        print(
            f'    "{name}": ['
        )

        print(
            f'        "{alias}"'
        )

        print(
            "    ],"
        )

    print("}")

    # ========================================================
    # BŁĘDY
    # ========================================================

    if errors:

        print()
        print("#" * 90)
        print(
            "NIEDZIAŁAJĄCE / "
            "NIEROZPOZNANE"
        )
        print("#" * 90)

        for cam in errors:

            print()
            print(
                cam["alias"],
                "-",
                cam["name"]
            )

            print(
                "Status:",
                cam["status"]
            )

            print(
                "Powód:",
                cam["info"]
            )


if __name__ == "__main__":
    main()

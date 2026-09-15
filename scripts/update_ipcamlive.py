import json
import pathlib
import re
import time
import urllib.parse
import urllib.request


PLAYLIST_FILE = pathlib.Path("Kamery-pogodowe.m3u8")


# ============================================================
# KAMERY IPCAMLIVE
#
# "nazwa dokładnie taka jak w M3U": ["alias"]
#
# Przy Svolvær są dwa możliwe aliasy.
# Skrypt spróbuje ustalić, który odpowiada obecnemu strumieniowi.
# ============================================================

CAMERAS = {

    # =========================================================
    # DOTYCHCZASOWE KAMERY
    # =========================================================

    "Krynica Morska - Hotel Kahlberg": [
        "5958e21475225"
    ],

    "Willa Favorita - San Sebastian - Hiszpania": [
        "5f4fbbc0c74cd"
    ],

    "Słowenia - Zamek Ptuj": [
        "ptujcastlecam"
    ],


    # =========================================================
    # NOWE KAMERY IPCAMLIVE
    # =========================================================

    "Anglia - Cotswold Airport": [
        "cotswold"
    ],

    "Anglia - Pagham Beach": [
        "6654f97b9fdf3"
    ],

    "Australia - Darwin Harbour": [
        "69421e5731fe2"
    ],

    "Botswana - Chobe River": [
        "57053402af5ea"
    ],

    "Cedar Cove Resort": [
        "cedarcoveresort"
    ],

    "Chorwacja - Kovacine": [
        "kovacine"
    ],

    "Francja - Saintes-Maries-de-la-Mer": [
        "otport"
    ],

    "Grecja - Rodos": [
        "dagilberto"
    ],

    "Hiszpania - Llafranc - plaża": [
        "6149f4deaa509"
    ],

    "Hiszpania - Llafranc - port": [
        "6149f4976134f"
    ],

    "Hiszpania - Port Torredembarra": [
        "porttorre"
    ],

    "Laurelwood Golf - green": [
        "laurelwoodgreen"
    ],

    "Laurelwood Golf - panorama": [
        "laurelwoodview"
    ],

    "Ozo Golf Club": [
        "ozogolfclub"
    ],

    "Polska - Bolesławiec - panorama": [
        "wiezowieczachod"
    ],

    "Rileys River Cam": [
        "rorc"
    ],

    "RPA - Ladysmith Airport": [
        "6690f8f74882c"
    ],

    "Słowenia - Planina nad Vrhniko": [
        "znpvkamera2"
    ],

    "Turcja - Belcekiz Beach": [
        "belcekizbeachclub"
    ],

    "USA - 5th Avenue Beach": [
        "5thavebeach"
    ],

    "USA - Bay Head Yacht Club": [
        "572100e287461"
    ],

    "USA - Lost Lake Woods": [
        "snowcam1"
    ],

    "USA - Old Saybrook - rybołów": [
        "oldsaybrook"
    ],

    "USA - Pine Grove Resort": [
        "64543e68da21a"
    ],

    "USA - Royal Mountain": [
        "63cb127a0a4f9"
    ],

    "USA - Sandpiper Cove Beach": [
        "sandpipercovebeach"
    ],

    "USA - Seneca Lake Pier": [
        "acb92fbd0c3c"
    ],

    "USA - Stone Harbor Beach South": [
        "62fe39146c821"
    ],

    "USA - Stone Harbor Yacht Club": [
        "647220b9d946a"
    ],

    "USA - Stuarts Draft Weather": [
        "sdwxcam"
    ],

    "USA - Ventura Harbor Entrance": [
        "jky47s3rdft73mek111a"
    ],

    "Weather Cam": [
        "5bfd8be9978fc"
    ],

    "Włochy - Albissola Marina": [
        "lidosparesort"
    ],

    "Włochy - Cervo - Camping Ondina": [
        "campingondina"
    ],

    "Włochy - Diano Marina": [
        "hotelgabriella"
    ],

    "Włochy - Ischia - Maronti": [
        "62da90f20979d"
    ],

    "Włochy - Rimini": [
        "riminieyecom"
    ],
 
}


STATE_SERVERS = [
    "https://ipcamlive.com/player/getcamerastreamstate.php",
    "https://g0.ipcamlive.com/player/getcamerastreamstate.php",
]


def player_url(alias):
    return (
        "https://g0.ipcamlive.com/player/"
        f"player.php?alias={alias}"
    )


def request_json(url, alias):

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Referer": player_url(alias),
        },
    )

    with urllib.request.urlopen(
        req,
        timeout=25
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


def get_camera_state(alias):

    last_error = None

    for endpoint in STATE_SERVERS:

        params = {
            "alias": alias,
            "getstreaminfo": "1",
            "targetdomain": "ipcamlive.com",
            "_": str(int(time.time() * 1000)),
        }

        url = (
            endpoint
            + "?"
            + urllib.parse.urlencode(params)
        )

        try:

            data = request_json(
                url,
                alias
            )

            if "details" in data:
                return data

        except Exception as e:

            last_error = e

    raise RuntimeError(
        "Nie udało się pobrać danych IPCamLive: "
        f"{last_error}"
    )


def test_stream(url, alias):

    try:

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": player_url(alias),
            },
        )

        with urllib.request.urlopen(
            req,
            timeout=20
        ) as response:

            content = response.read(
                4096
            ).decode(
                "utf-8",
                errors="ignore"
            )

            return "#EXTM3U" in content

    except Exception:

        return False


def make_stream_url(data, alias):

    details = data.get("details", {})

    address = details.get("address")
    stream_id = details.get("streamid")

    if not address or not stream_id:

        raise RuntimeError(
            "Brak address lub streamid."
        )

    stream_file = "stream.m3u8"

    try:

        levels = (
            data["streaminfo"]
            ["live"]
            ["levels"]
        )

        if levels:

            stream_file = levels[0].get(
                "url",
                "stream.m3u8"
            ).replace("\\", "/")

    except Exception:

        pass

    address = address.rstrip("/")

    servers = []

    if address.startswith("http://"):

        servers.append(
            "https://"
            + address[len("http://"):]
        )

    servers.append(address)

    candidates = []

    for server in servers:

        candidates.append(
            f"{server}/streams/"
            f"{stream_id}/{stream_file}"
        )

        candidates.append(
            f"{server}/streams_storage/"
            f"{stream_id}/{stream_file}"
        )

    for url in candidates:

        if test_stream(url, alias):

            return {
                "alias": alias,
                "streamid": stream_id,
                "url": url,
            }

    raise RuntimeError(
        "IPCamLive podał streamid, "
        "ale nie znaleziono działającego HLS."
    )


def find_camera_entry(lines, camera_name):

    for i, line in enumerate(lines):

        if (
            line.startswith("#EXTINF")
            and camera_name in line
        ):

            if i + 1 >= len(lines):

                raise RuntimeError(
                    f"Brak adresu pod: {camera_name}"
                )

            return i, lines[i + 1]

    raise RuntimeError(
        f'Nie znaleziono kamery "{camera_name}"'
    )


def extract_streamid(url):

    match = re.search(
        r"/streams(?:_storage)?/([^/]+)/",
        url
    )

    if match:
        return match.group(1)

    return None


def check_alias(alias):

    data = get_camera_state(alias)

    result = make_stream_url(
        data,
        alias
    )

    return result


def update_camera(
    lines,
    camera_name,
    aliases
):

    index, current_url = find_camera_entry(
        lines,
        camera_name
    )

    current_streamid = extract_streamid(
        current_url
    )

    print()
    print("=" * 70)
    print("KAMERA:", camera_name)
    print("OBECNY URL:", current_url)

    if current_streamid:

        print(
            "OBECNY STREAMID:",
            current_streamid
        )

    print("-" * 70)

    working = []

    for alias in aliases:

        print()
        print("Sprawdzam alias:", alias)

        try:

            result = check_alias(alias)

            working.append(result)

            print("  STREAMID:", result["streamid"])
            print("  HLS:", result["url"])

            if (
                current_streamid
                and
                result["streamid"]
                == current_streamid
            ):

                print(
                    "  >>> TEN ALIAS ODPOWIADA "
                    "OBECNEMU STRUMIENIOWI <<<"
                )

        except Exception as e:

            print(
                "  BŁĄD:",
                e
            )

    if not working:

        print()
        print(
            "BRAK DZIAŁAJĄCEGO ALIASU."
        )

        return False

    selected = None

    # Jeśli obecny streamid pasuje do któregoś aliasu,
    # wiemy dokładnie, który alias jest właściwy.

    if current_streamid:

        for result in working:

            if (
                result["streamid"]
                == current_streamid
            ):

                selected = result
                break

    # Jeżeli kamera ma tylko jeden alias,
    # nie ma potrzeby dopasowywania.

    if selected is None and len(aliases) == 1:

        selected = working[0]

    # Przy kilku aliasach (Svolvær):
    # jeśli nie udało się dopasować starego streamid,
    # nie zmieniamy kamery automatycznie.
    # Dzięki temu nie wybierzemy złego widoku.

    if selected is None:

        print()
        print(
            "UWAGA: kamera ma kilka aliasów "
            "i nie udało się ustalić,"
        )

        print(
            "który odpowiada obecnemu wpisowi."
        )

        print(
            "Nie zmieniam tej kamery automatycznie."
        )

        return False

    new_url = selected["url"]

    print()
    print("WYBRANY ALIAS:", selected["alias"])
    print("WYBRANY STREAMID:", selected["streamid"])
    print("NOWY URL:", new_url)

    if current_url == new_url:

        print()
        print("Adres bez zmian.")

        return False

    lines[index + 1] = new_url

    print()
    print(
        ">>> ADRES ZOSTAŁ "
        "ZAKTUALIZOWANY <<<"
    )

    return True


def main():

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    changed = False

    print()
    print("#" * 70)
    print("AUTOMATYCZNA AKTUALIZACJA IPCAMLIVE")
    print("#" * 70)

    for camera_name, aliases in CAMERAS.items():

        try:

            if update_camera(
                lines,
                camera_name,
                aliases
            ):

                changed = True

        except Exception as e:

            print()
            print(
                "BŁĄD KAMERY:",
                camera_name
            )

            print(e)

            # Awaria jednej kamery
            # nie zatrzymuje pozostałych.

            continue

    if changed:

        PLAYLIST_FILE.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8"
        )

        print()
        print("#" * 70)
        print(
            "ZAPISANO ZMIANY "
            "W Kamery-pogodowe.m3u8"
        )
        print("#" * 70)

    else:

        print()
        print("#" * 70)
        print("NIE BYŁO NIC DO ZMIANY")
        print("#" * 70)


if __name__ == "__main__":
    main()

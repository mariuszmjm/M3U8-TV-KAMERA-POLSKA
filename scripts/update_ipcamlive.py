import json
import pathlib
import time
import urllib.parse
import urllib.request


ALIAS = "5958e21475225"
PLAYLIST_FILE = pathlib.Path("Kamery-pogodowe.m3u8")
CAMERA_NAME = "Gniezno - Rynek"

PLAYER_URL = f"https://g0.ipcamlive.com/player/player.php?alias={ALIAS}"

STATE_SERVERS = [
    "https://ipcamlive.com/player/getcamerastreamstate.php",
    "https://g0.ipcamlive.com/player/getcamerastreamstate.php",
]


def request_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Referer": PLAYER_URL,
        },
    )

    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def get_camera_state():
    last_error = None

    for endpoint in STATE_SERVERS:
        params = {
            "alias": ALIAS,
            "getstreaminfo": "1",
            "targetdomain": "ipcamlive.com",
            "_": str(int(time.time() * 1000)),
        }

        url = endpoint + "?" + urllib.parse.urlencode(params)

        try:
            print("Sprawdzam:", endpoint)
            data = request_json(url)

            if "details" in data:
                return data

        except Exception as e:
            last_error = e
            print("Błąd:", e)

    raise RuntimeError(
        f"Nie udało się pobrać informacji IPCamLive: {last_error}"
    )


def test_stream(url):
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": PLAYER_URL,
            },
        )

        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read(2048).decode(
                "utf-8", errors="ignore"
            )

            return "#EXTM3U" in data

    except Exception as e:
        print("Nie działa:", url)
        print("Powód:", e)
        return False


def find_stream(data):
    details = data["details"]

    address = details.get("address")
    stream_id = details.get("streamid")

    if not address or not stream_id:
        raise RuntimeError(
            "IPCamLive nie zwrócił address lub streamid."
        )

    stream_file = "stream.m3u8"

    try:
        levels = data["streaminfo"]["live"]["levels"]

        if levels:
            stream_file = levels[0].get(
                "url",
                "stream.m3u8"
            ).replace("\\", "/")

    except Exception:
        pass

    address = address.rstrip("/")

    addresses = [address]

    if address.startswith("http://"):
        addresses.insert(
            0,
            "https://" + address[len("http://"):]
        )

    candidates = []

    for server in addresses:
        candidates.append(
            f"{server}/streams/{stream_id}/{stream_file}"
        )

        candidates.append(
            f"{server}/streams_storage/{stream_id}/{stream_file}"
        )

    print()
    print("IPCamLive zwrócił:")
    print("serwer:", address)
    print("streamid:", stream_id)
    print()

    for url in candidates:
        print("Testuję:", url)

        if test_stream(url):
            print("DZIAŁA:", url)
            return url

    raise RuntimeError(
        "IPCamLive podał dane kamery, "
        "ale żaden z utworzonych adresów HLS nie odpowiedział."
    )


def update_playlist(stream_url):
    text = PLAYLIST_FILE.read_text(
        encoding="utf-8"
    )

    lines = text.splitlines()

    found = False

    for i, line in enumerate(lines):
        if CAMERA_NAME in line and line.startswith("#EXTINF"):
            if i + 1 >= len(lines):
                raise RuntimeError(
                    "Brak adresu pod wpisem Gniezno."
                )

            old_url = lines[i + 1]

            print()
            print("Stary URL:")
            print(old_url)

            print()
            print("Nowy URL:")
            print(stream_url)

            if old_url == stream_url:
                print()
                print("Adres się nie zmienił.")
                return

            lines[i + 1] = stream_url
            found = True
            break

    if not found:
        raise RuntimeError(
            f'Nie znaleziono wpisu "{CAMERA_NAME}" '
            f'w {PLAYLIST_FILE}'
        )

    PLAYLIST_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )

    print()
    print("Plik M3U8 został zaktualizowany.")


def main():
    data = get_camera_state()
    stream_url = find_stream(data)
    update_playlist(stream_url)


if __name__ == "__main__":
    main()

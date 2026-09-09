from pathlib import Path
import re
from datetime import datetime, timezone


PLAYLIST = Path("Kamery-pogodowe.m3u8")

FORECAST_RE = re.compile(
    r"(https?://streaming\.forecastweather\.gr:8090/"
    r"live/[^/\s?#]+/playlist\.m3u8)"
    r"(?:\?[^\s]*)?",
    re.IGNORECASE,
)

REFRESH_RE = re.compile(
    r"^#FORECASTWEATHER-REFRESH:.*$",
    re.MULTILINE,
)


def main():

    text = PLAYLIST.read_text(
        encoding="utf-8"
    )

    # UTC wystarczy — chodzi tylko o unikalność.
    now = datetime.now(timezone.utc)

    stamp = now.strftime("%Y%m%d%H")

    refresh_comment = (
        f"#FORECASTWEATHER-REFRESH:{stamp}"
    )

    # -----------------------------------------
    # Zmieniamy wszystkie URL ForecastWeather
    # -----------------------------------------

    count = 0

    def replace_url(match):

        nonlocal count

        count += 1

        base_url = match.group(1)

        return (
            f"{base_url}"
            f"?refresh={stamp}"
        )

    new_text = FORECAST_RE.sub(
        replace_url,
        text,
    )

    # -----------------------------------------
    # Zmieniamy komentarz w całym głównym M3U.
    # -----------------------------------------

    if REFRESH_RE.search(new_text):

        new_text = REFRESH_RE.sub(
            refresh_comment,
            new_text,
            count=1,
        )

    else:

        lines = new_text.splitlines()

        if (
            lines
            and lines[0].startswith("#EXTM3U")
        ):

            lines.insert(
                1,
                refresh_comment,
            )

            new_text = "\n".join(lines)

            if text.endswith("\n"):
                new_text += "\n"

        else:

            new_text = (
                refresh_comment
                + "\n"
                + new_text
            )

    print()
    print("#" * 70)
    print(
        "ODŚWIEŻENIE FORECASTWEATHER"
    )
    print("#" * 70)

    print(
        "Znacznik:",
        stamp
    )

    print(
        "Zmienionych adresów:",
        count
    )

    if count == 0:

        print(
            "UWAGA: nie znaleziono "
            "ForecastWeather."
        )

        return

    if new_text == text:

        print(
            "Brak zmian."
        )

        return

    PLAYLIST.write_text(
        new_text,
        encoding="utf-8",
    )

    print(
        "Zaktualizowano cały "
        "Kamery-pogodowe.m3u8"
    )


if __name__ == "__main__":
    main()

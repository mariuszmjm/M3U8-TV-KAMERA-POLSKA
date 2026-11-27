# LG – pilot własnej pogody

Otwórz [odtwarzacz](https://mariuszmjm.github.io/M3U8-TV-KAMERA-POLSKA/test/lg-weather/). Oryginalne LG 2.0 i playlisty pozostają bez zmian.

Własne karty: Chojnice, WARSZAWA - Odolany, Zalewo (WorldCam), Niechorze - widok na latarnię (WebCamera), Praga. Pozostałe kamery zachowują dotychczasowe logo. Współrzędne przybliżone. Ustawienia pilota zapisywane osobno. Karty mają temperaturę, odczuwalną, wilgotność, wiatr, ciśnienie i czas danych. Dane modelowe Open-Meteo, nie pomiar z kamery. Darmowy endpoint tylko do użytku niekomercyjnego; atrybucja CC BY 4.0: https://open-meteo.com/.

Generator: Node.js 22, bez dodatkowych bibliotek. `node test/lg-weather/generate.cjs --test` oraz `node test/lg-weather/generate.cjs`. Workflow co 30 minut, z możliwym opóźnieniem GitHub. Gdy API zawiedzie, generator zachowuje ostatnią kartę z widoczną datą. Odtwarzacz próbuje pobrać dane bezpośrednio, gdy karta nie istnieje lub jest stara. Godzina danych w strefie miejscowości (wszystkie lokalizacje pilota mają tę samą strefę czasową). Brak danych nie jest zastępowany fikcyjną temperaturą.

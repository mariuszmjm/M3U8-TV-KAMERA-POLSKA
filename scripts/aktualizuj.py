#!/usr/bin/env python3
"""TV-Polska.eu -> playlisty M3U, bez pobierania filmów.

Uruchom: python aktualizuj.py --max-channels 12 --max-new 25
Do działania sieciowego wymagany jest internet; GitHub Actions może uruchamiać cyklicznie.
"""
from __future__ import annotations
import argparse
import csv
import html
import json
import logging
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qs, unquote
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

ROOT = 'https://tv-polska.eu'
USER_AGENT = 'OsobistyKatalogTVPolska/1.0 (+niekomercyjna playlista; kontakt przez administratora repozytorium)'
OUT = Path(__file__).parent / 'wyniki'
REGIONS_FILE = Path(__file__).parent / 'regiony.json'
VIDEO_PATH = re.compile(r'/film/([0-9]{3,})[-/]', re.I)
MEDIA_PATH = re.compile(r'\.(?:mp4|m3u8)(?:\?|$)', re.I)
MEDIA_URL = re.compile(r'(?:https?:)?//[^\s"\'<>\\]+?\.(?:mp4|m3u8)(?:\?[^\s"\'<>]*)?', re.I)
TOURISM = re.compile(r'(?i)\b(?:panoram|dron|drohnen|aerial|zamek|pałac|palac|dwor|dwór|muzeum|skansen|zabyt|histori|przyrod|krajobraz|park\b|las\b|jezior|rzek|morze|plaż|plaz|widok|starów|starow|architektur|wyciecz|turyst|szlak|pamiątk|pamiatk|kościo|koscio|twierdz|rynek\b|ogród|ogrod|jezior)')
AVOID = re.compile(r'(?i)sesja rady|posiedzenie|obrady|kampania wyborcz|przetarg|przewodniczącego rady')
LOG = logging.getLogger('tv-polska')


def normalize(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', value.lower()) if unicodedata.category(c) != 'Mn')


def safe_media(raw: str, base: str) -> str:
    if not raw:
        return ''
    raw = html.unescape(raw.strip().replace('\\/', '/'))
    if raw.startswith('//'):
        raw = 'https:' + raw
    url = urljoin(base, raw)
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or not MEDIA_PATH.search(parsed.path):
        return ''
    if parsed.username or parsed.password or parsed.hostname.endswith('.example'):
        return ''
    return url


def extract_movie_links(markup: str, base: str) -> list[dict]:
    soup = BeautifulSoup(markup, 'html.parser')
    out, seen = [], set()
    for a in soup.select('a[href]'):
        link = urljoin(base, a.get('href', ''))
        match = VIDEO_PATH.search(urlsplit(link).path)
        if not match or urlsplit(link).hostname != urlsplit(base).hostname or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        title = a.get_text(' ', strip=True) or a.get('title', '')
        if not title:
            img = a.find('img')
            title = img.get('alt', '') if img else ''
        title = re.sub(r'\s+', ' ', title).strip() or f'Film {match.group(1)}'
        out.append({'id': match.group(1), 'title': title, 'page': link})
    return out


def extract_channels(markup: str, base: str = ROOT) -> list[dict]:
    soup = BeautifulSoup(markup, 'html.parser')
    results, seen = [], set()
    for a in soup.select('a[href]'):
        url = urljoin(base, a.get('href', ''))
        parts = urlsplit(url)
        host = (parts.hostname or '').lower()
        if (not host.endswith('.tv-polska.eu') or host == 'tv-polska.eu'
                or parts.path not in ('', '/') or host in seen):
            continue
        name = re.sub(r'^\s*\d+[.]\s*', '', a.get_text(' ', strip=True))
        if not name:
            continue
        seen.add(host)
        results.append({'slug': host.split('.')[0], 'name': name, 'url': f'https://{host}/'})
    return results


def extract_media_from_html(markup: str, base: str) -> tuple[list[str], list[str]]:
    """Publiczne adresy z HTML; zwraca media i adresy osadzonych odtwarzaczy."""
    soup = BeautifulSoup(markup, 'html.parser')
    candidates, embeds = [], []
    for tag in soup.select('video[src], video[data-src], source[src], a[href], meta[property="og:video"], meta[property="og:video:url"], meta[name="twitter:player:stream"]'):
        val = tag.get('src') or tag.get('data-src') or tag.get('href') or tag.get('content')
        u = safe_media(val or '', base)
        if u: candidates.append(u)
    for script in soup.find_all('script'):
        content = (script.string or script.get_text() or '').replace('\\/', '/')
        for m in MEDIA_URL.findall(content):
            u = safe_media(m, base)
            if u: candidates.append(u)
        if script.get('type') == 'application/ld+json':
            for m in re.findall(r'"contentUrl"\s*:\s*"([^"\\]+)"', content):
                u = safe_media(m, base)
                if u: candidates.append(u)
    for iframe in soup.select('iframe[src], iframe[data-src]'):
        u = urljoin(base, iframe.get('src') or iframe.get('data-src'))
        parts = urlsplit(u)
        if parts.scheme == 'https' and parts.hostname and (parts.hostname.endswith('vimeo.com') or parts.hostname.endswith('tv-polska.eu')):
            embeds.append(u)
    return list(dict.fromkeys(candidates)), list(dict.fromkeys(embeds))


def expiry_time(url: str) -> int | None:
    qs = parse_qs(urlsplit(url).query)
    for key in ('expires', 'expire', 'exp', 'e', 'valid_until'):
        try:
            value = int(qs.get(key, [''])[0])
            if value > 1_000_000_000: return value
        except (ValueError, TypeError):
            pass
    return None


def pick_media(urls: list[str], min_validity_hours: float) -> str:
    now = time.time()
    urls = [u for u in urls if expiry_time(u) is None or expiry_time(u) - now >= min_validity_hours * 3600]
    # MP4 ma pierwszeństwo: użytkownik potwierdził jego odtwarzanie w M3U IPTV Browser.
    return next((u for u in urls if urlsplit(u).path.lower().endswith('.mp4')), '') or (urls[0] if urls else '')


def resolve_with_ytdlp(urls: list[str], min_validity_hours: float) -> str:
    try:
        import yt_dlp
    except ImportError:
        LOG.warning('Brak yt-dlp: pomijam media osadzone (opcjonalna zależność)')
        return ''
    options = {'quiet': True, 'no_warnings': True, 'skip_download': True,
               'noplaylist': True, 'socket_timeout': 12, 'retries': 1,
               'extractor_retries': 1, 'http_headers': {'User-Agent': USER_AGENT}}
    for page in urls[:3]:
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(page, download=False)
            if info is None: continue
            if 'entries' in info: info = next((x for x in info.get('entries', []) if x), {})
            formats = list(info.get('formats') or [])
            direct = info.get('url')
            if direct: formats.append({'url': direct, 'ext': info.get('ext', '')})
            # Preferuj MP4 po HTTP; ignoruj DRM, RTMP i DASH.
            formats = sorted(formats, key=lambda f: (f.get('ext') == 'mp4', f.get('height') or 0), reverse=True)
            choices = []
            for fmt in formats:
                u = safe_media(fmt.get('url') or '', page)
                if u and not fmt.get('has_drm'):
                    choices.append(u)
            found = pick_media(choices, min_validity_hours)
            if found: return found
        except Exception as exc:
            LOG.debug('Odtwarzacz %s: %s', page, str(exc)[:130])
    return ''


def topic_ok(title: str, category: str = '', channel: str = '') -> bool:
    value = normalize(' '.join([title, category, channel]))
    if AVOID.search(value): return False
    return bool(TOURISM.search(value) or any(word in value for word in ['klejnoty kultury', 'skarby przyrody', 'panoramy z drona', 'polska z drona', 'z drona']))


def load_regions() -> tuple[dict, str]:
    data = json.loads(REGIONS_FILE.read_text(encoding='utf-8'))
    index = {}
    for label, items in data['groups'].items():
        for slug in items:
            index[slug] = label
    return index, data['fallback']


def valid_page(url: str, domain: str = 'tv-polska.eu') -> bool:
    p = urlsplit(url)
    host = p.hostname or ''
    return p.scheme == 'https' and (host == domain or host.endswith('.' + domain))


class Client:
    def __init__(self, delay: float = 0.8):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT, 'Accept-Language': 'pl-PL,pl;q=0.9'})
        self.delay = delay
        self.robots = {}
        self.next_time = 0.0

    def allowed(self, url: str) -> bool:
        p = urlsplit(url)
        root = f'{p.scheme}://{p.netloc}'
        if root not in self.robots:
            rp = RobotFileParser()
            try:
                response = self.session.get(root + '/robots.txt', timeout=12)
                if response.status_code == 200:
                    rp.parse(response.text.splitlines())
                    self.robots[root] = rp
                else:
                    self.robots[root] = None
            except requests.RequestException:
                self.robots[root] = None
        rp = self.robots[root]
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    def get(self, url: str) -> str:
        if not valid_page(url):
            raise ValueError('Zablokowany adres spoza domeny TV-Polska.eu')
        if not self.allowed(url):
            raise PermissionError(f'robots.txt nie zezwala na pobranie: {url}')
        seconds = self.next_time - time.monotonic()
        if seconds > 0: time.sleep(seconds)
        self.next_time = time.monotonic() + self.delay
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        if 'html' not in response.headers.get('Content-Type', '').lower():
            raise ValueError('Odpowiedź nie jest HTML')
        return response.text


def save_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    tmp.replace(path)


def title_from_film(html_doc: str, fallback: str) -> str:
    soup = BeautifulSoup(html_doc, 'html.parser')
    h1 = soup.select_one('h1')
    return h1.get_text(' ', strip=True) if h1 else fallback


def is_mp4_or_hls(url: str) -> bool:
    return bool(url and MEDIA_PATH.search(urlsplit(url).path))


def make_playlists(state: dict, outdir: Path, region_names: list[str]):
    rows = [r for r in state.get('items', {}).values() if is_mp4_or_hls(r.get('media', '')) and
            (expiry_time(r['media']) is None or expiry_time(r['media']) > time.time() + 600)]
    order = {name: i for i, name in enumerate(region_names)}
    rows.sort(key=lambda r: (order.get(r['group'], 999), normalize(r['channel']), normalize(r['title'])))
    outdir.mkdir(parents=True, exist_ok=True)
    def build(name: str, subset: list):
        parts = ['#EXTM3U', '# TV-Polska.eu - prywatny katalog linkow; filmy pozostaja na serwerach nadawcow', '# Aktualizacja: ' + datetime.now(timezone.utc).isoformat()]
        for r in subset:
            label = f"{r['channel']} | {r['title']}".replace('\n', ' ').replace('\r', ' ').replace(',', ' - ')
            parts.append(f'#EXTINF:-1 group-title="{r["group"]}",{label}')
            parts.append(r['media'])
        (outdir / name).write_text('\n'.join(parts) + '\n', encoding='utf-8-sig')
    build('tv_polska_wszystkie.m3u8', rows)
    build('tv_polska_turystyka.m3u8', [r for r in rows if r.get('tourism')])
    fields = ['group', 'channel', 'title', 'tourism', 'media', 'page', 'updated']
    with (outdir / 'raport.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in rows: writer.writerow({key: r.get(key, '') for key in fields})
    # Raport diagnostyczny pozwala sprawdzić, którym filmom nie znaleziono stałego MP4.
    missing = [r for r in state.get('items', {}).values() if not r.get('media')]
    with (outdir / 'brak_adresu.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in missing: writer.writerow({key: r.get(key, '') for key in fields})
    return len(rows), sum(r['tourism'] for r in rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description='TV-Polska.eu -> M3U8: 12 grup, MP4/HLS')
    parser.add_argument('--max-channels', type=int, default=25, help='Liczba kanałów przeglądanych na jedno uruchomienie (rotacja)')
    parser.add_argument('--max-pages', type=int, default=2)
    parser.add_argument('--max-new', type=int, default=40, help='Limit nowych/odświeżanych filmów na uruchomienie')
    parser.add_argument('--max-film-per-channel', type=int, default=12)
    parser.add_argument('--refresh-hours', type=float, default=72)
    parser.add_argument('--min-validity-hours', type=float, default=8, help='Pomiń linki krótkotrwałe')
    parser.add_argument('--sleep', type=float, default=0.8)
    parser.add_argument('--no-ytdlp', action='store_true', help='Tylko bezpośrednie media z HTML')
    parser.add_argument('--state', default=str(OUT / 'stan.json'))
    parser.add_argument('--output', default=str(OUT))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    out = Path(args.output)
    path = Path(args.state)
    try:
        state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'items': {}, 'cursor': 0}
        region_index, default_region = load_regions()
        client = Client(delay=args.sleep)
        channels = extract_channels(client.get(ROOT + '/kanaly'))
        if not channels:
            raise RuntimeError('Nie znaleziono kanałów na stronie /kanaly - format strony mógł się zmienić')
        LOG.info('Wykryto %d kanałów. Bieżąca tura: maksymalnie %d.', len(channels), args.max_channels)
        start = state.get('cursor', 0) % len(channels)
        checked, refreshed = 0, 0
        state.setdefault('page_cursors', {})
        for offset in range(min(args.max_channels, len(channels))):
            channel = channels[(start + offset) % len(channels)]
            checked += 1
            slug, name = channel['slug'], channel['name']
            group = region_index.get(slug, default_region)
            LOG.info('Kanał %s: %s', slug, name)
            seen_channel = set()
            # Strona główna kanału: zawsze sprawdzana pod kątem nowości.
            # Archiwum: rotacja stron paginacji między kolejnymi uruchomieniami.
            archive_page = max(2, int(state['page_cursors'].get(slug, 2)))
            page_numbers = [1] + list(range(archive_page, archive_page + max(0, args.max_pages - 1)))
            for page_number in page_numbers:
                page_url = channel['url'] if page_number == 1 else channel['url'] + f'filmy/realizacje/{page_number}'
                try:
                    listing = extract_movie_links(client.get(page_url), channel['url'])
                except (requests.RequestException, ValueError, PermissionError) as exc:
                    LOG.warning('Brak listy %s: %s', page_url, str(exc)[:140]); break
                novel = [r for r in listing if r['id'] not in seen_channel]
                if not novel:
                    if page_number > 1: state['page_cursors'][slug] = 2
                    continue
                seen_channel.update(r['id'] for r in novel)
                if page_number > 1: state['page_cursors'][slug] = page_number + 1
                for item in novel[:args.max_film_per_channel]:
                    old = state['items'].get(item['id'])
                    if old and time.time() - old.get('checked_ts', 0) < args.refresh_hours * 3600 and \
                            (not expiry_time(old.get('media', '')) or expiry_time(old['media']) - time.time() > args.min_validity_hours * 3600):
                        continue
                    if refreshed >= args.max_new: break
                    refreshed += 1
                    try:
                        html_doc = client.get(item['page'])
                        title = title_from_film(html_doc, item['title'])
                        media, embeds = extract_media_from_html(html_doc, item['page'])
                        direct = pick_media(media, args.min_validity_hours)
                        if not direct and not args.no_ytdlp:
                            direct = resolve_with_ytdlp([item['page']] + embeds, args.min_validity_hours)
                        # Nie zastępuj działającego/stabilnego linku na błędny lub pusty.
                        if not direct and old and old.get('media') and (not expiry_time(old['media']) or expiry_time(old['media']) > time.time() + 600):
                            direct = old['media']
                        category = ''
                        state['items'][item['id']] = {
                            'id': item['id'], 'channel': name, 'title': title, 'group': group,
                            'tourism': topic_ok(title, category, name), 'media': direct,
                            'page': item['page'], 'checked_ts': time.time(),
                            'updated': datetime.now(timezone.utc).date().isoformat(),
                        }
                        LOG.info('  %s %s', 'OK' if direct else 'BRAK MP4/HLS', title[:85])
                    except (requests.RequestException, ValueError, PermissionError) as exc:
                        LOG.warning('  Błąd filmu %s: %s', item['id'], str(exc)[:140])
                        continue
                if refreshed >= args.max_new:
                    if page_number > 1: state['page_cursors'][slug] = page_number  # Strona do ponowienia
                    break
            if refreshed >= args.max_new: break
        state['cursor'] = (start + checked) % len(channels)
        state['last_run'] = datetime.now(timezone.utc).isoformat()
        save_json(path, state)
        total, tourism = make_playlists(state, out, list(json.loads(REGIONS_FILE.read_text(encoding='utf-8'))['groups']))
        LOG.info('Zapisano %d pozycji (turystyka %d); przetworzono %d kanałów.', total, tourism, checked)
        return 0
    except Exception:
        LOG.exception('Błąd aktualizatora. Nie nadpisuję ostatnich playlist.')
        return 1


if __name__ == '__main__':
    sys.exit(main())

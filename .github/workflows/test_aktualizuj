import json
import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from aktualizuj import (extract_channels, extract_movie_links, extract_media_from_html,
                       safe_media, pick_media, topic_ok, make_playlists)

class TestPlaylist(unittest.TestCase):
    def test_channels(self):
        h = '<a href="https://szczecin.tv-polska.eu/">164. Szczecin</a><a href="https://drawno.tv-polska.eu/">Drawno</a>'
        found = extract_channels(h)
        self.assertEqual([(x['slug'], x['name']) for x in found], [('szczecin','Szczecin'),('drawno','Drawno')])

    def test_dedupe_movies(self):
        h = '<a href="/film/500089-plac-dawniej">Plac dawniej</a><a href="/film/500089-plac-dawniej">Duplikat</a>'
        self.assertEqual(len(extract_movie_links(h, 'https://szczecin.tv-polska.eu/')), 1)

    def test_video_tag(self):
        h = '<video controls><source src="https://filmy.test.net/public/szczecin.mp4" type="video/mp4"></video>'
        self.assertEqual(extract_media_from_html(h,'https://szczecin.tv-polska.eu/')[0], ['https://filmy.test.net/public/szczecin.mp4'])

    def test_ld_json(self):
        h = '<script type="application/ld+json">{"contentUrl":"https://filmy.test.net/film.m3u8"}</script>'
        self.assertEqual(extract_media_from_html(h,'https://szczecin.tv-polska.eu/')[0], ['https://filmy.test.net/film.m3u8'])

    def test_iframe(self):
        h = '<iframe src="https://player.vimeo.com/video/12345"></iframe>'
        self.assertEqual(extract_media_from_html(h,'https://szczecin.tv-polska.eu/')[1], ['https://player.vimeo.com/video/12345'])

    def test_tourism(self):
        self.assertTrue(topic_ok('Panorama Szczecina z drona'))
        self.assertFalse(topic_ok('Sesja Rady Miasta w Drawnie'))

    def test_reject_bad_media(self):
        self.assertEqual(safe_media('javascript:alert(1)', 'https://a.tv-polska.eu/'), '')
        self.assertEqual(safe_media('https://evil.example/video.mp4', 'https://a.tv-polska.eu/'), '')
        self.assertEqual(safe_media('https://a.pl/video.mpd', 'https://a.tv-polska.eu/'), '')

    def test_playlist_groups(self):
        with TemporaryDirectory() as temp:
            state = {'items': {'500089': {'group': 'A', 'channel':'Szczecin','title':'Widok',
                      'tourism':True,'media':'https://video.test.net/vid.mp4',
                      'page':'https://szczecin.tv-polska.eu/film/500089-vid','updated':'2026-11-24'}}}
            total, tourism = make_playlists(state, Path(temp), ['A'])
            self.assertEqual((total,tourism),(1,1))
            data = (Path(temp)/'tv_polska_turystyka.m3u8').read_text(encoding='utf-8-sig')
            self.assertIn('group-title="A"',data)
            self.assertIn('https://video.test.net/vid.mp4',data)
            self.assertIn('Szczecin | Widok',data)

if __name__ == '__main__': unittest.main()

class TestWorkflow(unittest.TestCase):
    def test_full_flow_offline(self):
        import aktualizuj
        html_map = {
            'https://tv-polska.eu/kanaly': '''<a href="https://szczecin.tv-polska.eu/">Szczecin</a>
            <a href="https://drawno.tv-polska.eu/">Drawno</a>''',
            'https://szczecin.tv-polska.eu/': '''<a href="/film/500089-plac-holdu">Plac Hołdu Pruskiego - historia Szczecina</a>''',
            'https://szczecin.tv-polska.eu/film/500089-plac-holdu': '''<h1>Plac Hołdu Pruskiego – historia Szczecina</h1>
              <video><source src="https://media.test.net/szczecin.mp4"></video>''',
            'https://drawno.tv-polska.eu/': '''<a href="/film/500090-park">Park Drawieński z drona</a>''',
            'https://drawno.tv-polska.eu/film/500090-park': '''<h1>Park Drawieński z drona</h1>
              <video src="https://media.test.net/drawno.mp4"></video>''',
        }
        def fake_get(self, url):
            return html_map[url]
        with TemporaryDirectory() as tmp, patch.object(aktualizuj.Client, 'get', fake_get):
            out = Path(tmp)
            code = aktualizuj.main(['--max-channels','2','--max-pages','1','--max-new','5',
                '--no-ytdlp','--state',str(out/'stan.json'),'--output',str(out)])
            self.assertEqual(code, 0)
            whole = (out/'tv_polska_wszystkie.m3u8').read_text(encoding='utf-8-sig')
            tour = (out/'tv_polska_turystyka.m3u8').read_text(encoding='utf-8-sig')
            self.assertEqual(whole.count('#EXTINF'),2)
            self.assertIn('02 Pomorze Zachodnie - Szczecin i okolice',whole)
            self.assertIn('03 Pomorze Zachodnie - pojezierza',whole)
            self.assertIn('Park Drawieński z drona',tour)
            self.assertEqual(json.loads((out/'stan.json').read_text())['cursor'],0)

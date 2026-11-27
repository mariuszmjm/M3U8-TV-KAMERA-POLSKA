"""Build a conservative camera -> locality registry from GeoNames (CC BY 4.0).
No location is inferred from a stream number or a TV channel.
"""
import hashlib, io, json, re, sys, unicodedata, urllib.request, zipfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAYLIST = HERE.parents[1] / 'Kamery-pogodowe.m3u8'
OUT = HERE / 'cards' / 'locations.json'
POLISH = {'Miasta','Jeziora i inne miejsca','Kościoły','Góry, stoki narciarskie','Plaże','Peregrinus-PL'}
SKIP = {'TV','Telewizja Polska','EXPLORE.ORG - Afryka i nie tylko'}
COUNTRIES = {'polska':'PL','hiszpania':'ES','czechy':'CZ','niemcy':'DE','francja':'FR','wlochy':'IT','anglia':'GB','szkocja':'GB','wielka brytania':'GB','usa':'US','kanada':'CA','australia':'AU','rosja':'RU','brazylia':'BR','chorwacja':'HR','wegry':'HU','gruzja':'GE','kirgistan':'KG','kazachstan':'KZ','slowenia':'SI','slowacja':'SK','rumunia':'RO','macedonia polnocna':'MK','grecja':'GR','turcja':'TR','rpa':'ZA','botswana':'BW','bulgaria':'BG','portoryko':'PR','japonia':'JP','korea poludniowa':'KR','chiny':'CN','tajlandia':'TH','norwegia':'NO','austria':'AT','szwajcaria':'CH','belgia':'BE','holandia':'NL','portugalia':'PT','izrael':'IL','nowa zelandia':'NZ','ukraina':'UA','litwa':'LT','lotwa':'LV','estonia':'EE','finlandia':'FI','szwecja':'SE','dania':'DK','islandia':'IS','irlandia':'IE','andora':'AD','cypr':'CY','malta':'MT','serbia':'RS','czarnogora':'ME','albania':'AL'}
STOP = {'rynek','centrum','panorama','port','marina','plaza','beach','church','hotel','park','kamera','kamery','widok','stacja','most','plac','zamek','nowa','stara','gora','gory','las','pole','rzeka','jezioro','wyciag','live','central','snow','street','public','court','airport','polska','hiszpania'}
# Exact known spelling or landmark exceptions; town coordinates, not camera GPS.
OVERRIDES = {
 ('Miasta ze świata','Praga'):('Praga',50.075,14.438,'CZ'),
 ('Kamery Streamway','Wieża Eifla'):('Paryż',48.8584,2.2945,'FR'),
 ('Miasta','WIDOK NA PLAC ZAMKOWY W WARSZAWIE'):('Warszawa',52.247,21.014,'PL'),
 ('Miasta','RYNEK STAREGO MIASTA W WARSZAWIE'):('Warszawa',52.249,21.012,'PL'),
 ('Miasta','Panorama Krakowa'):('Kraków',50.061,19.938,'PL'),
 ('Miasta','Plac Przyjaciół Sopotu'):('Sopot',54.444,18.567,'PL'),
 ('Miasta','WARSZAWA - Odolany'):('Warszawa – Odolany',52.222,20.935,'PL'),
}
def norm(s):
    s=unicodedata.normalize('NFKD',s.casefold()).replace('ł','l')
    return ' '.join(re.sub(r'[\W_]+',' ',''.join(c for c in s if not unicodedata.combining(c))).split())

def entries(text):
    result=[]
    for line in text.splitlines():
        line=line.strip()
        if not line.startswith('#EXTINF:'): continue
        quoted=False
        for i,c in enumerate(line):
            if c=='"': quoted=not quoted
            elif c==',' and not quoted: break
        else: continue
        name=line[i+1:].strip()
        group=re.search(r'group-title="([^"]*)"',line[:i],re.I)
        result.append((group.group(1) if group and group.group(1) else 'Bez kategorii',name or 'Kamera'))
    return sorted(set(result))

def download(name):
    req=urllib.request.Request('https://download.geonames.org/export/dump/'+name+'.zip',headers={'User-Agent':'LG-camera-weather/1.0'})
    with urllib.request.urlopen(req,timeout=45) as r:
        data=r.read(70_000_001)
    if len(data)>70_000_000: raise ValueError('GeoNames file too large')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        with z.open(name+'.txt') as f:
            for line in f:
                yield line.decode('utf-8').rstrip('\r\n').split('\t')

def load_index():
    index=defaultdict(dict)
    for dataset in ('cities500','PL'):
        for p in download(dataset):
            if len(p)<19 or p[6]!='P' or p[7] in {'PPLH','PPLQ','PPLW','PPLX'}: continue
            country=p[8]
            place=(p[0],p[1],float(p[4]),float(p[5]),country,int(p[14] or 0))
            names=[p[1],p[2]]
            # Only populated places, and avoid obscure historical alternate names for Polish towns.
            if country!='PL': names+=p[3].split(',')
            for name in names:
                k=norm(name)
                if len(k)>=3 and k not in STOP:
                    index[k][p[0]]=place
    return index

def choose(candidates,country,exact):
    rows=[p for p in candidates.values() if not country or p[4]==country]
    if not rows: return None
    rows.sort(key=lambda p:p[5],reverse=True)
    # Same-name close localities do not create a meaningful weather ambiguity.
    if len(rows)>1:
        a,b=rows[:2]
        close=all(abs(a[2]-p[2])<.08 and abs(a[3]-p[3])<.12 for p in rows[1:])
        if not close and not (a[5]>=10000 and a[5]>=10*max(1,b[5])): return None
    if not country and not exact and rows[0][5]<50000: return None
    return rows[0]

def resolve(group,name,index):
    if group in SKIP or not name or name.isdigit(): return None
    if (group,name) in OVERRIDES:
        title,lat,lon,cc=OVERRIDES[group,name]
        return ('manual-'+hashlib.sha1((title+cc).encode()).hexdigest()[:12],title,lat,lon,cc,0)
    country='PL' if group in POLISH else 'ES' if group=='Hiszpania' else None
    parts=[x.strip() for x in re.split(r'\s+[-–—]\s+',name) if x.strip()]
    if len(parts)>1 and norm(parts[0]) in COUNTRIES:
        country=COUNTRIES[norm(parts.pop(0))]
    # Spanish titles frequently start with province, then the actual municipality.
    if group=='Hiszpania' and len(parts)>1 and norm(parts[0]) in {'alicante','teruel','huesca','zaragoza','valencia','castellon','malaga','granada','almeria','cadiz','murcia'}:
        parts.pop(0)
    title=norm(' '.join(parts))
    title=re.sub(r'^(?:kamera(?: internetowa)?(?: na)?|marina)\s+','',title)
    if not title: return None
    # Prefer complete locality names, then a leading locality (longest first).
    for key in [title]+[' '.join(title.split()[:i]) for i in range(min(6,len(title.split())-1),0,-1)]:
        if key not in index: continue
        if key!=title and not country and len(key.split())==1 and len(key)<5: continue
        p=choose(index[key],country,key==title)
        if p: return p
        # Ambiguous leading locality must not fall through to a shorter name.
        if any(not country or p[4]==country for p in index[key].values()): return None
    # A clearly separated place name in titles such as "Zamek - Ptuj".
    for part in parts[1:]:
        key=norm(part)
        if key in index:
            p=choose(index[key],country,True)
            if p: return p
    return None

def build():
    e=entries(PLAYLIST.read_text(encoding='utf-8-sig'))
    signature=hashlib.sha256(json.dumps(e,ensure_ascii=False).encode()).hexdigest()
    if OUT.exists():
        old=json.loads(OUT.read_text(encoding='utf-8'))
        if old.get('signature')==signature and old.get('version')==1:
            print('Registry unchanged:',len(old['cameras']),'mapped')
            return
    index=load_index()
    locations,cameras,unresolved={}, {}, []
    for group,name in e:
        p=resolve(group,name,index)
        if not p:
            if group not in SKIP: unresolved.append([group,name])
            continue
        gid,title,lat,lon,cc,_=p
        ident='geo-'+gid
        locations[ident]={'id':ident,'name':title,'lat':round(lat,4),'lon':round(lon,4),'country':cc}
        cameras[group+'\x1f'+name]=ident
    result={'version':1,'signature':signature,'source':'GeoNames CC BY 4.0 / manual overrides','locations':locations,'cameras':cameras,'unresolved':unresolved,'unique_entries':len(e)}
    OUT.parent.mkdir(exist_ok=True)
    tmp=OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    tmp.replace(OUT)
    print('Registry:',len(cameras),'mapped,',len(locations),'localities,',len(unresolved),'unresolved; TV and numbered Explore entries excluded.')

def test():
    ix={'warszawa':{'1':('1','Warszawa',52.23,21.01,'PL',1700000)},'gdansk':{'2':('2','Gdańsk',54.35,18.65,'PL',460000)},'springfield':{'3':('3','Springfield',1,1,'US',10000),'4':('4','Springfield',2,2,'US',9000)}}
    assert entries('#EXTINF:-1 group-title="Góry, stoki narciarskie", Test\nurl')==[('Góry, stoki narciarskie','Test')]
    assert resolve('Miasta','Gdańsk - widok',ix)[0]=='2'
    assert resolve('Miasta ze świata','Praga',ix)[4]=='CZ'
    assert resolve('IPCamLive','USA - Springfield',ix) is None
    assert resolve('EXPLORE.ORG - Afryka i nie tylko','1',ix) is None
    assert resolve('Telewizja Polska','Warszawa',ix) is None
    assert resolve('Miasta','Warszawa - Praga',ix)[4]=='PL'
    print('Registry tests OK')

if __name__=='__main__':
    test() if '--test' in sys.argv else build()

"""Real data services (only Python standard library). Each function raises on network failure; the app falls back to saved data.
Sources: Open-Meteo (forecast, geocoding, elevation, GloFAS river discharge), USGS (earthquakes),
OpenStreetMap (map tiles + Overpass places), Google News RSS (news from publishers)."""
import json, urllib.request, urllib.parse, math, datetime, base64, email.utils, statistics
import xml.etree.ElementTree as ET
UA = {'User-Agent': 'RAAH-CollegeProject/1.0 (student disaster-safety project)'}


def get(url, data=None, timeout=20, raw=False):
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=timeout) as r: b = r.read()
    return b if raw else json.loads(b.decode('utf-8'))


def q(**k): return urllib.parse.urlencode(k)
def n0(v): return v if v is not None else 0


def geocode(name, india=True):
    p = dict(name=name, count=10, language='en', format='json')
    if india: p['countryCode'] = 'IN'
    r = get('https://geocoding-api.open-meteo.com/v1/search?' + q(**p)).get('results') or []
    return [dict(name=x['name'], admin=x.get('admin1', ''), country=x.get('country', ''), lat=x['latitude'], lon=x['longitude'], elev=x.get('elevation'), pop=x.get('population') or 0) for x in r]


def weather(lat, lon):
    j = get('https://api.open-meteo.com/v1/forecast?' + q(latitude=lat, longitude=lon, timezone='auto', past_days=7, forecast_days=7, hourly='precipitation',
        current='temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_gusts_10m,surface_pressure',
        daily='weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max'))
    c, D, H = j['current'], j['daily'], j['hourly']; ti = D['time'].index(c['time'][:10])
    r7 = sum(n0(v) for v in D['precipitation_sum'][max(0, ti - 7):ti])
    try: hi = H['time'].index(c['time'][:13] + ':00'); r24 = sum(n0(v) for v in H['precipitation'][max(0, hi - 23):hi + 1])
    except ValueError: r24 = n0(D['precipitation_sum'][ti])
    days = [dict(date=D['time'][k], code=n0(D['weather_code'][k]), tmax=n0(D['temperature_2m_max'][k]), tmin=n0(D['temperature_2m_min'][k]), rain=n0(D['precipitation_sum'][k]),
                 prob=n0(D['precipitation_probability_max'][k]), wind=n0(D['wind_speed_10m_max'][k]), gust=n0(D['wind_gusts_10m_max'][k])) for k in range(ti, min(ti + 7, len(D['time'])))]
    now = dict(time=c['time'], temp=c['temperature_2m'], feels=c['apparent_temperature'], rh=c['relative_humidity_2m'], code=n0(c['weather_code']), wind=c['wind_speed_10m'], gust=c['wind_gusts_10m'], pres=c['surface_pressure'], rain=n0(c['precipitation']))
    return dict(now=now, rain7=r7, rain24=r24, daily=days)


def river(lat, lon):  # GloFAS river discharge (m3/s): last 30 days + 7-day forecast; None if no river modelled here
    d = get('https://flood-api.open-meteo.com/v1/flood?' + q(latitude=lat, longitude=lon, daily='river_discharge', past_days=30, forecast_days=7))['daily']
    return dict(time=d['time'], dis=d['river_discharge']) if any(v is not None for v in d['river_discharge']) else None


def terrain(lat, lon):  # real elevation at centre + 4 points ~3 km away -> steepest slope
    d = 0.03; la = [lat, lat + d, lat - d, lat, lat]; lo = [lon, lon, lon, lon + d, lon - d]
    e = get('https://api.open-meteo.com/v1/elevation?' + q(latitude=','.join(map(str, la)), longitude=','.join(map(str, lo))))['elevation']
    dist = [3330, 3330, 3330 * math.cos(math.radians(lat)), 3330 * math.cos(math.radians(lat))]
    return dict(elev=e[0], slope=round(max(math.degrees(math.atan(abs(e[i + 1] - e[0]) / dist[i])) for i in range(4)), 1))


def quakes(lat, lon):  # USGS, last 30 days, within 300 km, M2.5+
    s = (datetime.datetime.utcnow() - datetime.timedelta(days=30)).date().isoformat()
    j = get('https://earthquake.usgs.gov/fdsnws/event/1/query?' + q(format='geojson', latitude=lat, longitude=lon, maxradiuskm=300, minmagnitude=2.5, starttime=s, orderby='time', limit=30))
    return [dict(mag=f['properties']['mag'] or 0, place=f['properties']['place'], time=f['properties']['time']) for f in j['features']]


def hav(a, b, c, d):
    p = math.pi / 180; x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def places(lat, lon, r=7000):  # real hospitals / police / fire stations / shelters from OpenStreetMap
    a = f'(around:{r},{lat},{lon})'
    qq = f'[out:json][timeout:25];(nwr["amenity"="hospital"]{a};nwr["amenity"="police"]{a};nwr["amenity"="fire_station"]{a};nwr["amenity"="shelter"]{a};nwr["social_facility"="shelter"]{a};nwr["emergency"="assembly_point"]{a};);out center 150;'
    out, seen = [], set()
    for e in get('https://overpass-api.de/api/interpreter', data=q(data=qq).encode(), timeout=40)['elements']:
        t = e.get('tags', {}); la = e.get('lat') or (e.get('center') or {}).get('lat'); lo = e.get('lon') or (e.get('center') or {}).get('lon')
        if la is None: continue
        kind = 'Hospital' if t.get('amenity') == 'hospital' else 'Police' if t.get('amenity') == 'police' else 'Fire station' if t.get('amenity') == 'fire_station' else 'Shelter / assembly point'
        nm = t.get('name') or kind
        if (nm, kind) in seen: continue
        seen.add((nm, kind)); out.append(dict(kind=kind, name=nm, lat=la, lon=lo, dist=round(hav(lat, lon, la, lo), 1)))
    out.sort(key=lambda x: x['dist']); res = []
    for k in ('Hospital', 'Police', 'Fire station', 'Shelter / assembly point'): res += [x for x in out if x['kind'] == k][:6]
    return res


def project(lat, lon, z):
    n = 2 ** z * 256; return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def tiles(lat, lon, z=13):  # 3x3 OpenStreetMap tiles around the point (PNG as base64 for Tk PhotoImage)
    px, py = project(lat, lon, z); tx, ty = int(px // 256), int(py // 256); t = {}
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1): t[f'{tx + dx},{ty + dy}'] = base64.b64encode(get(f'https://tile.openstreetmap.org/{z}/{tx + dx}/{ty + dy}.png', raw=True)).decode()
    return dict(z=z, px=px, py=py, t=t)


def parse_news(xml):
    out = []
    for it in ET.fromstring(xml).iter('item'):
        src = it.find('source'); title = (it.findtext('title') or '').strip(); sname = src.text if src is not None else ''
        if sname and title.endswith(' - ' + sname): title = title[:-len(sname) - 3]
        try: ts = email.utils.parsedate_to_datetime(it.findtext('pubDate')).astimezone(datetime.timezone.utc).isoformat()
        except Exception: ts = ''
        out.append(dict(title=title, link=it.findtext('link') or '', source=sname, ts=ts))
    return out


SITES = {'All sources': '', 'India Today': 'indiatoday.in', 'The Hindu': 'thehindu.com', 'NDTV': 'ndtv.com', 'Indian Express': 'indianexpress.com', 'Times of India': 'timesofindia.indiatimes.com', 'News18': 'news18.com'}
TOPIC = '(flood OR cyclone OR "heavy rain" OR landslide OR earthquake OR "weather alert" OR "fire accident" OR "relief camp")'


def news(place, source='All sources'):
    qq = f'"{place}" {TOPIC}' if place else f'India {TOPIC}'
    if SITES.get(source): qq += f' site:{SITES[source]}'
    return parse_news(get('https://news.google.com/rss/search?' + q(q=qq + ' when:7d', hl='en-IN', gl='IN', ceid='IN:en'), raw=True))[:15]


# ---------- real road routing + terrain along route ----------
import os


def decode_poly(s, f=5):
    pts, i, la, lo = [], 0, 0, 0
    while i < len(s):
        for k in (0, 1):
            sh = r = 0
            while True:
                b = ord(s[i]) - 63; i += 1; r |= (b & 31) << sh; sh += 5
                if b < 32: break
            d = ~(r >> 1) if r & 1 else r >> 1
            if k == 0: la += d
            else: lo += d
        pts.append((la / 10 ** f, lo / 10 ** f))
    return pts


def routes(a, b, c, d):
    """Real driving routes (alternatives). Uses Google Directions API if GOOGLE_MAPS_API_KEY env var is set, otherwise free OSRM (OpenStreetMap data)."""
    key = os.environ.get('GOOGLE_MAPS_API_KEY')
    if key:
        try:
            j = get('https://maps.googleapis.com/maps/api/directions/json?' + q(origin=f'{a},{b}', destination=f'{c},{d}', alternatives='true', key=key))
            if j.get('routes'): return 'Google Maps Directions API', [dict(km=sum(l['distance']['value'] for l in r['legs']) / 1000, min=sum(l['duration']['value'] for l in r['legs']) / 60, pts=decode_poly(r['overview_polyline']['points'])) for r in j['routes']]
        except Exception: pass
    j = get(f'https://router.project-osrm.org/route/v1/driving/{b},{a};{d},{c}?' + q(overview='full', geometries='polyline', alternatives='true'))
    return 'OSRM routing (OpenStreetMap road data)', [dict(km=r['distance'] / 1000, min=r['duration'] / 60, pts=decode_poly(r['geometry'])) for r in j['routes']]


def elevations(pts):
    return get('https://api.open-meteo.com/v1/elevation?' + q(latitude=','.join(f'{p[0]:.5f}' for p in pts), longitude=','.join(f'{p[1]:.5f}' for p in pts)))['elevation']


def fit_tiles(lats, lons, w=340, h=300, pad=30):
    for z in range(16, 3, -1):
        P = [project(a, b, z) for a, b in zip(lats, lons)]; xs = [p[0] for p in P]; ys = [p[1] for p in P]
        if max(xs) - min(xs) <= w - 2 * pad and max(ys) - min(ys) <= h - 2 * pad: break
    left, top = (max(xs) + min(xs)) / 2 - w / 2, (max(ys) + min(ys)) / 2 - h / 2; t = {}
    for tx in range(int(left // 256), int((left + w) // 256) + 1):
        for ty in range(int(top // 256), int((top + h) // 256) + 1): t[f'{tx},{ty}'] = base64.b64encode(get(f'https://tile.openstreetmap.org/{z}/{tx % 2 ** z}/{ty}.png', raw=True)).decode()
    return dict(z=z, left=left, top=top, t=t)


def gmaps_url(a, b, c, d): return f'https://www.google.com/maps/dir/?api=1&origin={a},{b}&destination={c},{d}&travelmode=driving'

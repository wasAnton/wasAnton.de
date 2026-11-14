#!/usr/bin/env python3
"""Schreibt die Fahrplandaten: Straßenbahn und (gepackt) Busse -> index.html.
Aufruf: python3 build.py VAGFR.zip   (neue Zip von der VAG, wenn der Fahrplan abläuft)"""
import base64, csv, gzip, io, json, math, re, sys, zipfile
from collections import defaultdict
from datetime import date, timedelta

zf = zipfile.ZipFile(sys.argv[1] if len(sys.argv) > 1 else 'VAGFR.zip')
rows = lambda n: csv.DictReader(io.TextIOWrapper(zf.open(n), encoding='utf-8-sig'))
secs = lambda s: sum(int(x) * m for x, m in zip(s.split(':'), (3600, 60, 1)))

def kind_of(t):  # T = Straßenbahn, B = Bus, sonst None
    t = int(t)
    if t == 0 or 900 <= t < 1000: return 'T'
    if t == 3 or 700 <= t < 900: return 'B'

routes = [r for r in rows('routes.txt') if kind_of(r['route_type'])]
rix = {r['route_id']: i for i, r in enumerate(routes)}
kind = {r['route_id']: kind_of(r['route_type']) for r in routes}
trips = {t['trip_id']: t for t in rows('trips.txt') if t['route_id'] in rix}
stops = {s['stop_id']: s for s in rows('stops.txt')}
st = defaultdict(list)
for r in rows('stop_times.txt'):
    if r['trip_id'] in trips:
        st[r['trip_id']].append((int(r['stop_sequence']), r['stop_id'], r['departure_time'] or r['arrival_time']))

sids = sorted({t['service_id'] for t in trips.values()})
six = {s: i for i, s in enumerate(sids)}
heads, hix = [], {}
nm = lambda sid: re.sub(r'^Freiburg, ', '', stops[sid]['stop_name']).strip()
gkey = lambda sid: stops[sid]['parent_station'] or stops[sid]['stop_name']  # alle Steige einer Haltestelle
ll = lambda sid: (float(stops[sid]['stop_lat']), float(stops[sid]['stop_lon']))

plat = defaultdict(lambda: {'d': [], 'x': 0.0, 'y': 0.0})
for tid, lst in st.items():
    lst.sort()
    t = trips[tid]; kd = kind[t['route_id']]
    h = t.get('trip_headsign') or nm(lst[-1][1])
    if h not in hix:
        hix[h] = len(heads); heads.append(h)
    for i in range(len(lst) - 1):  # Endhaltestelle hat keine Abfahrt
        sid = lst[i][1]
        p = plat[(sid, kd)]
        p['d'].append((secs(lst[i][2]), six[t['service_id']], rix[t['route_id']], hix[h]))
        (a, o), (b, q) = ll(sid), ll(lst[i + 1][1])
        dy, dx = b - a, (q - o) * math.cos(math.radians(a))
        n = math.hypot(dx, dy) or 1
        p['x'] += dx / n; p['y'] += dy / n

byname = defaultdict(list)
for sid, kd in plat: byname[(kd, gkey(sid))].append(sid)
G = {'T': [], 'B': []}
for (kd, key), ids in sorted(byname.items()):
    name = nm(key) if key in stops else nm(ids[0])
    ps = []
    for sid in ids:
        p = plat[(sid, kd)]; p['d'].sort()
        ps.append([round(math.degrees(math.atan2(p['x'], p['y'])) % 360), [v for d in p['d'] for v in d]])
    G[kd].append([name, round(sum(ll(i)[0] for i in ids) / len(ids), 5), round(sum(ll(i)[1] for i in ids) / len(ids), 5), ps])

cal = {c['service_id']: c for c in rows('calendar.txt') if c['service_id'] in six}
exc = defaultdict(lambda: {'1': set(), '2': set()})
for e in rows('calendar_dates.txt'):
    if e['service_id'] in six: exc[e['date']][e['exception_type']].add(e['service_id'])
first = max(min(c['start_date'] for c in cal.values()), (date.today() - timedelta(days=2)).strftime('%Y%m%d'))
last = max(c['end_date'] for c in cal.values())
d = date(int(first[:4]), int(first[4:6]), int(first[6:]))
svc = {}
while d.strftime('%Y%m%d') <= last:
    ymd, wd = d.strftime('%Y%m%d'), d.strftime('%A').lower()
    on = {s for s, c in cal.items() if c[wd] == '1' and c['start_date'] <= ymd <= c['end_date']}
    on = (on | exc[ymd]['1']) - exc[ymd]['2']
    svc[ymd] = sorted(six[s] for s in on)
    d += timedelta(days=1)

dump = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':'))
data = {'routes': [[r['route_short_name'], r['route_color'] or '17211d', r['route_text_color'] or 'ffffff'] for r in routes],
        'heads': heads, 'svc': svc, 'g': G['T']}
html = open('index.html', encoding='utf-8').read()
html = re.sub(r'/\*DATA_START\*/.*?/\*DATA_END\*/', lambda m: '/*DATA_START*/const DATA=' + dump(data) + ';/*DATA_END*/', html, flags=re.S)
busz = base64.b64encode(gzip.compress(dump(G['B']).encode('utf-8'), 9, mtime=0)).decode()
html = re.sub(r'/\*BUS_START\*/.*?/\*BUS_END\*/', lambda m: '/*BUS_START*/const BUSZ="' + busz + '";/*BUS_END*/', html, flags=re.S)
open('index.html', 'w', encoding='utf-8').write(html)
print(f"{len(G['T'])} Tram-Haltestellen, {len(G['B'])} Bus-Haltestellen, {len(trips)} Fahrten, Fahrplan bis {last}")
print(f"index.html {len(html)//1024} KB (davon Busdaten gepackt {len(busz)//1024} KB)")

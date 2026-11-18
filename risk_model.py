"""RAAH risk model driven by REAL forecast data. Pure Python (no GUI). Indicative index, NOT an official warning.
Each factor = (label, max_points, fraction 0-1 or None if data unavailable, input text). Missing factors are left out and the rest re-scaled."""
import statistics


def cl(x): return max(0.0, min(1.0, x))
def lvl(s): return 'Low' if s < 35 else 'Moderate' if s < 65 else 'High'


def flood_ratio(fl, date):
    if not fl or date not in fl['time']: return None
    v = fl['dis'][fl['time'].index(date)]; today = fl['time'][-7] if len(fl['time']) > 7 else fl['time'][0]
    past = [x for t, x in zip(fl['time'], fl['dis']) if t < today and x is not None]
    return None if v is None or not past or statistics.median(past) <= 0 else v / statistics.median(past)


def hazards(env, i, ctx=None):
    d = env['daily'][i]; T = env.get('terrain') or {}; elev = T.get('elev', env['place'].get('elev')); sl = T.get('slope')
    r7 = env['rain7'] + sum(x['rain'] for x in env['daily'][:i]); ratio = flood_ratio(env.get('flood'), d['date']); Q = env.get('quakes')
    nq = len(Q) if Q is not None else None; mq = max([x['mag'] for x in Q], default=0) if Q is not None else None
    H = {
        'Flood': [('Forecast rain that day', 30, cl(d['rain'] / 120), f"{d['rain']:.0f} mm"), ('Chance of rain', 10, cl(d['prob'] / 100), f"{d['prob']}%"),
                  ('Wet ground (past 7 days + forecast)', 15, cl(r7 / 200), f'{r7:.0f} mm'), ('River flow vs recent normal (GloFAS)', 25, None if ratio is None else cl((ratio - 1) / 3), 'n/a' if ratio is None else f'{ratio:.1f}x'),
                  ('Low-lying land', 20, None if elev is None else cl(1 - elev / 100), 'n/a' if elev is None else f'{elev:.0f} m')],
        'Storm': [('Wind gusts', 40, cl((d['gust'] - 30) / 90), f"{d['gust']:.0f} km/h"), ('Sustained wind', 20, cl(d['wind'] / 80), f"{d['wind']:.0f} km/h"),
                  ('Forecast rain', 25, cl(d['rain'] / 150), f"{d['rain']:.0f} mm"), ('Chance of rain', 15, cl(d['prob'] / 100), f"{d['prob']}%")],
        'Fire': [('Heat', 25, cl((d['tmax'] - 25) / 20), f"{d['tmax']:.0f} °C"), ('Dry ground (little recent rain)', 30, 1 - cl(r7 / 40), f'{r7:.0f} mm'),
                 ('Wind', 25, cl(d['wind'] / 50), f"{d['wind']:.0f} km/h"), ('Dry day (low rain chance)', 20, 1 - cl(d['prob'] / 100), f"{d['prob']}%")],
        'Landslide': [('Terrain slope (3 km sample)', 35, None if sl is None else cl(sl / 20), 'n/a' if sl is None else f'{sl}°'), ('Forecast rain', 25, cl(d['rain'] / 120), f"{d['rain']:.0f} mm"),
                      ('Wet ground', 25, cl(r7 / 250), f'{r7:.0f} mm'), ('Chance of rain', 15, cl(d['prob'] / 100), f"{d['prob']}%")],
        'Earthquake': [('Strongest quake, 30 days, 300 km (USGS)', 60, None if mq is None else cl((mq - 2.5) / 4), 'n/a' if mq is None else f'M{mq:.1f}'),
                       ('Number of quakes M2.5+', 40, None if nq is None else cl(nq / 15), 'n/a' if nq is None else str(nq))]}
    x = (ctx or {}).get('exp') or {}; ev = (ctx or {}).get('ev'); T_ = lambda v: 'state not in database' if v is None else f'{v:.1f} of 1'
    N = lambda k: None if not ev else cl(ev.get(k, 0) / 3); Nt = lambda k: 'n/a' if not ev else f'{ev.get(k, 0)} events'
    H['Flood'] += [('Flood exposure of state (database: NDMA atlas)', 15, x.get('flood'), T_(x.get('flood'))), ('Major flood events in state (database)', 10, N('flood'), Nt('flood'))]
    H['Storm'] += [('Cyclone-prone coast of state (database: NDMA)', 25, x.get('storm'), T_(x.get('storm'))), ('Major cyclone events in state (database)', 10, N('storm'), Nt('storm'))]
    H['Landslide'] += [('Landslide-prone region (database: GSI/NDMA)', 20, x.get('landslide'), T_(x.get('landslide'))), ('Major landslide events in state (database)', 10, N('landslide'), Nt('landslide'))]
    H['Earthquake'] += [('Seismic zone of state (database: BIS IS 1893)', 50, x.get('quake'), T_(x.get('quake'))), ('Major earthquake events in state (database)', 10, N('quake'), Nt('quake'))]
    return H


def route_risk(flood, elevs, mins, best):
    """Route risk = flood score x low-ground exposure along the route (real elevations) + small time penalty. Lower = safer."""
    ex = sum(cl(1 - e / 60) for e in elevs) / len(elevs) if elevs else None
    t = 10 * cl((mins - best) / best) if best > 0 else 0
    return round(min(100, flood * (0.5 if ex is None else ex) + t)), ex


def score(fs):
    av = [(w, f) for _, w, f, _ in fs if f is not None]; return round(100 * sum(w * f for w, f in av) / sum(w for w, _ in av)) if av else 0
def scores(H): return {k: score(v) for k, v in H.items()}
def overall(S): return round(0.6 * max(S.values()) + 0.4 * sum(S.values()) / len(S))


def alerts(env):
    """Plain alerts using India Meteorological Department (IMD) rainfall categories (mm per day)."""
    out = []
    for i, d in enumerate(env['daily']):
        r = d['rain']; cat = 'Extremely heavy' if r >= 204.5 else 'Very heavy' if r >= 115.6 else 'Heavy' if r >= 64.5 else None
        if cat: out.append((i, 'High' if r >= 115.6 else 'Moderate', f'{cat} rainfall forecast ({r:.0f} mm)'))
        if d['gust'] >= 62: out.append((i, 'Moderate', f"Strong wind gusts up to {d['gust']:.0f} km/h"))
        if d['tmax'] >= 40: out.append((i, 'Moderate', f"Heat: max {d['tmax']:.0f} °C"))
    return out


def readiness(profile_fields, n_contacts, status_set, n_checks, saved_place, kit, plans_read):
    return [('Profile completed (2 per field)', 2 * profile_fields, 10, 'Fill name, phone, area, city, state'),
            ('Emergency contacts (10 each, max 2)', min(20, 10 * n_contacts), 20, 'Add family contacts in SOS tab'),
            ('Family safety status updated', 10 if status_set else 0, 10, 'Set a contact status in SOS tab'),
            ('Safety checklist (5 per item)', 5 * n_checks, 30, 'Tick items in Vault tab'),
            ('Nearest shelter/hospital saved', 10 if saved_place else 0, 10, 'Save a place in Safe Places tab'),
            ('Offline kit downloaded', 10 if kit else 0, 10, 'Press Download offline kit in Vault'),
            ('Disaster plans read (2.5 each)', 2.5 * plans_read, 10, 'Mark plans as read in Vault')]

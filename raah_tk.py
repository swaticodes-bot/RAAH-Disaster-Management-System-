"""RAAH - Your Way To Safety | Python Tkinter + SQLite + live public data APIs.
Run:  python raah_tk.py   (Python 3.8+, internet needed for live data; saved data is shown when offline)"""
import tkinter as tk, os, webbrowser, datetime, threading, queue, time, hashlib
from tkinter import ttk, messagebox
import db as dbm, services as sv, risk_model as rm

HERE = os.path.dirname(os.path.abspath(__file__))
BG, CARD, INK, ACC, TEAL, MUT, OK, WARN, BAD, NAVY, GREY = '#dff1ee', '#ffffff', '#10223a', '#f0473f', '#0f9d94', '#56677f', '#1fa35c', '#e0a000', '#d93a3a', '#0b1630', '#9db5b2'
FN = 'Segoe UI'; LV = {'Low': OK, 'Moderate': WARN, 'High': BAD}
KC = {'Hospital': '#d93a3a', 'Police': '#2a5bd7', 'Fire station': '#e07a00', 'Shelter / assembly point': '#1fa35c'}
NUMS = [('112', 'Emergency'), ('100', 'Police'), ('101', 'Fire'), ('108', 'Ambulance'), ('1078', 'Disaster Mgmt')]
PLANS = {'Flood': 'Before: know your shelter, keep documents high.\nDuring: never walk or drive through floodwater.\nAfter: wait for the official all-clear.',
         'Cyclone / Storm': 'Before: secure loose items, charge phone.\nDuring: stay indoors away from windows.\nAfter: avoid fallen wires.',
         'Fire': 'Before: know two exits.\nDuring: stay low, leave, call 101.\nAfter: do not re-enter until cleared.',
         'Earthquake': 'Before: identify safe spots.\nDuring: drop, cover, hold on.\nAfter: expect aftershocks.'}
CHK = ['Keep phone charged', 'Keep documents accessible', 'Keep drinking water', 'Know your nearest shelter', 'Inform family members', 'Follow official evacuation instructions']
EMO = ['🦊', '🐼', '🐯', '🦉', '🐬', '🦁']
TABS = [('home', '🏠', 'Home'), ('forecast', '🌦', 'Forecast'), ('places', '🗺', 'Places'), ('escape', '🧭', 'Escape'), ('news', '📰', 'News'), ('reports', '📣', 'Reports'), ('sos', '📞', 'SOS'), ('vault', '🎒', 'Vault')]
ACT = {'Flood': ['Avoid low-lying roads and underpasses', 'Know your nearest shelter (Places tab)', 'Move documents and electronics up', 'Inform family'],
       'Storm': ['Secure loose objects', 'Stay indoors away from windows', 'Charge phone and power bank', 'Follow IMD and local alerts'],
       'Fire': ['Know two exits from your building', 'Keep dry waste away from home', 'Save 101 on speed dial', 'Inform family'],
       'Landslide': ['Avoid steep slopes and cuttings', 'Watch for cracks or tilting trees', 'Know your evacuation route', 'Inform family'],
       'Earthquake': ['Identify safe spots (under sturdy furniture)', 'Keep an emergency kit ready', 'Know how to turn off gas/power', 'Inform family']}


def wxn(c):
    for ks, t, e in (((0,), 'Clear sky', '☀'), ((1, 2), 'Partly cloudy', '⛅'), ((3,), 'Overcast', '☁'), ((45, 48), 'Fog', '🌫'), ((51, 53, 55, 56, 57), 'Drizzle', '🌦'),
                     ((61, 63, 65, 66, 67), 'Rain', '🌧'), ((71, 73, 75, 77, 85, 86), 'Snow', '❄'), ((80, 81, 82), 'Rain showers', '🌧'), ((95, 96, 99), 'Thunderstorm', '⛈')):
        if c in ks: return t, e
    return 'Unknown', '☁'


def dayname(i, d): return 'Today' if i == 0 else 'Tomorrow' if i == 1 else datetime.date.fromisoformat(d).strftime('%a %d %b')
def hsh(pw, salt): return hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 100000).hex()


def ago(ts):
    try: m = int((datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(ts)).total_seconds() // 60)
    except Exception: return ''
    return f'{m} min ago' if m < 60 else f'{m // 60} h ago' if m < 1440 else f'{m // 1440} d ago'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('RAAH — Your Way To Safety'); self.geometry('430x800'); self.minsize(380, 640); self.configure(bg=BG)
        self.db = dbm.DB(os.path.join(HERE, 'raah.db')); self.gen = 0; self.day = 0; self.off = False; self.tab = 'home'; self.emo = EMO[0]; self.tl = {}
        self.nscope, self.nsrc = 'Your area', 'All sources'; self.user = None
        NUMS[:] = self.db.helplines(); PLANS.clear(); PLANS.update(self.db.plans())  # reference data comes from the database
        uid = self.db.kget(0, 'session')
        if uid: self.user = self.db.one('SELECT * FROM users WHERE id=?', (uid,))
        self.mode = 'login' if self.db.one('SELECT 1 FROM users') else 'signup'; self.show()

    # ---------- plumbing ----------
    @property
    def uid(self): return self.user['id']
    @property
    def area(self): return next((a for a in self.db.areas(self.uid) if a['active']), None)

    def bg(self, fn, cb):
        qu = queue.Queue()
        def work():
            try: qu.put((fn(), None))
            except Exception as ex: qu.put((None, str(ex)))
        threading.Thread(target=work, daemon=True).start()
        def poll():
            try: r, er = qu.get_nowait()
            except queue.Empty: return self.after(150, poll)
            cb(r, er)
        poll()

    def fetch(self, key, fn, ttl, done):
        g = self.gen; c = self.db.cget(key)
        def fin(d, note):
            if g == self.gen: done(d, note)
        if c and (self.off or time.time() - c[1] < ttl): return fin(c[0], 'Offline mode — showing saved data' if self.off else '')
        if self.off: return fin(None, 'Offline mode and nothing saved yet for this.')
        def cb(r, er):
            if r is not None: self.db.cset(key, r); fin(r, '')
            elif c: fin(c[0], 'No internet — showing data saved ' + datetime.datetime.fromtimestamp(c[1]).strftime('%d %b %H:%M'))
            else: fin(None, er)
        self.bg(fn, cb)

    def with_env(self, box, render):
        a = self.area; self.lab(box, '⏳ Fetching live forecast…', 10, fg=MUT)
        def job():
            e = {'place': a, 'errors': []}; e.update(sv.weather(a['lat'], a['lon']))
            for k, f in (('flood', sv.river), ('quakes', sv.quakes), ('terrain', sv.terrain)):
                try: e[k] = f(a['lat'], a['lon'])
                except Exception: e[k] = None; e['errors'].append(k)
            return e
        def done(e, note):
            for w in box.winfo_children(): w.destroy()
            if e is None: return self.lab(box, 'Live data unavailable. Check your internet connection.\n' + str(note), 10, fg=BAD)
            render(box, e, note)
        self.fetch(f"env:{a['id']}", job, 1800, done)

    def card(self, p, bg=CARD):
        f = tk.Frame(p, bg=bg, highlightbackground='#bcd8d3', highlightthickness=1); f.pack(fill='x', padx=12, pady=6)
        i = tk.Frame(f, bg=bg); i.pack(fill='x', padx=14, pady=12); return i

    def lab(self, p, t, s=10, b=False, fg=INK):
        l = tk.Label(p, text=t, font=(FN, s, 'bold' if b else 'normal'), fg=fg, bg=p['bg'], anchor='w', justify='left', wraplength=340); l.pack(fill='x'); return l

    def btn(self, p, t, cmd, bg=ACC, fg='white', side='left'):
        b = tk.Button(p, text=t, command=cmd, bg=bg, fg=fg, activebackground=bg, activeforeground=fg, relief='flat', bd=0, padx=10, pady=5, font=(FN, 9, 'bold'), cursor='hand2'); b.pack(side=side, padx=3, pady=3); return b

    def row(self, p): r = tk.Frame(p, bg=p['bg']); r.pack(fill='x', pady=2); return r
    def chip(self, p, t, c): tk.Label(p, text=t, bg=c, fg='white', font=(FN, 8, 'bold'), padx=8, pady=2).pack(side='left', padx=2)

    def meter(self, p, val, bg=CARD, w=320):
        c = tk.Canvas(p, width=w, height=12, bg=bg, highlightthickness=0); c.pack(anchor='w', pady=3); val = max(0, min(100, val))
        c.create_rectangle(0, 2, w, 10, fill='#d6e4e2', outline=''); bar = c.create_rectangle(0, 2, 0, 10, fill=TEAL if val < 35 else WARN if val < 65 else ACC, outline='')
        def step(x=0):
            t = w * val / 100
            if not c.winfo_exists(): return
            c.coords(bar, 0, 2, min(x, t), 10)
            if x < t: self.after(15, step, x + 10)
        step()

    def scroller(self, parent):
        c = tk.Canvas(parent, bg=BG, highlightthickness=0); sb = ttk.Scrollbar(parent, command=c.yview); f = tk.Frame(c, bg=BG)
        f.bind('<Configure>', lambda e: c.configure(scrollregion=c.bbox('all'))); w = c.create_window((0, 0), window=f, anchor='nw'); c.bind('<Configure>', lambda e: c.itemconfig(w, width=e.width))
        c.configure(yscrollcommand=sb.set); c.pack(side='left', fill='both', expand=True); sb.pack(side='right', fill='y')
        def wheel(e):
            try: c.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, 'units')
            except tk.TclError: pass
        for ev in ('<MouseWheel>', '<Button-4>', '<Button-5>'): c.bind_all(ev, wheel)
        return f

    # ---------- auth ----------
    def show(self):
        for w in self.winfo_children(): w.destroy()
        self.shell() if self.user else self.auth()

    def auth(self):
        f = tk.Frame(self, bg=BG); f.pack(fill='both', expand=True)
        tk.Label(f, text='🌊  RAAH  🔥', font=(FN, 32, 'bold'), fg=INK, bg=BG).pack(pady=(18, 0)); tk.Label(f, text='YOUR WAY TO SAFETY', font=(FN, 9, 'bold'), fg=TEAL, bg=BG).pack()
        c = self.card(f); su = self.mode == 'signup'; self.ent = {}; self.lab(c, 'Create your safety profile' if su else 'Welcome back 👋', 11, True)
        if su:
            r = tk.Frame(c, bg=CARD); r.pack(pady=4); self.eb = []
            for e in EMO:
                b = tk.Button(r, text=e, font=('Segoe UI Emoji', 17), relief='flat', bg='#ffd9d6' if e == self.emo else CARD, command=lambda e=e: self.pick(e)); b.pack(side='left', padx=2); self.eb.append((b, e))
            fields = [('name', 'Full name'), ('un', 'Username'), ('ph', 'Phone number (private)'), ('ar', 'Area / locality'), ('ci', 'City'), ('stt', 'State')]
        else: fields = [('un', 'Username')]
        for k, t in fields + [('pw', 'Password')]:
            self.lab(c, t, 9, fg=MUT); e = tk.Entry(c, show='*' if k == 'pw' else '', font=(FN, 10), relief='solid', bd=1); e.pack(fill='x', pady=(0, 5), ipady=4); self.ent[k] = e
        if su: self.lab(c, '🔒 Others only see your area name — never your exact location or phone number.', 8, fg=TEAL)
        self.err = self.lab(c, '', 9, fg=BAD)
        tk.Button(c, text='CREATE ACCOUNT' if su else 'LOG IN', command=self.signup if su else self.login, bg=ACC, fg='white', relief='flat', font=(FN, 10, 'bold'), pady=8).pack(fill='x', pady=3)
        tk.Button(c, text=('Have an account? Log in' if su else 'New to RAAH? Sign up'), command=self.flip, bg=CARD, fg=TEAL, relief='flat', bd=0).pack(pady=4)

    def pick(self, e):
        self.emo = e
        for b, x in self.eb: b.config(bg='#ffd9d6' if x == e else CARD)

    def flip(self): self.mode = 'login' if self.mode == 'signup' else 'signup'; self.show()
    def g(self, k): return self.ent[k].get().strip()

    def signup(self):
        u = {k: self.g(k) for k in ('name', 'un', 'ph', 'ar', 'ci', 'stt')}; pw = self.ent['pw'].get(); u['un'] = ''.join(ch for ch in u['un'].lower() if ch.isalnum() or ch == '_')
        if not all(u[k] for k in ('name', 'un', 'ar', 'ci')): return self.err.config(text='Fill name, username, area and city.')
        if sum(ch.isdigit() for ch in u['ph']) < 10: return self.err.config(text='Enter a valid phone number.')
        if len(pw) < 6: return self.err.config(text='Password needs 6+ characters.')
        if self.db.one('SELECT 1 FROM users WHERE un=?', (u['un'],)): return self.err.config(text='Username already taken.')
        salt = os.urandom(8).hex()
        uid = self.db.x('INSERT INTO users(un,salt,h,name,phone,area,city,state,emoji,joined) VALUES(?,?,?,?,?,?,?,?,?,?)', (u['un'], salt, hsh(pw, salt), u['name'], u['ph'], u['ar'], u['ci'], u['stt'], self.emo, datetime.date.today().strftime('%d %b %Y')))
        self.login_as(uid)

    def login(self):
        r = self.db.one('SELECT * FROM users WHERE un=?', (self.g('un').lower(),))
        if not r or r['h'] != hsh(self.ent['pw'].get(), r['salt']): return self.err.config(text='Wrong username or password.')
        self.login_as(r['id'])

    def login_as(self, uid):
        self.db.kset(0, 'session', uid); self.user = self.db.one('SELECT * FROM users WHERE id=?', (uid,)); self.show()

    def logout(self): self.db.kset(0, 'session', None); self.user = None; self.mode = 'login'; self.show()

    # ---------- shell ----------
    def shell(self):
        top = tk.Frame(self, bg=BG); top.pack(fill='x', padx=12, pady=(8, 2)); tk.Label(top, text='RAAH', font=(FN, 16, 'bold'), fg=INK, bg=BG).pack(side='left')
        tk.Button(top, text=self.user['emoji'], font=('Segoe UI Emoji', 14), relief='flat', bg=CARD, command=lambda: self.go('me')).pack(side='right')
        a = self.area; tk.Button(top, text=f"📍 {a['name'] if a else 'Choose area'} ▾", font=(FN, 9, 'bold'), relief='flat', bg=CARD, fg=INK, command=self.pick_area).pack(side='right', padx=6)
        self.banner = tk.Label(self, text='OFFLINE MODE — showing saved data only', bg=BAD, fg='white', font=(FN, 9, 'bold'))
        nav = tk.Frame(self, bg=CARD); nav.pack(side='bottom', fill='x'); self.nb = {}
        for k, e, t in TABS:
            b = tk.Button(nav, text=f'{e}\n{t}', font=(FN, 8), relief='flat', bg=CARD, fg=MUT, command=lambda k=k: self.go(k)); b.pack(side='left', expand=True, fill='x'); self.nb[k] = b
        self.host = tk.Frame(self, bg=BG); self.host.pack(fill='both', expand=True); self.go(self.tab)
        if not a: self.after(300, lambda: self.pick_area(True))

    def go(self, tab):
        self.tab = tab; self.gen += 1
        for w in self.host.winfo_children(): w.destroy()
        if self.off: self.banner.pack(fill='x', before=self.host)
        else: self.banner.pack_forget()
        for k, b in self.nb.items(): b.config(fg=ACC if k == tab else MUT)
        if not self.area and tab not in ('me', 'vault', 'sos'): return self.lab(self.scroller(self.host), '\nChoose an area (top right) to load live data.', 11, fg=MUT)
        getattr(self, 'v_' + tab)(self.scroller(self.host))

    def pick_area(self, first=False):
        w = tk.Toplevel(self); w.title('Choose area'); w.geometry('380x470'); w.configure(bg=BG); w.transient(self)
        tk.Label(w, text='Search any city, town or locality', font=(FN, 11, 'bold'), bg=BG).pack(pady=8); e = tk.Entry(w, font=(FN, 11)); e.pack(fill='x', padx=14, ipady=4)
        if first: e.insert(0, self.user['area'])
        ind = tk.BooleanVar(value=True); tk.Checkbutton(w, text='India only', variable=ind, bg=BG).pack()
        lb = tk.Listbox(w, font=(FN, 10), height=12); lb.pack(fill='both', expand=True, padx=14, pady=6); res = []; msg = tk.Label(w, text='', bg=BG, fg=MUT); msg.pack()
        def search(ev=None):
            if not e.get().strip(): return
            msg.config(text='Searching…')
            def ok(r, er):
                if not w.winfo_exists(): return
                res[:] = r or []; lb.delete(0, 'end')
                for x in res: lb.insert('end', f"{x['name']}, {x['admin']} ({x['country']})" + (f"  · {x['elev']:.0f} m" if x.get('elev') is not None else ''))
                msg.config(text='' if res else (er or 'No results — try another spelling'))
            self.bg(lambda: sv.geocode(e.get().strip(), ind.get()), ok)
        def choose(ev=None):
            s = lb.curselection()
            if not s: return
            self.db.add_area(self.uid, res[s[0]]); self.day = 0; w.destroy(); self.show()
        e.bind('<Return>', search); lb.bind('<Double-Button-1>', choose); r = tk.Frame(w, bg=BG); r.pack(pady=6)
        self.btn(r, 'Search', search, TEAL); self.btn(r, 'Select area', choose)
        if first: search()

    # ---------- Home ----------
    def v_home(self, b): box = tk.Frame(b, bg=BG); box.pack(fill='x'); self.with_env(box, self.r_home)
    def shift(self, d): self.day = max(0, min(6, self.day + d)); self.go('home')

    def r_home(self, box, e, note):
        i = min(self.day, len(e['daily']) - 1); d = e['daily'][i]; H = rm.hazards(e, i, self.ctx()); S = rm.scores(H); ov = rm.overall(S); n = e['now']; a = self.area; wt, we = wxn(d['code'])
        for hz, fs in H.items(): self.db.log_calc(self.uid, a['name'], d['date'], hz, S[hz], rm.lvl(S[hz]), [[f[0], f[1], f[2], f[3]] for f in fs])  # audit log of every calculation
        c = self.card(box, NAVY); r = self.row(c); self.btn(r, '◀', lambda: self.shift(-1), '#3a4a78'); tk.Label(r, text=dayname(i, d['date']), font=(FN, 11, 'bold'), fg='#f3eee2', bg=NAVY).pack(side='left', expand=True); self.btn(r, '▶', lambda: self.shift(1), '#3a4a78', side='right')
        self.lab(c, f"{a['name']}, {a['admin']}", 17, True, '#f3eee2'); r = self.row(c); self.chip(r, 'LIVE · Open-Meteo', TEAL); self.chip(r, f'RISK: {rm.lvl(ov).upper()}', LV[rm.lvl(ov)])
        if i == 0: self.lab(c, f"{we} {n['temp']:.0f}°C (feels {n['feels']:.0f}°) · {wt if n['code'] == d['code'] else wxn(n['code'])[0]} · humidity {n['rh']}% · wind {n['wind']:.0f} km/h · rain last 24h {e['rain24']:.1f} mm", 9, fg='#d7def0')
        self.lab(c, f"Forecast: {we} {wt} · {d['tmin']:.0f}–{d['tmax']:.0f}°C · rain {d['rain']:.1f} mm ({d['prob']}% chance) · gusts {d['gust']:.0f} km/h", 9, fg='#d7def0')
        self.lab(c, f'{ov} / 100', 28, True, '#f3eee2'); self.meter(c, ov, NAVY); r = self.row(c)
        for hz in S: x = tk.Frame(r, bg=NAVY); x.pack(side='left', padx=3); tk.Label(x, text=hz, fg='#b7c2de', bg=NAVY, font=(FN, 8)).pack(); self.chip(x, f'{S[hz]} {rm.lvl(S[hz])}', LV[rm.lvl(S[hz])])
        self.lab(c, 'Indicative index from live forecast data — not an official warning. Follow IMD/NDMA/local authorities.', 8, fg='#b7c2de')
        if note: self.lab(c, note, 8, fg='#ffd27a')
        if e['errors']: self.lab(c, 'Data not available here: ' + ', '.join(e['errors']) + ' (left out of the score)', 8, fg='#ffd27a')
        self.btn(c, 'How is this calculated?', lambda: self.go('why'), TEAL)
        al = rm.alerts(e); c = self.card(box); self.lab(c, '⚠ Alerts from forecast', 12, True)
        if not al: self.lab(c, 'No heavy rain, strong wind or heat alerts in the 7-day forecast.', 9, fg=MUT)
        for di, lv, t in al: r = self.row(c); self.chip(r, lv.upper(), LV[lv]); self.lab(r, f"{dayname(di, e['daily'][di]['date'])}: {t}", 9)
        top = max(S, key=S.get); c = self.card(box); self.lab(c, 'What should I do now?', 12, True); self.lab(c, f'Top concern for {dayname(i, d["date"])}: {top} ({rm.lvl(S[top])}, {S[top]}/100)', 9, fg=MUT)
        for k, t in enumerate(ACT[top], 1): self.lab(c, f'{k}. {t}')
        rd = round(sum(x[1] for x in self.rdy())); c = self.card(box); self.lab(c, f'Readiness {rd} / 100', 12, True); self.meter(c, rd); self.btn(c, 'See breakdown', lambda: self.go('me'), TEAL)

    def r_why(self, box, e, note):
        i = min(self.day, 6); H = rm.hazards(e, i, self.ctx()); S = rm.scores(H); c = self.card(box); self.lab(c, f"How {self.area['name']} is scored — {dayname(i, e['daily'][i]['date'])}", 13, True)
        self.lab(c, 'Each hazard = weighted factors from real data (max 100). Missing data is left out and the rest re-scaled. Level: below 35 Low, 35-64 Moderate, 65+ High. Overall = 60% worst hazard + 40% average.', 9, fg=MUT)
        self.lab(c, f'Overall: {rm.overall(S)} / 100 → {rm.lvl(rm.overall(S))}', 15, True)
        self.lab(c, 'Sources: Open-Meteo forecast & elevation, GloFAS river discharge, USGS earthquakes. Storm index uses forecast winds and rain; official cyclone warnings come from IMD (mausam.imd.gov.in).', 8, fg=MUT)
        for hz, fs in H.items():
            c = self.card(box); r = self.row(c); tk.Label(r, text=hz, font=(FN, 12, 'bold'), bg=CARD).pack(side='left'); self.chip(r, f'{S[hz]} · {rm.lvl(S[hz]).upper()}', LV[rm.lvl(S[hz])])
            for l, w, f, t in fs: self.lab(c, f'{l}: {t}  →  ' + ('not available' if f is None else f'+{w * f:.1f} / {w}'), 9); self.meter(c, 0 if f is None else 100 * f, w=260)
        st = a_ = self.area['admin']; ex = self.db.exposure(st); c = self.card(box); self.lab(c, f'Reference database used for {st}', 12, True)
        self.lab(c, ('Exposure (0-1): flood %.1f · cyclone %.1f · landslide %.1f · earthquake %.1f  — table state_exposure' % (ex['flood'], ex['storm'], ex['landslide'], ex['quake'])) if ex else 'State not in the exposure table — those factors are left out of the score.', 9)
        for ev in self.db.q('SELECT * FROM events WHERE states LIKE ? ORDER BY year', (f'%{st}%',)): self.lab(c, f"• {ev['year']} {ev['name']} ({ev['type']}): {ev['impact']}", 8, fg=MUT)
        self.lab(c, 'Every calculation is saved in table calc_log (inputs, score, level, time) so results can be audited. Event figures are rounded public numbers.', 8, fg=MUT)
        self.btn(box, '← Back', lambda: self.go('home'), GREY)

    def v_why(self, b): box = tk.Frame(b, bg=BG); box.pack(fill='x'); self.with_env(box, self.r_why)

    # ---------- Forecast ----------
    def v_forecast(self, b): box = tk.Frame(b, bg=BG); box.pack(fill='x'); self.with_env(box, self.r_fc)

    def r_fc(self, box, e, note):
        self.lab(box, f"  7-day forecast · {self.area['name']}", 14, True)
        if note: self.lab(box, '  ' + note, 8, fg=WARN)
        for i, d in enumerate(e['daily']):
            S = rm.scores(rm.hazards(e, i, self.ctx())); ov = rm.overall(S); wt, we = wxn(d['code']); c = self.card(box, '#fff4d6' if i == self.day else CARD); r = self.row(c)
            tk.Label(r, text=f"{we} {dayname(i, d['date'])}", font=(FN, 11, 'bold'), bg=c['bg']).pack(side='left'); self.chip(r, f'{rm.lvl(ov)} {ov}', LV[rm.lvl(ov)])
            self.lab(c, f"{wt} · {d['tmin']:.0f}–{d['tmax']:.0f}°C · rain {d['rain']:.1f} mm ({d['prob']}%) · wind {d['wind']:.0f} / gust {d['gust']:.0f} km/h", 9, fg=MUT)
            self.btn(c, 'View risk for this day', lambda i=i: (setattr(self, 'day', i), self.go('home')), TEAL)

    def ctx(self):
        st = self.area['admin']; ex = self.db.exposure(st)
        return dict(exp=ex, ev={h: self.db.events_count(st, t) for h, t in (('flood', 'Flood'), ('storm', 'Cyclone'), ('landslide', 'Landslide'), ('quake', 'Earthquake'))}) if ex else dict(exp=None, ev=None)

    # ---------- Escape routes (real roads + real elevation) ----------
    def v_escape(self, b): box = tk.Frame(b, bg=BG); box.pack(fill='x'); self.with_env(box, self.r_escape)

    def r_escape(self, box, e, note):
        a = self.area; fl = rm.scores(rm.hazards(e, self.day, self.ctx()))['Flood']; c = self.card(box); self.lab(c, '🧭 Escape routes', 14, True)
        self.lab(c, f"From: {a['name']} (area centre) · Flood score for {dayname(self.day, e['daily'][self.day]['date'])}: {fl}/100", 9, fg=MUT); dests = {}; cp = self.db.cget(f"pl:{a['id']}")
        for x in (cp[0] if cp else []):
            if x['kind'] in ('Hospital', 'Shelter / assembly point'): dests[f"{x['kind'][0]} · {x['name']} ({x['dist']} km)"] = (x['lat'], x['lon'], x['name'])
        for s_ in self.db.q('SELECT * FROM saved_places WHERE user_id=?', (self.uid,)): dests[f"★ {s_['name']}"] = (s_['lat'], s_['lon'], s_['name'])
        self.lab(c, 'Destination (nearby shelter / hospital / saved place):', 9, fg=MUT); cb = ttk.Combobox(c, values=list(dests), state='readonly'); cb.pack(fill='x', pady=2)
        if not dests: self.lab(c, 'Open the Places tab once to load nearby shelters and hospitals, or type a destination below.', 8, fg=WARN)
        self.lab(c, '…or type any destination (city / locality / landmark):', 9, fg=MUT); en = tk.Entry(c, font=(FN, 10), relief='solid', bd=1); en.pack(fill='x', ipady=3); out = tk.Frame(box, bg=BG); out.pack(fill='x')
        def run():
            txt, sel = en.get().strip(), cb.get()
            if not txt and not sel: return messagebox.showinfo('RAAH', 'Choose or type a destination.')
            self.find_routes(out, fl, None if txt else dests.get(sel), txt)
        self.btn(c, 'Find safest route', run)

    def find_routes(self, out, fl, dest, txt):
        for w in out.winfo_children(): w.destroy()
        self.lab(out, '⏳ Getting real road routes and ground elevation…', 10, fg=MUT); a = self.area; g = self.gen
        def job():
            d = dest
            if d is None:
                r = sv.geocode(txt, True) or sv.geocode(txt, False)
                if not r: raise Exception('Destination not found')
                d = (r[0]['lat'], r[0]['lon'], f"{r[0]['name']}, {r[0]['admin']}")
            prov, rs = sv.routes(a['lat'], a['lon'], d[0], d[1])
            for r in rs:
                p = r['pts']; r['elev'] = []
                try: r['elev'] = sv.elevations(p[::max(1, len(p) // 20)][:25])
                except Exception: pass
            try: P = [x for r in rs for x in r['pts']]; tl = sv.fit_tiles([x[0] for x in P], [x[1] for x in P])
            except Exception: tl = None
            return dict(d=d, prov=prov, rs=rs, tl=tl)
        def cb(res, er):
            if g != self.gen or not out.winfo_exists(): return
            for w in out.winfo_children(): w.destroy()
            if not res: return self.lab(out, 'Could not get routes (needs internet). ' + str(er), 10, fg=BAD)
            self.r_routes(out, res, fl)
        self.bg(job, cb)

    def r_routes(self, out, R, fl):
        a = self.area; d = R['d']; rs = R['rs']; best = min(r['min'] for r in rs)
        for r in rs: r['risk'], r['ex'] = rm.route_risk(fl, r['elev'], r['min'], best)
        order = sorted(range(len(rs)), key=lambda i: (rs[i]['risk'], rs[i]['min'])); col = {}
        for k, i in enumerate(order): col[i] = TEAL if len(rs) == 1 else (OK, WARN, BAD)[min(k, 2)]
        c = self.card(out); self.lab(c, f'To: {d[2]}', 12, True); self.lab(c, 'Real road routes by ' + R['prov'], 8, fg=MUT)
        cv = tk.Canvas(c, width=340, height=300, bg='#dfeaf0', highlightthickness=0); cv.pack(pady=4); tl = R['tl']
        if tl:
            z, L0, T0 = tl['z'], tl['left'], tl['top']; self.rimgs = []
            try:
                for k, v in tl['t'].items(): tx, ty = map(int, k.split(',')); im = tk.PhotoImage(data=v); self.rimgs.append(im); cv.create_image(tx * 256 - L0, ty * 256 - T0, anchor='nw', image=im)
            except tk.TclError: pass
            def XY(p): x, y = sv.project(p[0], p[1], z); return x - L0, y - T0
            for i in reversed(order):
                p = rs[i]['pts']; pts = [v for pp in p[::max(1, len(p) // 250)] + [p[-1]] for v in XY(pp)]; cv.create_line(*pts, fill=col[i], width=6 if i == order[0] else 3, capstyle='round', joinstyle='round')
            sx, sy = XY((a['lat'], a['lon'])); ex_, ey = XY((d[0], d[1]))
            cv.create_oval(sx - 7, sy - 7, sx + 7, sy + 7, fill=NAVY, outline='white', width=2); cv.create_oval(ex_ - 8, ey - 8, ex_ + 8, ey + 8, fill=ACC, outline='white', width=2); cv.create_text(6, 292, text='© OpenStreetMap contributors', anchor='w', font=(FN, 7))
        else: cv.create_text(170, 150, text='Map tiles unavailable')
        r0 = rs[order[0]]; self.lab(c, f"✅ Route {order[0] + 1} is recommended: lowest risk ({r0['risk']}/100).", 10, True)
        self.lab(c, 'Basis: route risk = flood score × low-ground exposure (real elevations sampled along the road) + time penalty (max 10). Low ground floods first, so routes over higher ground score safer. Not an official evacuation route — follow authorities.', 8, fg=MUT)
        for rank, i in enumerate(order):
            r = rs[i]; c = self.card(out); tag = 'ONLY ROUTE' if len(rs) == 1 else ('SAFEST', 'CAUTION', 'AVOID')[min(rank, 2)]; self.chip(self.row(c), tag, col[i])
            self.lab(c, f"Route {i + 1}: {r['km']:.1f} km · {r['min']:.0f} min · risk {r['risk']}/100", 11, True)
            exs = 'n/a' if r['ex'] is None else '%.2f' % r['ex']; el = ('avg ground %.0f m, lowest %.0f m' % (sum(r['elev']) / len(r['elev']), min(r['elev']))) if r['elev'] else 'elevation unavailable'
            self.lab(c, f'Flood score {fl} × exposure {exs} ({el})', 9, fg=MUT); rw = self.row(c)
            self.btn(rw, 'Open in Google Maps ↗', lambda: webbrowser.open(sv.gmaps_url(a['lat'], a['lon'], d[0], d[1])), NAVY)
            self.btn(rw, 'OSM ↗', lambda: webbrowser.open(f"https://www.openstreetmap.org/directions?from={a['lat']},{a['lon']}&to={d[0]},{d[1]}"), GREY)

    def db_viewer(self):
        w = tk.Toplevel(self); w.title('RAAH database (SQLite: raah.db)'); w.geometry('720x440')
        names = [r['name'] for r in self.db.q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        cb = ttk.Combobox(w, values=[f"{n} ({self.db.one('SELECT COUNT(*) n FROM ' + n)['n']} rows)" for n in names], state='readonly', width=44); cb.pack(anchor='w', padx=6, pady=6)
        tv = ttk.Treeview(w, show='headings'); sb = ttk.Scrollbar(w, command=tv.yview); tv.configure(yscrollcommand=sb.set); sb.pack(side='right', fill='y'); tv.pack(fill='both', expand=True)
        def show(ev=None):
            n = names[cb.current()]; rows = self.db.q(f'SELECT * FROM {n} LIMIT 300'); cols = list(rows[0]) if rows else [r['name'] for r in self.db.q(f'PRAGMA table_info({n})')]
            tv.delete(*tv.get_children()); tv['columns'] = cols
            for c in cols: tv.heading(c, text=c); tv.column(c, width=110)
            for r in rows: tv.insert('', 'end', values=['•••' if c in ('h', 'salt') else str(r[c])[:60] for c in cols])
        cb.bind('<<ComboboxSelected>>', show); cb.current(0); show()

    # ---------- Places (OpenStreetMap) ----------
    def v_places(self, b):
        a = self.area; box = tk.Frame(b, bg=BG); box.pack(fill='x'); self.lab(box, '⏳ Loading real nearby places from OpenStreetMap…', 10, fg=MUT)
        def done(p, note):
            for w in box.winfo_children(): w.destroy()
            if p is None: return self.lab(box, 'Could not load places. Check internet.\n' + str(note), 10, fg=BAD)
            self.r_places(box, p, note)
        self.fetch(f"pl:{a['id']}", lambda: sv.places(a['lat'], a['lon']), 21600, done)

    def r_places(self, box, p, note):
        a = self.area; c = self.card(box); self.lab(c, f"Safe places near {a['name']}", 14, True)
        if note: self.lab(c, note, 8, fg=WARN)
        self.lab(c, 'Real locations from OpenStreetMap. Shelter occupancy is not public data — call to confirm before going.', 8, fg=MUT)
        cv = tk.Canvas(c, width=340, height=260, bg='#dfeaf0', highlightthickness=0); cv.pack(pady=4); cv.create_text(170, 130, text='Loading map…')
        def draw(t):
            if not cv.winfo_exists(): return
            cv.delete('all'); z, px, py = t['z'], t['px'], t['py']; self.imgs = []
            try:
                for k, v in t['t'].items(): tx, ty = map(int, k.split(',')); im = tk.PhotoImage(data=v); self.imgs.append(im); cv.create_image(tx * 256 - px + 170, ty * 256 - py + 130, anchor='nw', image=im)
            except tk.TclError: cv.create_text(170, 130, text='Map image unsupported by this Tk version')
            for x in p:
                mx, my = sv.project(x['lat'], x['lon'], z); X, Y = mx - px + 170, my - py + 130
                if 8 < X < 332 and 8 < Y < 252: cv.create_oval(X - 9, Y - 9, X + 9, Y + 9, fill=KC[x['kind']], outline='white', width=2); cv.create_text(X, Y, text=x['kind'][0], fill='white', font=(FN, 8, 'bold'))
            cv.create_oval(164, 124, 176, 136, fill=NAVY, outline='white', width=2); cv.create_text(6, 252, text='© OpenStreetMap contributors', anchor='w', font=(FN, 7))
        if a['id'] in self.tl: draw(self.tl[a['id']])
        else: self.bg(lambda: sv.tiles(a['lat'], a['lon']), lambda t, er: (self.tl.__setitem__(a['id'], t), draw(t)) if t else (cv.winfo_exists() and cv.create_text(170, 150, text='Map tiles unavailable', fill=BAD)))
        r = self.row(c)
        for k, col in KC.items(): tk.Label(r, text='● ' + k.split(' ')[0], fg=col, bg=CARD, font=(FN, 8, 'bold')).pack(side='left', padx=4)
        saved = {(s['name'], s['kind']) for s in self.db.q('SELECT name,kind FROM saved_places WHERE user_id=?', (self.uid,))}
        for k in KC:
            items = [x for x in p if x['kind'] == k]; self.lab(box, '  ' + k + 's' if not k.startswith('Shelter') else '  ' + k, 12, True)
            if not items: c = self.card(box); self.lab(c, 'None mapped within 7 km on OpenStreetMap.', 9, fg=MUT)
            for x in items[:4]:
                c = self.card(box); self.lab(c, x['name'], 11, True); self.lab(c, f"{x['dist']} km away", 9, fg=MUT); r = self.row(c)
                self.btn(r, '🗺 Map', lambda x=x: webbrowser.open(f"https://www.openstreetmap.org/?mlat={x['lat']}&mlon={x['lon']}#map=17/{x['lat']}/{x['lon']}"), TEAL)
                self.btn(r, '🧭 Route', lambda x=x: webbrowser.open(f"https://www.openstreetmap.org/directions?from={a['lat']},{a['lon']}&to={x['lat']},{x['lon']}"), NAVY)
                self.btn(r, 'Saved ✓' if (x['name'], x['kind']) in saved else 'Save', lambda x=x: self.save_place(x), GREY)

    def save_place(self, x):
        if not self.db.one('SELECT 1 FROM saved_places WHERE user_id=? AND name=? AND kind=?', (self.uid, x['name'], x['kind'])): self.db.x('INSERT INTO saved_places(user_id,name,kind,lat,lon) VALUES(?,?,?,?,?)', (self.uid, x['name'], x['kind'], x['lat'], x['lon']))
        self.go('places')

    # ---------- News ----------
    def v_news(self, b):
        a = self.area; c = self.card(b); self.lab(c, 'RAAH Brief — disaster news', 14, True)
        self.lab(c, 'Live headlines from publishers via Google News RSS. Tap to read the full story on the publisher’s website.', 8, fg=MUT); r = self.row(c)
        sc = ttk.Combobox(r, values=['Your area', 'Top India'], state='readonly', width=11); sc.set(self.nscope); sc.pack(side='left', padx=2)
        sr = ttk.Combobox(r, values=list(sv.SITES), state='readonly', width=15); sr.set(self.nsrc); sr.pack(side='left', padx=2)
        def apply(ev=None): self.nscope, self.nsrc = sc.get(), sr.get(); self.go('news')
        sc.bind('<<ComboboxSelected>>', apply); sr.bind('<<ComboboxSelected>>', apply)
        box = tk.Frame(b, bg=BG); box.pack(fill='x'); self.lab(box, '⏳ Loading news…', 10, fg=MUT); place = a['name'] if self.nscope == 'Your area' else ''
        def done(items, note):
            for w in box.winfo_children(): w.destroy()
            if items is None: return self.lab(box, 'News unavailable. Check internet.\n' + str(note), 10, fg=BAD)
            if note: self.lab(box, '  ' + note, 8, fg=WARN)
            if not items: self.lab(box, '  No disaster-related stories found in the last 7 days for this filter.', 10, fg=MUT)
            for it in items:
                c = self.card(box); r = self.row(c); self.chip(r, (it['source'] or 'News').upper()[:28], TEAL); tk.Label(r, text=ago(it['ts']), bg=CARD, fg=MUT, font=(FN, 8)).pack(side='left', padx=4)
                self.lab(c, it['title'], 10, True); self.btn(c, 'Read full story ↗', lambda u=it['link']: webbrowser.open(u), NAVY)
        self.fetch(f"news:{place}:{self.nsrc}", lambda: sv.news(place, self.nsrc), 900, done)

    # ---------- Reports (stored in local SQLite) ----------
    def v_reports(self, b):
        a = self.area; c = self.card(b); self.lab(c, 'Community reports', 14, True)
        self.lab(c, 'Report what you see. Reports are saved on this device and always shown as UNVERIFIED. Only your area name is stored — not exact location.', 8, fg=MUT)
        tp = ttk.Combobox(c, values=['Flood', 'Waterlogging', 'Fire', 'Cyclone / storm damage', 'Landslide', 'Road block', 'Power outage', 'Other'], state='readonly'); tp.set('Flood'); tp.pack(fill='x', pady=2)
        sv_ = ttk.Combobox(c, values=['Low', 'Moderate', 'High'], state='readonly'); sv_.set('Moderate'); sv_.pack(fill='x', pady=2)
        tx = tk.Text(c, height=3, font=(FN, 10), relief='solid', bd=1); tx.pack(fill='x', pady=3)
        def post():
            t = tx.get('1.0', 'end').strip()
            if len(t) < 5: return messagebox.showwarning('RAAH', 'Describe what you see (at least a few words).')
            self.db.x('INSERT INTO reports(user_id,area,type,severity,text,created) VALUES(?,?,?,?,?,?)', (self.uid, a['name'], tp.get(), sv_.get(), t, datetime.datetime.now().isoformat(timespec='minutes'))); self.go('reports')
        self.btn(c, '📣 Post report', post)
        rs = self.db.q('SELECT r.*,u.un FROM reports r JOIN users u ON u.id=r.user_id ORDER BY r.id DESC LIMIT 30')
        if not rs: c = self.card(b); self.lab(c, 'No reports yet.', 9, fg=MUT)
        for x in rs:
            c = self.card(b); r = self.row(c); self.chip(r, x['type'].upper(), TEAL); self.chip(r, x['severity'].upper(), LV[x['severity']]); self.chip(r, 'COMMUNITY · ' + x['status'], WARN)
            self.lab(c, x['text'], 10); self.lab(c, f"📍 {x['area']} area · @{x['un']} · {x['created'].replace('T', ' ')}", 8, fg=MUT)
            if x['user_id'] == self.uid: self.btn(c, '🗑 Delete', lambda i=x['id']: (self.db.x('DELETE FROM reports WHERE id=?', (i,)), self.go('reports')), GREY)

    # ---------- SOS + family contacts ----------
    def dial(self, name, num):
        messagebox.showinfo('Calling', f'Calling {name}\n{num}\n(On a PC this opens your calling app if one is installed.)')
        try: webbrowser.open('tel:' + ''.join(ch for ch in num if ch.isdigit() or ch == '+'))
        except Exception: pass

    def v_sos(self, b):
        c = self.card(b, ACC); self.lab(c, '🚨 In danger? Call', 13, True, 'white'); r = self.row(c)
        for n, t in NUMS: self.btn(r, f'{n}', lambda n=n, t=t: self.dial(t, n), 'white', ACC)
        self.lab(c, '112 Emergency · 100 Police · 101 Fire · 108 Ambulance · 1078 Disaster Mgmt', 8, fg='white')
        c = self.card(b); self.lab(c, 'My family emergency contacts', 12, True); self.lab(c, '🔒 Only visible to you (stored in your local database)', 9, fg=TEAL); self.ce = {}
        for k, t in (('n', 'Name (Mom, Dad…)'), ('r', 'Relationship'), ('p', 'Phone number')):
            self.lab(c, t, 9, fg=MUT); e = tk.Entry(c, font=(FN, 10), relief='solid', bd=1); e.pack(fill='x', pady=(0, 4), ipady=3); self.ce[k] = e
        self.btn(c, '＋ Add contact', self.add_c); cs = self.db.q('SELECT * FROM contacts WHERE user_id=? ORDER BY id', (self.uid,))
        if not cs: c = self.card(b); self.lab(c, 'No contacts yet — add your family’s numbers so you can call them in one tap.', 9, fg=MUT)
        COL = {'SAFE': OK, 'NEEDS HELP': BAD, 'CHECKING IN': WARN, 'UNKNOWN': GREY}
        for x in cs:
            c = self.card(b); r = self.row(c); tk.Label(r, text=f"👤 {x['name']} ({x['rel'] or 'Family'})", font=(FN, 11, 'bold'), bg=CARD).pack(side='left'); self.chip(r, x['status'], COL[x['status']])
            self.lab(c, f"{x['phone']} · status set manually {x['updated'] or '—'}", 9, fg=MUT); r = self.row(c)
            self.btn(r, '📞 Call', lambda x=x: self.dial(x['name'], x['phone']), OK); self.btn(r, '💬 SMS', lambda x=x: webbrowser.open('sms:' + x['phone']), TEAL); self.btn(r, '🗑', lambda i=x['id']: (self.db.x('DELETE FROM contacts WHERE id=?', (i,)), self.go('sos')), GREY)
            r = self.row(c)
            for s in ('SAFE', 'CHECKING IN', 'NEEDS HELP'): self.btn(r, s.title(), lambda s=s, i=x['id']: self.set_st(i, s), COL[s])
        self.lab(b, '  Family status is updated manually after you check with them — RAAH does not track anyone’s location.', 8, fg=MUT)

    def set_st(self, i, s): self.db.x('UPDATE contacts SET status=?,updated=? WHERE id=?', (s, datetime.datetime.now().strftime('%d %b %H:%M'), i)); self.go('sos')

    def add_c(self):
        n, r, p = (self.ce[k].get().strip() for k in 'nrp')
        if not n or sum(ch.isdigit() for ch in p) < 7: return messagebox.showwarning('RAAH', 'Add a name and a valid phone number.')
        self.db.x('INSERT INTO contacts(user_id,name,rel,phone) VALUES(?,?,?,?)', (self.uid, n, r, p)); self.go('sos')

    # ---------- Vault ----------
    def v_vault(self, b):
        kit = self.db.kget(self.uid, 'kit'); c = self.card(b); self.lab(c, '🎒 RAAH Vault — offline kit', 13, True)
        self.lab(c, f"Connection mode: {'OFFLINE (saved data only)' if self.off else 'ONLINE'} · Kit: {kit or 'not downloaded'}", 9, fg=MUT); r = self.row(c)
        self.btn(r, 'Go online' if self.off else 'Test offline mode', self.flip_off); self.btn(r, '⬇ Download offline kit', self.make_kit, TEAL)
        self.lab(c, 'Offline mode shows the last saved forecast, news and places. The kit is a text file you can open without internet.', 8, fg=MUT)
        c = self.card(b); self.lab(c, 'Safety checklist', 12, True); ck = self.db.checks(self.uid); self.vars = []
        for i, t in enumerate(CHK): v = tk.BooleanVar(value=i in ck); tk.Checkbutton(c, text=t, variable=v, bg=CARD, anchor='w', command=lambda i=i: self.db.toggle_check(self.uid, i)).pack(fill='x'); self.vars.append(v)
        pr = self.db.kget(self.uid, 'plans_read', [])
        for k, t in PLANS.items(): c = self.card(b); self.lab(c, k + ' plan', 11, True); self.lab(c, t); self.btn(c, 'Read ✓' if k in pr else 'Mark as read', lambda k=k: self.read_plan(k), TEAL)

    def read_plan(self, k):
        pr = self.db.kget(self.uid, 'plans_read', [])
        if k not in pr: pr.append(k)
        self.db.kset(self.uid, 'plans_read', pr); self.go('vault')

    def flip_off(self): self.off = not self.off; self.go('vault')

    def make_kit(self):
        u, a = self.user, self.area; L = ['RAAH OFFLINE SAFETY KIT', f"Saved: {datetime.datetime.now():%d %b %Y %I:%M %p}", f"Name: {u['name']}  Area: {a['name'] if a else u['area']}", '', 'OFFICIAL NUMBERS'] + [f'  {n} - {t}' for n, t in NUMS]
        L += ['', 'MY EMERGENCY CONTACTS'] + [f"  {x['name']} ({x['rel']}): {x['phone']}" for x in self.db.q('SELECT * FROM contacts WHERE user_id=?', (self.uid,))]
        c = self.db.cget(f"env:{a['id']}") if a else None
        if c:
            e = c[0]; L += ['', f"LAST SAVED FORECAST for {a['name']} (fetched {datetime.datetime.fromtimestamp(c[1]):%d %b %H:%M}) - source Open-Meteo"]
            for i, d in enumerate(e['daily']): S = rm.scores(rm.hazards(e, i, self.ctx())); L.append(f"  {d['date']}: {wxn(d['code'])[0]}, {d['tmin']:.0f}-{d['tmax']:.0f}C, rain {d['rain']:.0f}mm, gust {d['gust']:.0f}km/h, risk {rm.overall(S)}/100 ({rm.lvl(rm.overall(S))})")
        L += ['', 'SAVED PLACES'] + [f"  {s['kind']}: {s['name']} ({s['lat']:.4f},{s['lon']:.4f})" for s in self.db.q('SELECT * FROM saved_places WHERE user_id=?', (self.uid,))] + ['', 'CHECKLIST'] + [f'  [ ] {t}' for t in CHK]
        for k, t in PLANS.items(): L += ['', k.upper() + ' PLAN', t]
        try: p = os.path.join(HERE, 'offline_kit.txt'); open(p, 'w', encoding='utf-8').write('\n'.join(L))
        except Exception as ex: return messagebox.showerror('RAAH', f'Could not save kit: {ex}')
        self.db.kset(self.uid, 'kit', datetime.datetime.now().strftime('%d %b %H:%M')); messagebox.showinfo('Offline kit saved', f'Saved to:\n{p}'); self.go('vault')

    # ---------- Profile + readiness ----------
    def rdy(self):
        u = self.user; cs = self.db.q('SELECT status FROM contacts WHERE user_id=?', (self.uid,))
        return rm.readiness(sum(1 for k in ('name', 'phone', 'area', 'city', 'state') if u[k]), len(cs), any(x['status'] != 'UNKNOWN' for x in cs), len(self.db.checks(self.uid)),
                            bool(self.db.one('SELECT 1 FROM saved_places WHERE user_id=?', (self.uid,))), bool(self.db.kget(self.uid, 'kit')), len(self.db.kget(self.uid, 'plans_read', [])))

    def v_me(self, b):
        u = self.user; c = self.card(b); tk.Label(c, text=u['emoji'], font=('Segoe UI Emoji', 40), bg=CARD).pack(); self.lab(c, u['name'], 16, True); self.lab(c, '@' + u['un'], 10, fg=MUT)
        self.lab(c, f"📍 {u['area']} area, {u['city']} (approximate area only)", 10); self.lab(c, '🔒 Others never see your phone number or exact location.', 9, fg=TEAL)
        R = self.rdy(); tot = round(sum(x[1] for x in R)); c = self.card(b); self.lab(c, f'Readiness score: {tot} / 100', 13, True); self.meter(c, tot)
        for n, p, m, tip in R:
            r = self.row(c); tk.Label(r, text=n, font=(FN, 9), bg=CARD, anchor='w').pack(side='left'); self.chip(r, f'{p:g}/{m}', OK if p >= m else WARN if p else BAD)
            if p < m: self.lab(c, '→ ' + tip, 8, fg=MUT)
        c = self.card(b); self.lab(c, 'My followed areas', 12, True)
        for a in self.db.areas(self.uid):
            r = self.row(c); tk.Label(r, text=('● ' if a['active'] else '○ ') + f"{a['name']}, {a['admin']}", font=(FN, 9), bg=CARD).pack(side='left')
            self.btn(r, '✕', lambda i=a['id']: (self.db.del_area(self.uid, i), self.show()), GREY, side='right'); self.btn(r, 'Switch', lambda i=a['id']: (self.db.set_active(self.uid, i), setattr(self, 'day', 0), self.show()), TEAL, side='right')
        self.btn(c, '＋ Add / change area', self.pick_area, TEAL)
        c = self.card(b); self.lab(c, 'Database', 12, True); self.lab(c, 'See every table stored in SQLite (users, areas, reports, events, state_exposure, calc_log…).', 9, fg=MUT); self.btn(c, '🗄 Open database viewer', self.db_viewer, NAVY); self.btn(b, 'Log out', self.logout, GREY)


if __name__ == '__main__':
    App().mainloop()

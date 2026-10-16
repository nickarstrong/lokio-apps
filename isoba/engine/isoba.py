"""
Isoba · движок v3 — все 16 карточек каталога из открытых официальных рядов.

    python fetch.py     входы → data/ (FRED без ключа + индекс геополитического риска GPR)
    python isoba.py     расчёт → ../data.json (снимок: его качает приложение по «Обновить»)
                                 ../history.json (каждый рабочий день с 1990: «История по дням», «Разбор любого дня»)
    python verify.py    проверки: детерминизм, схема, «без будущего»

Правила:
  · Без будущего. Каждый вход — перцентиль 0–100 своей истории ДО этого дня; ряд виден в день публикации (lag_days в sources.csv).
  · Детерминизм. Одни входы → один выход байт в байт: время запуска не участвует, последний день = последний день данных.
  · Только открытые ряды. Nasdaq и NBER — только чтобы посчитать «как часто бывало» для «Что впереди»; в приложение не идут.

Приборы (зона считается по показанному целому числу):
  DSI 0–100           координата долларовой системы, F1–F8          слабый < 35 · нейтрально < 65 · сильный
  Кризисометр 0–100   стресс, который уже есть, 4 лампы              спокойно < 25 · умеренно < 50 · напряжение < 75 · стресс
  Риск вершины 0–100  аналог Bear Market Risk Indicator GS (2017)   спокойно < 60 · поздний цикл < 75 · перегрев
  Риск рецессии 0–100 5 опережающих признаков                       низкий < 50 · средний < 65 · высокий
"""
import json, math, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('ISOBA_DATA', os.path.join(HERE, 'data'))
OUT = os.environ.get('ISOBA_OUT', os.path.dirname(HERE))       # isoba/ — отдаёт GitHub Pages
CUT = os.environ.get('ISOBA_CUTOFF')                          # verify.py: отрезать все ряды по дате наблюдения
SRC = pd.read_csv(os.path.join(HERE, 'sources.csv'))
LIT = 80                 # лампа горит с 80-го перцентиля
RECENT = 130             # рабочих дней в data.json (≈ 6 мес.): мини-графики, «за неделю», «за месяц»
HIST_FROM, DSI_FROM = '1990-01-01', '2006-01-01'

ZONES = {'dsi': [(35, 'weak'), (65, 'neutral'), (101, 'strong')],
         'crisis': [(25, 'calm'), (50, 'moderate'), (75, 'tension'), (101, 'stress')],
         'top': [(60, 'calm'), (75, 'late'), (101, 'overheat')],
         'rec': [(50, 'low'), (65, 'medium'), (101, 'high')]}
DSI_W = {'F3': 0.40, 'F1': 0.20, 'F7': 0.15, 'F2': 0.10, 'F6': 0.05, 'F4': 0.10}   # F4 (сырьё) — обратно: 100 − F4
F_IN = {'F1': ['real_rate', 'curve_flat', 'qt', 'm2_slow'], 'F2': ['rates_vol', 'cp_risk', 'funding'],
        'F3': ['usd_level', 'usd_mom', 'real_yield'], 'F4': ['oil', 'cmdty', 'breakeven'], 'F5': ['claims', 'sahm'],
        'F6': ['gpr', 'epu'], 'F7': ['em_mom', 'em_level'], 'F8': ['credit', 'nfci']}


def r0(x):
    """Округление «как в школе» (0.5 → вверх) — одинаково везде, без банковского округления."""
    return None if x is None or pd.isna(x) else int(math.floor(float(x) + 0.5))


def zone(kind, v):
    return next(n for t, n in ZONES[kind] if v < t)


def series(r):
    path = os.path.join(DATA, r.file)
    if r.url == 'gpr':
        x = pd.read_excel(path).dropna(subset=['DAY', 'GPRD'])
        s = pd.Series(pd.to_numeric(x['GPRD'], errors='coerce').values, index=pd.to_datetime(x['DAY'].astype(int).astype(str), format='%Y%m%d'))
    else:
        df = pd.read_csv(path)
        s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors='coerce').values, index=pd.to_datetime(df.iloc[:, 0]))
    s = s.dropna().sort_index()
    s = s[~s.index.duplicated(keep='last')]
    if CUT:
        s = s[s.index <= CUT]
    if r.url == 'gpr':
        s = s.rolling(30, min_periods=10).mean().dropna()        # шум одного дня новостей сглажен месяцем
    s.index = s.index + pd.Timedelta(days=int(r.lag_days))      # видно в день публикации, не в день наблюдения
    return s


def load():
    raw = {r.id: series(r) for r in SRC.itertuples()}
    daily = [r for r in SRC.itertuples() if r.freq == 'D' and int(r.lag_days) == 1]
    end = max(raw[r.id].index[-1] for r in daily)                 # день, когда виден последний рыночный день
    if end.dayofweek >= 5:
        end = end + pd.offsets.BDay(1)                            # данные пятницы — в понедельник
    asof = max(raw[r.id].index[-1] - pd.Timedelta(days=1) for r in daily)
    for new, old in [('DTWEXBGS', 'DTWEXB'), ('DTWEXEMEGS', 'DTWEXO')]:   # доллар до 2006 — старые индексы ФРС H.10
        n, o = raw[new], raw.pop(old)
        raw[new] = pd.concat([o[o.index < n.index[0]] * n.iloc[0] / o[o.index <= n.index[0]].iloc[-1], n])
    idx = pd.bdate_range('1985-01-01', end)
    lim = {'D': 10, 'W': 20, 'M': 70, 'Q': 200}
    freq = SRC.set_index('id').freq
    d = pd.DataFrame({k: v.reindex(idx, method='ffill', limit=lim[freq[k]]) for k, v in raw.items()}, index=idx)
    lag = SRC.set_index('id').lag_days
    last = {k: (v.index[-1] - pd.Timedelta(days=int(lag[k]))).strftime('%Y-%m-%d') for k, v in raw.items()}
    return d, asof, last


def pct(x, min_obs=500):
    """Перцентиль 0–100 значения среди всей истории ряда до этого дня."""
    return x.expanding(min_periods=min_obs).rank(pct=True) * 100


def yoy(x):
    return (x / x.shift(260) - 1) * 100


def dsi_block(d):
    core = yoy(d.CPILFESL)
    f = pd.DataFrame({
        'real_rate': pct(d.DFF - core), 'curve_flat': pct(-d.T10Y2Y),
        'qt': pct(-(d.WALCL / d.WALCL.shift(130) - 1)), 'm2_slow': pct(-yoy(d.M2SL)),
        'rates_vol': pct(d.DGS10.diff().rolling(21).std()), 'cp_risk': pct(d.RIFSPPNA2P2D90NB - d.DCPN3M), 'funding': pct(d.DCPF3M - d.DTB3),
        'usd_level': pct(d.DTWEXBGS), 'usd_mom': pct(d.DTWEXBGS / d.DTWEXBGS.shift(63) - 1), 'real_yield': pct(d.DFII10),
        'oil': pct(yoy(d.DCOILWTICO)), 'cmdty': pct(yoy(d.PALLFNFINDEXM)), 'breakeven': pct(d.T5YIE),
        'claims': pct(d.ICSA / d.ICSA.rolling(260).min() - 1), 'sahm': pct(d.SAHMREALTIME),
        'gpr': pct(d.GPR), 'epu': pct(d.USEPUINDXD.rolling(30).mean()),
        'em_mom': pct(d.DTWEXEMEGS / d.DTWEXEMEGS.shift(63) - 1), 'em_level': pct(d.DTWEXEMEGS),
        'credit': pct(d.HQMCB10YR - d.DGS10), 'nfci': pct(d.NFCI)}, index=d.index)
    f = f.ewm(span=10).mean().where(f.notna())       # недельное сглаживание, как у остальных приборов: зона не мигает
    F = pd.DataFrame({
        'F1': f[F_IN['F1']].mean(axis=1), 'F2': f[F_IN['F2']].mean(axis=1),
        'F3': f.usd_level * 0.5 + f.usd_mom * 0.3 + f.real_yield * 0.2,
        'F4': f[F_IN['F4']].mean(axis=1), 'F5': f[F_IN['F5']].mean(axis=1),
        'F6': f.gpr * 0.6 + f.epu * 0.4, 'F7': f.em_mom * 0.6 + f.em_level * 0.4,
        'F8': f[F_IN['F8']].mean(axis=1)}, index=d.index)
    F.loc[F.index < DSI_FROM, :] = np.nan
    dsi = sum(F[k] * w for k, w in DSI_W.items() if k != 'F4') + (100 - F['F4']) * DSI_W['F4']
    return f, F, dsi


def lamp_blocks(d):
    ch = d.QCNPAM770A
    top = pd.DataFrame({
        'unemployment_low': pct(-d.UNRATE), 'factories_peak': pct(d.GACDFSA066MSFRBPHI), 'core_inflation': pct(yoy(d.CPILFESL)),
        'curve_flat': (pct(-d.T10Y2Y) + pct(-d.T10Y3M)) / 2, 'market_expensive': pct(d.NCBEILQ027S / d.GDP)})
    crisis = pd.DataFrame({
        'credit_funding': pd.concat([pct(d.NFCICREDIT), pct(d.HQMCB10YR - d.DGS10), pct(d.RIFSPPNA2P2D90NB - d.DCPN3M), pct(d.KCFSI)], axis=1).mean(axis=1),
        'banks_tighten': pct(d.DRTSCILM),
        'jobs_claims': pd.concat([pct(d.ICSA / d.ICSA.rolling(260).min() - 1), pct(yoy(d.CCSA)), pct(d.SAHMREALTIME)], axis=1).mean(axis=1),
        'economy_weak': pd.concat([pct(-d.CFNAI), pct(-yoy(d.NEWORDER)), pct(-yoy(d.PERMIT))], axis=1).mean(axis=1)})
    rec = pd.DataFrame({
        'curve_inverted': pct(-d.T10Y3M), 'banks_tighten': pct(d.DRTSCILM), 'permits_down': pct(-yoy(d.PERMIT)),
        'claims_up': pct(yoy(d.CCSA)), 'real_rate_high': pct(d.DFF - yoy(d.CPILFESL))})
    ctx = pd.DataFrame({
        'oil_up': pct(yoy(d.DCOILWTICO)), 'dollar_up': pct(d.DTWEXBGS / d.DTWEXBGS.shift(63) - 1),
        'china_credit': pct(-((ch - ch.shift(260)) - (ch.shift(260) - ch.shift(520))))})
    dial = lambda L: L.mean(axis=1).ewm(span=10).mean()     # недельное сглаживание: один шумный день не двигает зону
    return {'top': top, 'crisis': crisis, 'rec': rec, 'context': ctx}, dial(top), dial(crisis), dial(rec)


def odds(d, top, rec):
    """Как часто бывало: событие в ближайшие 12 мес. в той же зоне прибора против обычного."""
    idx = d.index[d.index >= '1995-01-01']
    nq = d.NASDAQCOM.reindex(idx)
    near = (nq / nq.rolling(252, min_periods=60).max() - 1) >= -0.05          # рынок у максимума
    f12 = nq[::-1].rolling(252, min_periods=20).min()[::-1].shift(-1)
    y = ((f12 / nq - 1) <= -0.20).astype(float); y[f12.isna()] = np.nan       # Nasdaq ниже на 20 %+ в ближайшие 12 мес.
    t = top.reindex(idx)
    out = {'top': {'usual': r0(y.where(near).mean() * 100)}, 'rec': {}}
    for a, b in [(0, 60), (60, 75), (75, 101)]:
        out['top'][zone('top', a)] = r0(y[near & (t >= a) & (t < b)].mean() * 100)
    ir = d.index[d.index >= '1990-01-01']
    us = d.USREC.reindex(ir).ffill().fillna(0)
    nx = (us.diff() > 0)[::-1].rolling(260, min_periods=1).max()[::-1].shift(-1)
    yr = ((nx > 0) & (us == 0)).astype(float)
    yr[ir > ir[-1] - pd.Timedelta(days=380)] = np.nan; yr[us == 1] = np.nan  # рецессия США начнётся в ближайшие 12 мес.
    rr = rec.reindex(ir)
    out['rec']['usual'] = r0(yr.mean() * 100)
    for a, b in [(0, 50), (50, 65), (65, 101)]:
        out['rec'][zone('rec', a)] = r0(yr[(rr >= a) & (rr < b) & yr.notna()].mean() * 100)
    return out


def since(ints, kind, dates):
    """Дата, с которой прибор в текущей зоне (по последним RECENT дням; None — дольше)."""
    z = zone(kind, ints[-1])
    for i in range(len(ints) - 2, -1, -1):
        if ints[i] is None or zone(kind, ints[i]) != z:
            return dates[i + 1]
    return None


def changes(R, lamps, dates):
    """«Что изменилось» за неделю (5 рабочих дней): до 3 событий; текст — в приложении по ключу k (22 языка)."""
    ev = []
    for card in ['dsi', 'crisis', 'rec', 'top']:
        v1, v0 = R[card][-1], R[card][-6]
        if zone(card, v1) != zone(card, v0):
            ev.append((100, card, {'k': 'zone', 'card': card, 'from': zone(card, v0), 'to': zone(card, v1), 'v0': v0, 'v1': v1}))
        elif abs(v1 - v0) >= 5:
            ev.append((abs(v1 - v0) * 4, card, {'k': 'move', 'card': card, 'v0': v0, 'v1': v1}))
    r1, r0_ = R['rate'][-1], R['rate'][-6]
    if abs(r1 - r0_) >= 0.1:
        ev.append((90, 'rate', {'k': 'rate', 'v0': r0_, 'v1': r1, 'f': 'F1', 'df': R['F1'][-1] - R['F1'][-6]}))
    for g, L in lamps.items():
        for k in L.columns:
            now, was = L[k].iloc[-1], L[k].iloc[-6]
            if pd.notna(now) and pd.notna(was) and (now >= LIT) != (was >= LIT):
                ev.append((60, f'{g}.{k}', {'k': 'lamp', 'id': f'{g}.{k}', 'on': bool(now >= LIT), 'v': r0(now)}))
    for F in F_IN:
        dv = R[F][-1] - R[F][-6]
        if abs(dv) >= 8 and not (F == 'F1' and any(e[1] == 'rate' for e in ev)):
            ev.append((abs(dv) * 2, F, {'k': 'filter', 'f': F, 'v0': R[F][-6], 'v1': R[F][-1]}))
    ev.sort(key=lambda e: -e[0])                                   # стабильная сортировка: при равенстве — порядок выше
    out, cards = [], set()
    for _, c, e in ev:
        if c not in cards and len(out) < 3:
            out.append(e); cards.add(c)
    lit = [f'{g}.{k}' for g, L in lamps.items() for k in L.columns if pd.notna(L[k].iloc[-1]) and L[k].iloc[-1] >= LIT]
    for card in ['crisis', 'dsi', 'rate']:                          # тихая неделя: что стоит на месте — тоже новость
        if len(out) < 3 and card not in cards:
            if card == 'rate':
                moved = [i for i in range(1, len(R['rate'])) if abs(R['rate'][i] - R['rate'][i - 1]) >= 0.1]
                e = {'k': 'steady', 'card': 'rate', 'v': R['rate'][-1], 'since': dates[moved[-1]] if moved else None}
            else:
                e = {'k': 'steady', 'card': card, 'v': R[card][-1], 'm1': R[card][-1] - R[card][-22]}
            if card == 'crisis':
                e['lit'] = lit
            out.append(e); cards.add(card)
    return out


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    d, asof, last = load()
    f, F, dsi = dsi_block(d)
    lamps, top, crisis, rec = lamp_blocks(d)
    od = odds(d, top, rec)
    usd, rate = d.DTWEXBGS, d.DFF
    dial = {'dsi': dsi, 'crisis': crisis, 'top': top, 'rec': rec}

    # последние RECENT дней — для мини-графиков и изменений
    tail = d.index[-RECENT:]
    dates = [x.strftime('%Y-%m-%d') for x in tail]
    R = {k: [r0(v) for v in s.reindex(tail)] for k, s in dial.items()}
    R.update({k: [r0(v) for v in F[k].reindex(tail)] for k in F_IN})
    R['usd'] = [round(float(v), 1) for v in usd.reindex(tail)]
    R['rate'] = [round(float(v), 2) for v in rate.reindex(tail)]
    now = {k: R[k][-1] for k in dial}
    w1 = lambda k: R[k][-6]
    m1 = lambda k: R[k][-22]
    q1 = lambda k: R[k][-64]

    parts = {k: [r0(F[k].iloc[-1]), DSI_W[k], round((100 - F[k].iloc[-1] if k == 'F4' else F[k].iloc[-1]) * DSI_W[k], 1)] for k in DSI_W}
    data = {
        'v': 3,
        'asof': asof.strftime('%Y-%m-%d'),
        'dsi': {'v': now['dsi'], 'zone': zone('dsi', now['dsi']), 'since': since(R['dsi'], 'dsi', dates),
                'w1': w1('dsi'), 'm1': m1('dsi'), 'parts': parts},
        'crisis': {'v': now['crisis'], 'zone': zone('crisis', now['crisis']), 'since': since(R['crisis'], 'crisis', dates),
                   'w1': w1('crisis'), 'm1': m1('crisis'),
                   'lamps': {k: [r0(v), bool(v >= LIT)] for k, v in lamps['crisis'].iloc[-1].items()}},
        'ahead': {k: {'v': now[k], 'zone': zone(k, now[k]), 'now': od[k][zone(k, now[k])], 'usual': od[k]['usual'],
                      'zones': {z: p for z, p in od[k].items() if z != 'usual'},
                      'lamps': {n: [r0(v), bool(v >= LIT)] for n, v in lamps[k].iloc[-1].items()}} for k in ['top', 'rec']},
        'context': {k: [r0(v), bool(v >= LIT)] for k, v in lamps['context'].iloc[-1].items()},
        'changes': changes(R, lamps, dates),
        'filters': {k: {'v': R[k][-1], 'w1': w1(k), 'm1': m1(k), 'in': {n: r0(f[n].iloc[-1]) for n in F_IN[k]}} for k in F_IN},
        'fed': {'usd': {'v': R['usd'][-1], 'q1': R['usd'][-64]}, 'rate': {'v': R['rate'][-1], 'q1': R['rate'][-64]},
                'crisis': {'v': now['crisis'], 'm1': m1('crisis')}},
        'recent': {'d0': dates[0], 'n': len(dates), **{k: R[k] for k in ['dsi', 'crisis', 'top', 'rec', *F_IN, 'usd', 'rate']}},
        'data_through': {k: v for k, v in last.items() if SRC.set_index('id').use[k] != 'odds'},
        'sources': {r.id: r.license for r in SRC.itertuples()},
    }

    hidx = d.index[d.index >= HIST_FROM]
    col = lambda s: [r0(v) for v in s.reindex(hidx)]
    hist = {'v': 3, 'asof': data['asof'], 'd0': hidx[0].strftime('%Y-%m-%d'), 'n': len(hidx), 'days': 'Mon-Fri',
            **{k: col(s) for k, s in dial.items()}, **{k: col(F[k]) for k in F_IN},
            'lamps': {f'{g}.{k}': col(L[k]) for g, L in lamps.items() for k in L.columns}}

    os.makedirs(OUT, exist_ok=True)
    for name, obj in [('data.json', data), ('history.json', hist)]:
        with open(os.path.join(OUT, name), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(obj, fh, ensure_ascii=False, separators=(',', ':'))
            fh.write('\n')
    print(f"данные на {data['asof']} · DSI {now['dsi']} {data['dsi']['zone']} · кризисометр {now['crisis']} {data['crisis']['zone']} · "
          f"вершина {now['top']} {data['ahead']['top']['zone']} ({data['ahead']['top']['now']} % / {data['ahead']['top']['usual']} %) · "
          f"рецессия {now['rec']} {data['ahead']['rec']['zone']} ({data['ahead']['rec']['now']} % / {data['ahead']['rec']['usual']} %)")
    print('F1–F8', {k: R[k][-1] for k in F_IN}, '· доллар', R['usd'][-1], '· ставка', R['rate'][-1])
    print('изменилось', json.dumps(data['changes'], ensure_ascii=False))


if __name__ == '__main__':
    main()

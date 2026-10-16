"""
Isoba · проверки движка. Зелёный (код 0) — данные можно коммитить.

    python verify.py

1. Детерминизм: два запуска на одних входах дают байт-в-байт одинаковые data.json и history.json.
2. Схема и смысл data.json: все 16 карточек, числа 0–100, зона = порог по показанному числу, вклады DSI складываются в DSI.
3. Без будущего: расчёт на рядах, обрезанных по 31.12.2019, совпадает с полным расчётом во всех днях до этой даты.
4. Свежесть входов — предупреждения (не ошибка: задержка публикации у ведомства не должна останавливать обновление).
"""
import json, os, subprocess, sys, tempfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import isoba                                                       # noqa: E402  (пороги и ключи — из движка, не копией)

CUTOFF = '2019-12-31'
errors, warns = [], []


def run(out, **env):
    e = dict(os.environ, ISOBA_OUT=out, **env)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'isoba.py')], env=e, capture_output=True, text=True, encoding='utf-8')
    if r.returncode:
        print(r.stdout, r.stderr)
        sys.exit('движок упал')
    return {n: open(os.path.join(out, n), 'rb').read() for n in ('data.json', 'history.json')}


def need(cond, msg):
    if not cond:
        errors.append(msg)


def dial(name, kind, x):
    need(isinstance(x.get('v'), int) and 0 <= x['v'] <= 100, f'{name}.v вне 0–100: {x.get("v")}')
    if isinstance(x.get('v'), int):
        need(x.get('zone') == isoba.zone(kind, x['v']), f'{name}: зона {x.get("zone")} не совпадает с числом {x["v"]}')


def schema(d):
    need(d.get('v') == 3, 'версия схемы не 3')
    date.fromisoformat(d['asof'])
    dial('dsi', 'dsi', d['dsi']); dial('crisis', 'crisis', d['crisis'])
    parts = d['dsi']['parts']
    need(set(parts) == set(isoba.DSI_W), f'вклады DSI: {sorted(parts)}')
    need(abs(sum(p[2] for p in parts.values()) - d['dsi']['v']) <= 1, f'вклады DSI {sum(p[2] for p in parts.values()):.1f} ≠ DSI {d["dsi"]["v"]}')
    need(len(d['crisis']['lamps']) == 4, 'кризисометр: не 4 лампы')
    for k in ('top', 'rec'):
        a = d['ahead'][k]
        dial(f'ahead.{k}', k, a)
        need(a['now'] == a['zones'].get(a['zone']), f'ahead.{k}: «сейчас» не из своей зоны')
        need(set(a['zones']) == {n for _, n in isoba.ZONES[k]}, f'ahead.{k}: зоны {sorted(a["zones"])}')
        need(all(isinstance(v, int) and 0 <= v <= 100 for v in [a['usual'], *a['zones'].values()]), f'ahead.{k}: частоты вне 0–100')
    ch = d['changes']
    need(1 <= len(ch) <= 3, f'«Что изменилось»: {len(ch)} строк')
    need(all(c['k'] in {'zone', 'move', 'rate', 'lamp', 'filter', 'steady'} for c in ch), '«Что изменилось»: неизвестный вид')
    need(set(d['filters']) == set(isoba.F_IN), 'фильтры: не F1–F8')
    for k, f in d['filters'].items():
        need(isinstance(f['v'], int) and 0 <= f['v'] <= 100, f'{k} вне 0–100')
        need(set(f['in']) == set(isoba.F_IN[k]), f'{k}: входы {sorted(f["in"])}')
    need(d['fed']['usd']['v'] > 50 and 0 <= d['fed']['rate']['v'] < 25, f'ряды ФРС странные: {d["fed"]}')
    r = d['recent']
    for k in ['dsi', 'crisis', 'top', 'rec', *isoba.F_IN, 'usd', 'rate']:
        need(len(r[k]) == r['n'] == isoba.RECENT, f'recent.{k}: длина {len(r[k])}')
        need(None not in r[k], f'recent.{k}: пропуски')
    ids = {row.id for row in isoba.SRC.itertuples() if row.use != 'odds'} - {'DTWEXB', 'DTWEXO'}
    need(ids <= set(d['data_through']), f'data_through без {sorted(ids - set(d["data_through"]))}')
    asof = date.fromisoformat(d['asof'])
    allow = {'D': 10, 'W': 21, 'M': 75, 'Q': 130}
    for row in isoba.SRC.itertuples():
        if row.id in d['data_through']:
            age = (asof - date.fromisoformat(d['data_through'][row.id])).days - int(row.lag_days)
            if age > allow[row.freq]:
                warns.append(f'{row.id}: последнее наблюдение {d["data_through"][row.id]} — задержка {age} дн. сверх обычной')
    return asof


def history(h, d):
    need(h['asof'] == d['asof'] and h['d0'] == isoba.HIST_FROM, 'history: дата или начало')
    keys = ['dsi', 'crisis', 'top', 'rec', *isoba.F_IN]
    for k in keys:
        need(len(h[k]) == h['n'], f'history.{k}: длина')
        need(all(v is None or 0 <= v <= 100 for v in h[k]), f'history.{k}: вне 0–100')
    for k, a in h['lamps'].items():
        need(len(a) == h['n'], f'history.lamps.{k}: длина')
    for k in ['dsi', 'crisis']:
        need(h[k][-1] == d[k]['v'], f'history.{k} последний ≠ data.json')
    need(h['top'][-1] == d['ahead']['top']['v'] and h['rec'][-1] == d['ahead']['rec']['v'], 'history: вершина/рецессия ≠ data.json')


def no_future(full, cut):
    n = cut['n']
    need(n < full['n'], 'обрезанный расчёт не короче полного')
    for k in ['dsi', 'crisis', 'top', 'rec', *isoba.F_IN]:
        diff = [i for i in range(n) if full[k][i] != cut[k][i]]
        need(not diff, f'{k}: будущее влияет на прошлое — {len(diff)} дн. расходятся (первый №{diff[0] if diff else 0})')
    for k in full['lamps']:
        diff = sum(full['lamps'][k][i] != cut['lamps'][k][i] for i in range(n))
        need(not diff, f'лампа {k}: будущее влияет на прошлое — {diff} дн.')


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as c:
        A, B = run(a), run(b)
        need(A == B, 'не детерминирован: два запуска дали разные файлы')
        d, h = json.loads(A['data.json']), json.loads(A['history.json'])
        schema(d)
        history(h, d)
        C = run(c, ISOBA_CUTOFF=CUTOFF)
        no_future(h, json.loads(C['history.json']))
    print(f"данные на {d['asof']} · data.json {len(A['data.json']) // 1024} КБ · history.json {len(A['history.json']) // 1024} КБ")
    for w in warns:
        print('предупреждение:', w)
    for e in errors:
        print('ОШИБКА:', e)
    print('VERIFY GREEN' if not errors else f'VERIFY RED · {len(errors)}')
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()

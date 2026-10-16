"""
Isoba · скачать входы в data/ по sources.csv.

    python fetch.py

FRED — без ключа (fredgraph.csv). GPR (Caldara–Iacoviello, CC BY) — ссылка на свежий файл берётся со страницы gpr.htm.
Файл заменяется только целым и проверенным скачиванием: сбой одного ряда не портит старую копию.
Код выхода 1, если хоть один ряд не скачался, — в GitHub Actions это красный запуск, данные в этот день не коммитятся.
"""
import csv, io, os, re, sys, time, urllib.request
from urllib.parse import urljoin

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('ISOBA_DATA', os.path.join(HERE, 'data'))
UA = 'Mozilla/5.0 (isoba-engine; +https://github.com/nickarstrong/lokio-apps)'
FRED = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id='
GPR_PAGE = 'https://www.matteoiacoviello.com/gpr.htm'
GPR_FALLBACK = 'https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls'


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(5 * 3 ** i)                                  # 5, 15, 45 с


def check_csv(body, sid):
    rows = list(csv.reader(io.StringIO(body.decode('utf-8-sig'))))
    head = [c.strip().lower() for c in rows[0]]
    if len(head) != 2 or head[0] not in ('observation_date', 'date') or head[1] != sid.lower():
        raise ValueError(f'заголовок {rows[0]}')
    if len(rows) < 50:
        raise ValueError(f'всего {len(rows) - 1} строк')
    return rows[-1][0]


def gpr():
    page = get(GPR_PAGE).decode('utf-8', 'replace')
    m = re.findall(r'href="([^"]*data_gpr_daily_recent[^"]*\.xls)"', page, re.I)
    body = get(urljoin(GPR_PAGE, m[0]) if m else GPR_FALLBACK)
    if body[:8] != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' or len(body) < 100_000:   # Excel 97–2003 (OLE)
        raise ValueError(f'не похоже на xls, {len(body)} байт')
    return body, 'xls ' + (m[0].rsplit('/', 1)[-1] if m else 'fallback')


def main():
    os.makedirs(DATA, exist_ok=True)
    bad = []
    with open(os.path.join(HERE, 'sources.csv'), encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        try:
            if r['url'] == 'fred':
                body = get(FRED + r['id'])
                last = check_csv(body, r['id'])
            elif r['url'] == 'gpr':
                body, last = gpr()
            else:
                raise ValueError(f"неизвестный источник {r['url']}")
            path = os.path.join(DATA, r['file'])
            with open(path + '.part', 'wb') as fh:
                fh.write(body)
            os.replace(path + '.part', path)
            print(f"ok   {r['id']:<20} {last}")
        except Exception as e:
            bad.append(r['id'])
            print(f"FAIL {r['id']:<20} {e}")
        time.sleep(0.5)                                             # вежливо к FRED
    if bad:
        print('NOT UPDATED:', ' '.join(bad))
        sys.exit(1)
    print('ALL INPUTS UPDATED')


if __name__ == '__main__':
    main()

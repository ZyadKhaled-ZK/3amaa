import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

import os, re, ssl, threading, time, json, urllib.request, urllib.parse
from html import unescape as h
from urllib.request import Request, urlopen, HTTPCookieProcessor, build_opener, HTTPSHandler

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data.parquet')

if not os.path.exists(DATA_PATH):
    print('Downloading data...', flush=True)
    url = 'https://github.com/ZyadKhaled-ZK/3amaa/raw/master/data.parquet'
    urllib.request.urlretrieve(url, DATA_PATH)
    print('Download complete', flush=True)

print('Loading data...', flush=True)
df = pd.read_parquet(DATA_PATH)
df.columns = df.columns.str.strip()
print(f'Loaded {len(df)} records', flush=True)

df['seating_no'] = df['seating_no'].astype(str)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    query = data.get('query', '').strip()
    search_by = data.get('searchBy', 'seating_no')

    if not query:
        return jsonify({'error': 'يرجى إدخال رقم الجلوس أو الاسم'})

    if search_by == 'seating_no':
        result = df[df['seating_no'] == query]
    else:
        result = df[df['arabic_name'].str.contains(query, case=False, na=False, regex=False)]

    if result.empty:
        return jsonify({'error': 'لا توجد نتائج للبحث المطلوب'})

    results = result.to_dict('records')
    for r in results:
        r['seating_no'] = str(r['seating_no'])
        r['percentage'] = round((r['total_degree'] / 320) * 100, 1) if r['total_degree'] else 0
    return jsonify({'results': results, 'count': len(results)})

# ---- subjects from natega.youm7.com with small TTL cache ----
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE
_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 6 * 3600  # 6 hours
_CACHE_MAX = 5000


def _scrape_youm7(seat_no, timeout=25):
    cj = HTTPCookieProcessor()
    op = build_opener(cj, HTTPSHandler(context=_ssl_ctx))
    try:
        op.open(Request('https://natega.youm7.com/',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}), timeout=timeout)
        d = urllib.parse.urlencode({'seating_no': str(seat_no), 'system': '1'}).encode()
        resp = op.open(Request('https://natega.youm7.com/Result/1', data=d, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://natega.youm7.com', 'Referer': 'https://natega.youm7.com/',
        }), timeout=timeout)
        body = resp.read().decode('utf-8', errors='replace')
        r = {'seat': str(seat_no)}
        nm = re.search(r'student-result__name[^>]*>([^<]+)', body)
        if nm:
            r['name'] = h(nm.group(1)).replace('الاسم: ', '').strip()
        sm = re.search(r'حالة الطالب:\s*([^<\n]+)', body)
        if sm:
            r['status'] = sm.group(1).strip()
        st = re.search(r'نوعية التعليم:\s*([^<\n]+)', body)
        if st:
            r['school_type'] = h(st.group(1)).strip()
        bm = re.search(r'الشعبة:\s*([^<\n]+)', body)
        if bm:
            r['branch'] = bm.group(1).strip()
        total_m = re.search(r'summary-value--marks[^>]*>([\d.]+) / ([\d.]+)', body)
        if total_m:
            r['total'] = float(total_m.group(1))
            r['max_marks'] = int(total_m.group(2))
        subjects = []
        table_m = re.search(r'<tbody>(.*?)</tbody>', body, re.DOTALL)
        if table_m:
            rows = re.findall(r'<tr>(.*?)</tr>', table_m.group(1), re.DOTALL)
            for row in rows:
                cols = re.findall(r'<td>(.*?)</td>', row, re.DOTALL)
                cols = [re.sub(r'<[^>]+>', '', h(c)).strip() for c in cols]
                if len(cols) >= 2:
                    subjects.append({'subject': cols[0], 'mark': cols[1], 'pct': cols[2] if len(cols) > 2 else ''})
        r['subjects'] = subjects
        r['ok'] = bool(r.get('name'))
        return r
    except Exception as e:
        return {'seat': str(seat_no), 'ok': False, 'error': str(e)[:200]}


@app.route('/subjects')
def subjects():
    seat = (request.args.get('seat') or '').strip()
    if not seat:
        return jsonify({'error': 'رقم الجلوس مطلوب'})
    now = time.time()
    with _cache_lock:
        cached = _cache.get(seat)
        if cached and now - cached['ts'] < _CACHE_TTL:
            return jsonify(cached['data'])
    res = _scrape_youm7(seat)
    if res.get('ok'):
        with _cache_lock:
            if len(_cache) >= _CACHE_MAX:
                oldest = min(_cache, key=lambda k: _cache[k]['ts'])
                _cache.pop(oldest, None)
            _cache[seat] = {'ts': now, 'data': res}
    return jsonify(res)


@app.route('/tansiq')
def tansiq():
    p = os.path.join(os.path.dirname(__file__), 'tansiq_data.json')
    with open(p, encoding='utf-8') as f:
        return jsonify(json.load(f))


@app.route('/student/<seat>')
def student(seat):
    r = df[df['seating_no'] == str(seat)]
    if r.empty:
        return jsonify({'error': 'لا توجد نتائج'})
    row = r.iloc[0]
    return jsonify({
        'seating_no': str(row['seating_no']),
        'arabic_name': row['arabic_name'],
        'total_degree': int(row['total_degree']),
        'student_case_desc': row['student_case_desc'],
        'percentage': round((row['total_degree'] / 320) * 100, 1) if row['total_degree'] else 0,
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

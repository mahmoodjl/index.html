#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
جمع‌کننده قیمت روز — داشبورد کیمیا مس تابان کویر
================================================
این اسکریپت روی سرور گیت‌هاب (GitHub Actions) اجرا می‌شود، نه داخل مرورگر.
دلیلش این است که مرورگر اجازه نمی‌دهد یک صفحه ساکن، محتوای سایت دیگری را
مستقیم بخواند (CORS). پس قیمت‌ها اینجا گرفته و در فایل prices.json کنار
index.html نوشته می‌شوند و داشبورد همان فایل را می‌خواند.

قاعده حاکم پروژه اینجا هم برقرار است: هیچ عدد فرضی ساخته نمی‌شود.
اگر منبعی خوانده نشد، عدد قبلیِ موفق با زمان خودش نگه داشته می‌شود و
پرچم ok=false می‌خورد تا داشبورد آن را «قدیمی» نشان بدهد.

    python3 fetch_prices.py --out prices.json
"""
import argparse, json, os, re, sys, time
from datetime import datetime, timezone, timedelta

import requests

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/125.0 Safari/537.36')
HDRS = {'User-Agent': UA, 'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8'}
TIMEOUT = 25
SUPPLIER = 'ملی صنایع مس ایران'
LOG = []


def log(*a):
    m = ' '.join(str(x) for x in a)
    LOG.append(m)
    print(m, flush=True)


def get(url, **kw):
    kw.setdefault('headers', HDRS)
    kw.setdefault('timeout', TIMEOUT)
    return requests.get(url, **kw)


def post(url, **kw):
    kw.setdefault('headers', HDRS)
    kw.setdefault('timeout', TIMEOUT)
    return requests.post(url, **kw)


def num(s):
    """عدد از متن — جداکننده هزارگان و ارقام فارسی/عربی را هم می‌فهمد"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s)
    for i, d in enumerate('۰۱۲۳۴۵۶۷۸۹'):
        t = t.replace(d, str(i))
    for i, d in enumerate('٠١٢٣٤٥٦٧٨٩'):
        t = t.replace(d, str(i))
    t = t.replace(',', '').replace('٬', '').replace('،', '').strip()
    m = re.search(r'-?\d+(?:\.\d+)?', t)
    return float(m.group(0)) if m else None


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ---------------------------------------------------------------- تاریخ شمسی
def to_jalali(g: datetime):
    gy, gm, gd = g.year, g.month, g.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    g_day_no += g_d_m[gm2] + gd2
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        g_day_no += 1
    g_day_no -= 79
    j_np = g_day_no // 12053
    g_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (g_day_no // 1461)
    g_day_no %= 1461
    if g_day_no >= 366:
        jy += (g_day_no - 1) // 365
        g_day_no = (g_day_no - 1) % 365
    if g_day_no < 186:
        jm = 1 + g_day_no // 31
        jd = 1 + g_day_no % 31
    else:
        jm = 7 + (g_day_no - 186) // 30
        jd = 1 + (g_day_no - 186) % 30
    return jy, jm, jd


def jstr(g: datetime):
    y, m, d = to_jalali(g)
    return f'{y}/{m:02d}/{d:02d}'


# ================================================================= دلار tgju
def fetch_usd():
    """نرخ دلار آزاد — واحد خروجی: ریال"""
    # ۱) سرویس داده‌ای خود tgju
    for url in ('https://call1.tgju.org/ajax.json',
                'https://call3.tgju.org/ajax.json'):
        try:
            r = get(url)
            if r.ok:
                j = r.json()
                cur = j.get('current') or j
                for key in ('price_dollar_rl', 'dollar', 'price_dollar'):
                    it = cur.get(key)
                    if isinstance(it, dict):
                        v = num(it.get('p') or it.get('price'))
                        if v and v > 100000:
                            log(f'  USD ✓ {url} [{key}] = {v:,.0f} ریال')
                            return {'ok': True, 'rial': v, 'at': now_iso(),
                                    'src': 'tgju.org', 'note': it.get('t') or ''}
        except Exception as e:
            log(f'  USD ✗ {url}: {e}')
    # ۲) خواندن مستقیم از صفحه
    try:
        r = get('https://www.tgju.org/profile/price_dollar_rl')
        if r.ok:
            m = re.search(r'data-price="([\d,\.]+)"', r.text) or \
                re.search(r'<span[^>]*class="[^"]*value[^"]*"[^>]*>\s*([\d,]+)', r.text)
            v = num(m.group(1)) if m else None
            if v and v > 100000:
                log(f'  USD ✓ صفحه پروفایل = {v:,.0f} ریال')
                return {'ok': True, 'rial': v, 'at': now_iso(), 'src': 'tgju.org'}
    except Exception as e:
        log(f'  USD ✗ صفحه پروفایل: {e}')
    log('  USD ✗ هیچ منبعی جواب نداد')
    return {'ok': False, 'at': now_iso(), 'src': 'tgju.org'}


# ================================================================== LME مس
def fetch_lme():
    """قیمت مس LME — دلار بر تن. صفحه عمومی LME یک روز تأخیر دارد."""
    try:
        r = get('https://www.lme.com/api/trading-data/instrument-prices?instrumentId=AH')
        log(f'  LME api probe status={r.status_code}')
    except Exception as e:
        log(f'  LME api probe: {e}')

    for url in ('https://www.lme.com/en/metals/non-ferrous/lme-copper/',
                'https://www.lme.com/metals/non-ferrous/lme-copper'):
        try:
            r = get(url)
            if not r.ok:
                log(f'  LME ✗ {url} status={r.status_code}')
                continue
            t = r.text
            # عدد قیمت معمولاً داخل همان JSON جاسازی‌شده صفحه است
            cands = []
            for m in re.finditer(r'"(?:price|value|closePrice|lastPrice)"\s*:\s*"?([\d,]+\.\d+)"?', t):
                v = num(m.group(1))
                if v and 1000 < v < 60000:
                    cands.append(v)
            if not cands:
                for m in re.finditer(r'>\s*([\d],?[\d]{3}\.\d{2})\s*<', t):
                    v = num(m.group(1))
                    if v and 1000 < v < 60000:
                        cands.append(v)
            if cands:
                v = cands[0]
                chg = None
                mc = re.search(r'"(?:changePercent|percentChange)"\s*:\s*"?(-?[\d.]+)"?', t)
                if mc:
                    chg = num(mc.group(1))
                log(f'  LME ✓ {url} = {v:,.2f} USD/t  (نامزدها: {cands[:5]})')
                return {'ok': True, 'usd_ton': v, 'chg_pct': chg, 'at': now_iso(),
                        'src': 'lme.com', 'delayed': True}
            log(f'  LME ✗ {url}: عددی در صفحه پیدا نشد (طول {len(t)})')
        except Exception as e:
            log(f'  LME ✗ {url}: {e}')
    log('  LME ✗ هیچ منبعی جواب نداد')
    return {'ok': False, 'at': now_iso(), 'src': 'lme.com', 'delayed': True}


# ============================================================ بورس کالا IME
IME_ENDPOINTS = [
    'https://www.ime.co.ir/subsystems/ime/services/home/imedata.asmx/AmareMoamelatList',
    'https://www.ime.co.ir/subsystems/ime/services/home/imedata.asmx/GetAmareMoamelat',
]


def fetch_ime(days=120):
    """
    آمار معاملات بورس کالا برای عرضه‌کننده «ملی صنایع مس ایران» و کالای کاتد مس.
    خروجی: فهرست جلسات با قیمت پایه، میانگین موزون، بالاترین، عرضه، تقاضا، حجم معامله.
    """
    end = datetime.now()
    start = end - timedelta(days=days)
    fmt = lambda d: d.strftime('%Y/%m/%d')
    rows = []
    for ep in IME_ENDPOINTS:
        for payload in (
            {'language': 0, 'fari': False, 'GregorianFromDate': fmt(start),
             'GregorianToDate': fmt(end), 'mainCat': 0, 'cat': 0, 'subCat': 0,
             'producer': 0, 'Producer': 0, 'flow': 0},
            {'Language': 0, 'fari': 'false', 'FromDate': fmt(start), 'ToDate': fmt(end)},
        ):
            try:
                r = post(ep, json=payload)
                log(f'  IME probe {ep.rsplit("/", 1)[-1]} status={r.status_code} len={len(r.text)}')
                if not r.ok:
                    continue
                data = r.json()
                d = data.get('d', data)
                if isinstance(d, str):
                    d = json.loads(d)
                if isinstance(d, dict):
                    d = d.get('Data') or d.get('data') or []
                if not isinstance(d, list) or not d:
                    continue
                log(f'  IME ✓ {len(d)} ردیف خام؛ کلیدهای نمونه: {list(d[0].keys())[:14]}')
                for it in d:
                    blob = json.dumps(it, ensure_ascii=False)
                    if 'کاتد' not in blob:
                        continue
                    if SUPPLIER not in blob:
                        continue
                    rows.append({
                        'date': pick(it, 'date', 'Date', 'ddate', 'DeliveryDate'),
                        'base': num(pick(it, 'BasePrice', 'basePrice', 'GheymatPaye', 'Price')),
                        'avg': num(pick(it, 'arzeh', 'WeightedAvg', 'avgPrice', 'MeanPrice', 'Value')),
                        'high': num(pick(it, 'MaxPrice', 'maxPrice', 'HighPrice')),
                        'supply': num(pick(it, 'arzeh', 'Supply', 'OfferVol', 'ArzeVolume')),
                        'demand': num(pick(it, 'taghaza', 'Demand', 'DemandVol')),
                        'traded': num(pick(it, 'MoamelatVol', 'Volume', 'ContractVolume', 'quantity')),
                        'raw': it,
                    })
                if rows:
                    log(f'  IME ✓ {len(rows)} ردیف کاتد مس از «{SUPPLIER}»')
                    return {'ok': True, 'rows': rows, 'at': now_iso(), 'src': 'ime.co.ir',
                            'supplier': SUPPLIER}
            except Exception as e:
                log(f'  IME ✗ {ep.rsplit("/", 1)[-1]}: {e}')
    log('  IME ✗ هیچ سرویسی داده کاتد مس نداد — ساختار صفحه را باید دوباره بررسی کرد')
    return {'ok': False, 'rows': [], 'at': now_iso(), 'src': 'ime.co.ir', 'supplier': SUPPLIER}


def pick(d, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ''):
            return d[k]
    for k in keys:
        for kk in d:
            if kk.lower() == k.lower() and d[kk] not in (None, ''):
                return d[kk]
    return None


# ==================================================================== اخبار
NEWS_FEEDS = [
    ('https://news.google.com/rss/search?q=copper+price+OR+copper+market+when:7d&hl=en-US&gl=US&ceid=US:en', 'Google News'),
    ('https://news.google.com/rss/search?q=LME+copper+OR+copper+mine+disruption+when:7d&hl=en-US&gl=US&ceid=US:en', 'Google News'),
]
HIGH = ['tariff', 'strike', 'disruption', 'halt', 'force majeure', 'ban', 'sanction',
        'shutdown', 'outage', 'surge', 'plunge', 'record high', 'slump']
MED = ['demand', 'inventory', 'stocks', 'output', 'production', 'smelter', 'treatment charge',
       'forecast', 'deficit', 'surplus', 'china']


def fetch_news(limit=5):
    items, seen = [], set()
    for url, src in NEWS_FEEDS:
        try:
            r = get(url)
            if not r.ok:
                log(f'  NEWS ✗ {src} status={r.status_code}')
                continue
            for m in re.finditer(r'<item>(.*?)</item>', r.text, re.S):
                b = m.group(1)
                t = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', b, re.S)
                l = re.search(r'<link>(.*?)</link>', b, re.S)
                d = re.search(r'<pubDate>(.*?)</pubDate>', b, re.S)
                s = re.search(r'<source[^>]*>(.*?)</source>', b, re.S)
                if not t:
                    continue
                title = re.sub(r'<[^>]+>', '', t.group(1)).strip()
                key = title.lower()[:70]
                if key in seen:
                    continue
                seen.add(key)
                low = title.lower()
                imp = 'high' if any(w in low for w in HIGH) else ('med' if any(w in low for w in MED) else 'low')
                items.append({'title': title, 'url': (l.group(1).strip() if l else ''),
                              'src': (re.sub(r'<[^>]+>', '', s.group(1)).strip() if s else src),
                              'date': (d.group(1).strip() if d else ''), 'impact': imp})
        except Exception as e:
            log(f'  NEWS ✗ {src}: {e}')
    rank = {'high': 0, 'med': 1, 'low': 2}
    items.sort(key=lambda x: rank[x['impact']])
    log(f'  NEWS ✓ {len(items)} خبر — {sum(1 for i in items if i["impact"] == "high")} مهم')
    return items[:limit]


# ===================================================================== main
def merge(old, new, key):
    """اگر منبع تازه خوانده نشد، آخرین مقدار موفق با زمان خودش نگه داشته می‌شود"""
    o = (old or {}).get(key) or {}
    if new.get('ok'):
        return new
    if o.get('ok'):
        o = dict(o)
        o['ok'] = False
        o['stale'] = True
        o['checked'] = now_iso()
        return o
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='prices.json')
    a = ap.parse_args()

    old = {}
    if os.path.exists(a.out):
        try:
            old = json.load(open(a.out, encoding='utf-8'))
        except Exception:
            old = {}

    log('— دلار —');  usd = fetch_usd()
    log('— LME —');   lme = fetch_lme()
    log('— بورس کالا —'); ime = fetch_ime()
    log('— اخبار —'); news = fetch_news()

    out = {
        'built': now_iso(),
        'builtJalali': jstr(datetime.now()),
        'usd': merge(old, usd, 'usd'),
        'lme': merge(old, lme, 'lme'),
        'ime': merge(old, ime, 'ime'),
        'news': news if news else (old.get('news') or []),
        'log': LOG[-60:],
    }

    # تاریخچه: هر اجرا یک نقطه، حداکثر ۲۰۰۰ نقطه نگه داشته می‌شود
    hist = old.get('hist') or []
    point = {'t': out['built'], 'j': out['builtJalali']}
    if out['usd'].get('rial'):
        point['usd'] = out['usd']['rial']
    if out['lme'].get('usd_ton'):
        point['lme'] = out['lme']['usd_ton']
    if len(point) > 2:
        last = hist[-1] if hist else None
        if not last or last.get('usd') != point.get('usd') or last.get('lme') != point.get('lme'):
            hist.append(point)
    out['hist'] = hist[-2000:]

    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    okn = sum(1 for k in ('usd', 'lme', 'ime') if out[k].get('ok'))
    log(f'\n✔ {a.out} نوشته شد — {okn} از ۳ منبع تازه · {len(out["news"])} خبر · {len(out["hist"])} نقطه تاریخچه')
    return 0


if __name__ == '__main__':
    sys.exit(main())

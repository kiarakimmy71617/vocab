"""순서 세트를 폰 터치로 끝까지 맞춰 보는 점검: python3 _build/touch.py <page>.html [세트ID 접두어]
안드로이드 크롬 폰 화면(390×760, 터치)으로 연다. 끌기는 Playwright CDP 터치 이벤트로 한다.
- 지문마다 먼저 문장 부분을 꾹 누른 채(0.45초) 천천히 밀어 올림 → 카드가 하나도 안 움직여야 함(스크롤만)
- 그다음 손잡이로 카드를 하나씩 끌어 교과서 순서로 맞춤(멀리 있으면 화면 위쪽 끝으로 끌어 자동 스크롤,
  자리에 오면 손가락을 끝에서 떼고 놓음) → 놓을 때마다 화면 순서 = 저장된 순서(S.sess.cur.picks)인지
- 다 맞췄으면 확인 → 정답('다 제자리')이어야 함. 세트의 모든 지문을 이렇게 돈다
페이지 스크립트는 (() => { ... })() 안에 있어서, 끝에 시험용 훅(window.__T)을 단 복사본을 /tmp/touch_pages에 만들어 연다."""
import sys, os, time
from playwright.sync_api import sync_playwright

src_path = os.path.abspath(sys.argv[1])
only = sys.argv[2] if len(sys.argv) > 2 else ''
os.makedirs('/tmp/touch_pages', exist_ok=True)
page_path = '/tmp/touch_pages/' + os.path.basename(src_path)
html = open(src_path, encoding='utf-8').read()
cut = html.rindex('})();')
open(page_path, 'w', encoding='utf-8').write(html[:cut] + 'window.__T = { S, get SET() { return SET; } };\n' + html[cut:])

ORDER = '() => Array.from(document.querySelectorAll("#od-list .od-line")).map(e => +e.dataset.line)'
PICKS = '() => window.__T.S.sess && window.__T.S.sess.cur ? window.__T.S.sess.cur.picks.slice() : null'
RECTS = '() => Array.from(document.querySelectorAll("#od-list .od-line")).map(e => { const r = e.getBoundingClientRect(); return [r.top, r.bottom, +e.dataset.line]; })'


def touch(cdp, kind, x=None, y=None):
    cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': [] if kind == 'touchEnd' else [{'x': x, 'y': y}]})


def slide(cdp, pg, x, y0, y1, steps=6):
    for k in range(1, steps + 1):
        touch(cdp, 'touchMove', x, y0 + (y1 - y0) * k / steps); pg.wait_for_timeout(16)
    return y1


def grip_drag(cdp, pg, line, dest):
    """line(문장 번호) 카드를 손잡이로 잡아 dest 자리로 (앞자리부터 채우니 늘 위로 옮김)"""
    h = pg.evaluate('innerHeight')
    pg.evaluate('(l) => document.querySelector(`#od-list .od-line[data-line="${l}"]`).scrollIntoView({block: "center"})', line)
    pg.wait_for_timeout(50)
    x, y = pg.evaluate('(l) => { const g = document.querySelector(`#od-list .od-line[data-line="${l}"] .od-grip`).getBoundingClientRect(); return [g.left + g.width / 2, g.top + g.height / 2]; }', line)
    touch(cdp, 'touchStart', x, y); pg.wait_for_timeout(20)
    t0 = time.time()
    while time.time() - t0 < 25:
        if pg.evaluate(ORDER).index(line) == dest and 80 <= y <= h - 120: break
        tgt = [r for r in pg.evaluate(RECTS) if r[2] != line][dest]   # 이 카드 바로 위에 놓아야 함
        if 74 <= tgt[0] <= h - 126: y = slide(cdp, pg, x, y, tgt[0] + 6); pg.wait_for_timeout(30)
        else: y = slide(cdp, pg, x, y, 30, steps=3); pg.wait_for_timeout(120)   # 위쪽 끝 → 자동 스크롤
    touch(cdp, 'touchEnd'); pg.wait_for_timeout(60)
    return pg.evaluate(ORDER).index(line) == dest


def text_swipe(cdp, pg):
    """가운데 카드의 문장 부분을 꾹 눌렀다가(0.45초) 천천히 밀어 올림. 카드가 움직였으면 False"""
    before, pk = pg.evaluate(ORDER), pg.evaluate(PICKS)
    pg.evaluate('() => { const l = document.querySelectorAll("#od-list .od-line"); l[Math.floor(l.length / 2)].scrollIntoView({block: "center"}); }')
    pg.wait_for_timeout(60)
    x, y = pg.evaluate('() => { const l = document.querySelectorAll("#od-list .od-line"); const r = l[Math.floor(l.length / 2)].getBoundingClientRect(); return [r.left + 70, r.top + Math.min(20, r.height / 2)]; }')
    touch(cdp, 'touchStart', x, y); pg.wait_for_timeout(450)
    for k in range(1, 11): touch(cdp, 'touchMove', x, y - 22 * k); pg.wait_for_timeout(40)
    touch(cdp, 'touchEnd'); pg.wait_for_timeout(120)
    return pg.evaluate(ORDER) == before and pg.evaluate(PICKS) == pk


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 760}, device_scale_factor=2, is_mobile=True, has_touch=True,
                        user_agent='Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36')
    pg = ctx.new_page(); cdp = ctx.new_cdp_session(pg)
    errs = []
    pg.on('pageerror', lambda e: errs.append('JS 오류: ' + str(e)))
    pg.goto('file://' + page_path); pg.wait_for_timeout(300)
    sids = [s for s in pg.evaluate('() => Array.from(document.querySelectorAll(\'[data-act="full"][data-set]\')).map(b => b.dataset.set)')
            if '-order-' in s and s.startswith(only)]
    total = ok = desync = drags = swipes = moved = 0
    for sid in sids:
        pg.click(f'[data-act="full"][data-set="{sid}"]'); pg.wait_for_timeout(300)
        while pg.locator('#od-go').count():
            n = pg.evaluate('() => window.__T.SET.passages[window.__T.S.sess.cur.id].lines.length')
            name = pg.inner_text('#od-name')
            swipes += 1
            if not text_swipe(cdp, pg): moved += 1; errs.append(f'{sid} {name}: 문장 부분을 꾹 눌러 밀었더니 카드가 움직임')
            for dest in range(n):
                if pg.evaluate(ORDER).index(dest) == dest: continue
                drags += 1
                if not grip_drag(cdp, pg, dest, dest): errs.append(f'{sid} {name}: {dest}번 문장을 제자리로 못 옮김 → {pg.evaluate(ORDER)}')
                if pg.evaluate(ORDER) != pg.evaluate(PICKS): desync += 1; errs.append(f'{sid} {name}: 놓은 뒤 화면 ≠ 저장')
            final = pg.evaluate(ORDER)
            pg.click('#od-go'); pg.wait_for_timeout(150)
            hint = pg.inner_text('#od-hint')
            total += 1
            if final == list(range(n)) and '다 제자리' in hint: ok += 1
            else: errs.append(f'{sid} {name}: 화면 {final} → 채점 {hint!r}')
            if pg.locator('#od-next').count(): pg.click('#od-next'); pg.wait_for_timeout(150)
            else: break
        pg.goto('file://' + page_path); pg.wait_for_timeout(300)
    print(f'순서 {len(sids)}세트 · 지문 {total}개 손잡이로 맞춤 → 정답 {ok}/{total} · 끌기 {drags}번 · 놓은 뒤 화면≠저장 {desync}번')
    print(f'문장 부분 꾹 눌러 밀기 {swipes}번 → 카드 움직임 {moved}번')
    for e in errs[:30]: print(' !', e)
    b.close()
    sys.exit(1 if errs or ok != total else 0)

"""폰 화면(390px)으로 열어서 목록 → 세트 시작까지 오류 없는지 확인: python3 _build/smoke.py <page>.html [캡처.png]
페이지에 있는 세트 종류마다 첫 세트를 한 번씩 연다.
- 단어 세트: 외우기 첫 카드까지
- 순서 세트: 첫 지문을 끌어서 교과서 순서로 맞춰 정답 처리 → 다음 지문을 섞인 채로 확인해 오답(해설 포함) → 목록에 진행 중
- 핵심어 세트: 첫 지문에서 핵심만 골라 정답 → 다음 지문에서 핵심 하나 빼고 오답 하나 더해 오답(이유 2개) → 끝까지 맞혀서
  결과 화면 → (제출 폼이 있으면) 이름 넣고 폼 링크에 세트·다시 한 지문이 들어가는지 → 목록에 지난 기록
끌기는 마우스로 흉내 낸다. 캡처 경로를 주면 목록과 단계별 화면을 따로 찍는다(-pick, -ok, -miss, -kw-pick, -kw-ok, -kw-miss, -kw-result)."""
import sys, os, json
from urllib.parse import unquote
from playwright.sync_api import sync_playwright

page_path = os.path.abspath(sys.argv[1])
shot = sys.argv[2] if len(sys.argv) > 2 else None
snap = lambda pg, tag: shot and pg.screenshot(path=shot.replace('.png', f'-{tag}.png'), full_page=True)


def shown_lines(pg):
    return [t.strip() for t in pg.locator('#od-list .od-line > span:nth-child(2)').all_inner_texts()]


def drag_row(pg, from_idx, to_idx):
    """from_idx 번째 문장 카드를 to_idx 자리로 끌어다 놓음 (마우스). 두 카드 모두 화면 안에 보여야 함"""
    rows = pg.locator('#od-list .od-line')
    src = rows.nth(from_idx).bounding_box()
    dst = rows.nth(to_idx).bounding_box()
    x = src['x'] + src['width'] / 2
    y0 = src['y'] + src['height'] / 2
    y1 = dst['y'] + (4 if to_idx < from_idx else dst['height'] - 4)
    pg.mouse.move(x, y0); pg.mouse.down()
    steps = 8
    for k in range(1, steps + 1): pg.mouse.move(x, y0 + (y1 - y0) * k / steps); pg.wait_for_timeout(10)
    pg.mouse.up(); pg.wait_for_timeout(60)


def visible_rows(pg):
    """화면에 다 보이는 카드의 번호 목록 (위 80px·아래 130px은 자동 스크롤 구역·고정 버튼이라 뺌)"""
    h = pg.evaluate('window.innerHeight')
    out = []
    for i, bx in enumerate(pg.locator('#od-list .od-line').evaluate_all('els => els.map(e => { const r = e.getBoundingClientRect(); return [r.top, r.bottom]; })')):
        if bx[0] >= 80 and bx[1] <= h - 130: out.append(i)
    return out


def arrange(pg, target):
    """화면의 문장들을 target 순서가 되도록 끌어서 정렬. 멀리 있는 카드는 보이는 범위 안에서 여러 번에 나눠 옮김"""
    center = lambda k: (pg.evaluate('(i) => document.querySelectorAll("#od-list .od-line")[i].scrollIntoView({block: "center"})', k), pg.wait_for_timeout(60))
    for i, line in enumerate(target):
        guard = 0
        while shown_lines(pg).index(line) != i and guard < 40:
            guard += 1
            j = shown_lines(pg).index(line)
            center(i)
            if j in visible_rows(pg): drag_row(pg, j, i); continue
            center(j)
            vis = visible_rows(pg)
            cand = [k for k in vis if k < j] if i < j else [k for k in vis if k > j]
            if not cand: break
            drag_row(pg, j, min(cand) if i < j else max(cand))
    return shown_lines(pg) == target


def start(pg, sid):
    pg.click(f'[data-act="full"][data-set="{sid}"]'); pg.wait_for_timeout(400)


def run_vocab(pg, st, errs):
    start(pg, st['id'])
    sub = pg.inner_text('#st-sub'); word = pg.inner_text('#ek-word')
    if not word.strip(): errs.append('단어 카드가 비어 있음')
    pg.click('#st-back'); pg.wait_for_timeout(300)
    return f'단어 {st["title"]!r}: {sub} · 첫 단어 {word!r}'


def run_order(pg, first, errs):
    start(pg, first['id'])
    # 1) 첫 지문: 섞여 나왔는지 → 끌어서 교과서 순서로 → 정답
    name = pg.inner_text('#od-name')
    passage = next(q for q in first['passages'] if q['name'] == name)
    if shown_lines(pg) == passage['lines']: errs.append('섞였어야 할 문장이 교과서 순서 그대로 나옴')
    badges = pg.locator('#od-list .od-bb').all_inner_texts()
    if badges != [str(i + 1) for i in range(len(passage['lines']))]: errs.append('번호가 1부터 차례로 안 붙음: ' + str(badges))
    snap(pg, 'pick')
    if not arrange(pg, passage['lines']): errs.append('끌어서 정렬했는데 순서가 안 맞음: ' + str(shown_lines(pg)))
    pg.click('#od-go'); pg.wait_for_timeout(300)
    hint_ok = pg.inner_text('#od-hint')
    if '다 제자리' not in hint_ok: errs.append('교과서 순서로 놓았는데 정답 처리가 안 됨: ' + hint_ok)
    if pg.locator('#od-list .od-cue').count(): errs.append('정답인데 해설이 나옴')
    snap(pg, 'ok')
    pg.click('#od-next'); pg.wait_for_timeout(300)
    # 2) 둘째 지문: 섞인 채로 확인 → 오답 + 해설
    name2 = pg.inner_text('#od-name')
    p2 = next(q for q in first['passages'] if q['name'] == name2)
    pg.click('#od-go'); pg.wait_for_timeout(300)
    hint_bad = pg.inner_text('#od-hint')
    if '제자리.' not in hint_bad or '다시 나와' not in hint_bad: errs.append('섞인 순서로 놓았는데 오답 처리가 안 됨: ' + hint_bad)
    miss = pg.locator('#od-list .miss').count()
    cues = pg.locator('#od-list .od-cue').count()
    flow = pg.locator('#od-flow:not([hidden])').count()
    if any(p2.get('cues') or []) and (cues != len(p2['lines']) or not flow): errs.append(f'오답 해설이 빠짐 (단서 {cues}/{len(p2["lines"])}, 흐름 {flow})')
    snap(pg, 'miss')
    # 3) 목록으로 돌아가면 진행 중 표시
    pg.click('#od-back'); pg.wait_for_timeout(300)
    card = pg.locator(f'[data-set="{first["id"]}"]').first.locator('xpath=ancestor::article')
    chip = card.locator('.chip').first.inner_text() if card.locator('.chip').count() else ''
    if '진행 중' not in chip: errs.append('목록의 순서 세트 카드에 진행 중 표시가 없음')
    return (f'순서 첫 지문 {name!r} {len(passage["lines"])}문장 끌어서 맞춤 → {hint_ok} / 둘째 지문 {name2!r} 섞인 채 확인 → {hint_bad} '
            f'(빨간 문장 {miss}, 단서 {cues}, 흐름 {"있음" if flow else "없음"}) / 목록: {chip}')


def kw_pick(pg, words):
    """보기 중 words에 든 것만 눌러서 고름"""
    for b in pg.locator('#kw-chips .kw-chip').all():
        if b.inner_text().strip() in words: b.click()
    pg.wait_for_timeout(60)


def run_kw(pg, first, has_form, errs):
    start(pg, first['id'])
    byname = {q['name']: q for q in first['passages']}
    keys_of = lambda q: [o[0] for o in q['opts'] if o[1]]
    # 1) 첫 지문: 본문·보기가 다 보이고 섞였는지 → 핵심만 골라 정답
    name = pg.inner_text('#kw-name'); p = byname[name]
    chips = [t.strip() for t in pg.locator('#kw-chips .kw-chip').all_inner_texts()]
    if sorted(chips) != sorted(o[0] for o in p['opts']): errs.append(f'보기가 데이터와 다름: {chips}')
    if chips == [o[0] for o in p['opts']]: errs.append('보기가 원본 순서 그대로 나옴 (핵심이 앞에 몰림)')
    nums = pg.locator('#kw-text .kw-n').count()
    if nums != len(p['lines']): errs.append(f'본문 문장 번호 {nums}개 (문장 {len(p["lines"])}개)')
    if not pg.locator('#kw-go').is_disabled(): errs.append('아무것도 안 골랐는데 확인 버튼이 눌림')
    kw_pick(pg, keys_of(p))
    go_txt = pg.inner_text('#kw-go')
    if f'{len(keys_of(p))}개' not in go_txt: errs.append('고른 개수가 버튼에 안 나옴: ' + go_txt)
    snap(pg, 'kw-pick')
    pg.click('#kw-go'); pg.wait_for_timeout(300)
    hint_ok = pg.inner_text('#kw-hint')
    if '다 골랐어' not in hint_ok: errs.append('핵심만 골랐는데 정답 처리가 안 됨: ' + hint_ok)
    if pg.locator('.kw-why').count(): errs.append('정답인데 이유가 나옴')
    if not pg.locator('.kw-topic').count() or '**' in pg.inner_text('.kw-topic'): errs.append('정답 뒤 한 줄 주제가 안 나오거나 ** 가 그대로 보임')
    snap(pg, 'kw-ok')
    pg.click('#kw-next'); pg.wait_for_timeout(300)
    # 2) 둘째 지문: 핵심 하나 빼고 오답 하나 더해서 → 오답 + 이유 2개 + 한 줄 주제
    name2 = pg.inner_text('#kw-name'); p2 = byname[name2]
    k2 = keys_of(p2); wrong = next(o[0] for o in p2['opts'] if not o[1])
    kw_pick(pg, k2[1:] + [wrong])
    pg.click('#kw-go'); pg.wait_for_timeout(300)
    hint_bad = pg.inner_text('#kw-hint')
    if '빠뜨린 핵심 1개' not in hint_bad or '잘못 고른 보기 1개' not in hint_bad or '다시 나와' not in hint_bad:
        errs.append('핵심 하나 빼고 오답 하나 더했는데 오답 처리가 이상함: ' + hint_bad)
    whys = pg.locator('.kw-why').count()
    if whys != 2: errs.append(f'틀린 보기 이유가 {whys}개 (2개여야 함)')
    if not pg.locator('.kw-topic').count(): errs.append('오답 뒤 한 줄 주제가 안 나옴')
    snap(pg, 'kw-miss')
    # 3) 나머지는 다 맞혀서 결과 화면까지 (틀린 둘째 지문은 맨 뒤에 다시 나옴)
    seen = [name, name2]
    for _ in range(len(first['passages']) * 2 + 2):
        pg.click('#kw-next'); pg.wait_for_timeout(250)
        if pg.locator('.result').count(): break
        nm = pg.inner_text('#kw-name'); seen.append(nm)
        kw_pick(pg, keys_of(byname[nm]))
        pg.click('#kw-go'); pg.wait_for_timeout(200)
        if '다 골랐어' not in pg.inner_text('#kw-hint'): errs.append(f'{nm}: 핵심만 골랐는데 정답 처리가 안 됨')
    if not pg.locator('.result').count(): errs.append('끝까지 맞혔는데 결과 화면이 안 나옴'); return 'kw 결과 화면 없음'
    if seen[-1] != name2: errs.append(f'틀린 지문({name2})이 맨 뒤에 다시 안 나옴: {seen}')
    res_h = pg.inner_text('.big-h')
    submit = ''
    if has_form:
        if not pg.locator('#sub-name').count(): errs.append('결과 화면에 제출 칸이 없음')
        else:
            pg.fill('#sub-name', '점검'); pg.wait_for_timeout(50)
            href = unquote(pg.get_attribute('#sub-go', 'href'))
            want_set = f'핵심어 · {first["title"]}'
            if want_set not in href: errs.append('폼 링크에 세트가 없음: ' + href)
            if f'1지문: {name2}(2번 만에)' not in href: errs.append('폼 링크에 다시 한 지문이 없음: ' + href)
            submit = f' · 폼 링크: {want_set} / 1지문: {name2}(2번 만에)'
    snap(pg, 'kw-result')
    pg.click('#r-home'); pg.wait_for_timeout(300)
    card = pg.locator(f'[data-set="{first["id"]}"]').first.locator('xpath=ancestor::article').inner_text()
    if '지난 기록' not in card or '틀린 지문만 1' not in card: errs.append('목록 카드에 지난 기록·틀린 지문만 1이 없음: ' + card[:80])
    return (f'핵심어 첫 지문 {name!r} → {hint_ok} / 둘째 {name2!r} → {hint_bad} (이유 {whys}) / '
            f'{len(seen)}번 풀어 결과: {res_h}{submit} / 목록: 지난 기록·틀린 지문만 1')


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 390, 'height': 844}, device_scale_factor=2)
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto('file://' + page_path); pg.wait_for_timeout(500)
    if shot: pg.screenshot(path=shot, full_page=True)
    titles = pg.locator('.set-title').all_inner_texts()
    groups = pg.locator('.group-h').all_inner_texts()
    wide = pg.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    sets = json.loads(pg.inner_text('#sets-data'))
    cfg = json.loads(pg.inner_text('#page-config')) if pg.locator('#page-config').count() else {}
    details = []
    vocab = next((s for s in sets if not s.get('kind')), None)
    order = next((s for s in sets if s.get('kind') == 'order'), None)
    kw = next((s for s in sets if s.get('kind') == 'kw'), None)
    if vocab: details.append(run_vocab(pg, vocab, errs))
    if order: details.append(run_order(pg, order, errs))
    if kw:
        details.append(run_kw(pg, kw, bool(cfg.get('form')), errs))
        wide = wide or pg.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    b.close()
print(f'그룹 {groups}\n세트 {titles}\n' + '\n'.join(details) + f'\n가로 넘침 {wide} · 오류 {errs or "없음"}')
sys.exit(1 if errs or wide else 0)

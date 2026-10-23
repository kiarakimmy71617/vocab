"""폰 화면(390px)으로 열어서 목록 → 첫 세트 시작까지 오류 없는지 확인: python3 _build/smoke.py <page>.html [캡처.png]
단어 세트면 외우기 첫 카드까지, 순서 세트면 첫 지문을 끌어서 교과서 순서로 맞춰 정답 처리되는지 → 다음 지문을 섞인 채로 확인해
오답 처리(해설 포함)되는지까지 본다. 끌기는 마우스로 흉내 낸다."""
import sys, os, json
from playwright.sync_api import sync_playwright

page_path = os.path.abspath(sys.argv[1])
shot = sys.argv[2] if len(sys.argv) > 2 else None


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
        while shown(pg).index(line) != i and guard < 40:
            guard += 1
            j = shown(pg).index(line)
            center(i)
            if j in visible_rows(pg): drag_row(pg, j, i); continue
            center(j)
            vis = visible_rows(pg)
            cand = [k for k in vis if k < j] if i < j else [k for k in vis if k > j]
            if not cand: break
            drag_row(pg, j, min(cand) if i < j else max(cand))
    return shown(pg) == target


def shown(pg): return shown_lines(pg)


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
    first = sets[0] if sets and sets[0].get('kind') == 'order' else None
    pg.click('[data-act="full"]'); pg.wait_for_timeout(500)
    if first is None:
        sub = pg.inner_text('#st-sub'); word = pg.inner_text('#ek-word')
        detail = f'첫 화면: {sub} · 첫 단어 {word!r}'
    else:
        # 1) 첫 지문: 섞여 나왔는지 → 끌어서 교과서 순서로 → 정답
        name = pg.inner_text('#od-name')
        passage = next(q for q in first['passages'] if q['name'] == name)
        if shown_lines(pg) == passage['lines']: errs.append('섞였어야 할 문장이 교과서 순서 그대로 나옴')
        badges = pg.locator('#od-list .od-bb').all_inner_texts()
        if badges != [str(i + 1) for i in range(len(passage['lines']))]: errs.append('번호가 1부터 차례로 안 붙음: ' + str(badges))
        if shot: pg.screenshot(path=shot.replace('.png', '-pick.png'), full_page=True)
        if not arrange(pg, passage['lines']): errs.append('끌어서 정렬했는데 순서가 안 맞음: ' + str(shown_lines(pg)))
        pg.click('#od-go'); pg.wait_for_timeout(300)
        hint_ok = pg.inner_text('#od-hint')
        if '다 제자리' not in hint_ok: errs.append('교과서 순서로 놓았는데 정답 처리가 안 됨: ' + hint_ok)
        if pg.locator('#od-list .od-cue').count(): errs.append('정답인데 해설이 나옴')
        if shot: pg.screenshot(path=shot.replace('.png', '-ok.png'), full_page=True)
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
        if shot: pg.screenshot(path=shot.replace('.png', '-miss.png'), full_page=True)
        # 3) 목록으로 돌아가면 진행 중 표시
        pg.click('#od-back'); pg.wait_for_timeout(300)
        chip = pg.locator('.chip').first.inner_text() if pg.locator('.chip').count() else ''
        if '진행 중' not in chip: errs.append('목록에 진행 중 표시가 없음')
        detail = (f'첫 지문 {name!r} {len(passage["lines"])}문장 끌어서 맞춤 → {hint_ok} / 둘째 지문 {name2!r} 섞인 채 확인 → {hint_bad} '
                  f'(빨간 문장 {miss}, 단서 {cues}, 흐름 {"있음" if flow else "없음"}) / 목록: {chip}')
    b.close()
print(f'그룹 {groups}\n세트 {titles}\n{detail}\n가로 넘침 {wide} · 오류 {errs or "없음"}')
sys.exit(1 if errs or wide else 0)

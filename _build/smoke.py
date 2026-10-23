"""폰 화면(390px)으로 열어서 목록 → 첫 세트 시작까지 오류 없는지 확인: python3 _build/smoke.py <page>.html [캡처.png]
단어 세트면 외우기 첫 카드까지, 순서 세트면 첫 지문을 교과서 순서로 놓아 정답 처리되는지 → 다음 지문을 틀리게 놓아 오답 처리되는지까지 본다."""
import sys, os, json
from playwright.sync_api import sync_playwright

page_path = os.path.abspath(sys.argv[1])
shot = sys.argv[2] if len(sys.argv) > 2 else None
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
    first = next((s for s in sets if s.get('kind') == 'order'), None) if sets and sets[0].get('kind') == 'order' else None
    pg.click('[data-act="full"]'); pg.wait_for_timeout(500)
    if first is None:
        sub = pg.inner_text('#st-sub'); word = pg.inner_text('#ek-word')
        detail = f'첫 화면: {sub} · 첫 단어 {word!r}'
    else:
        # 1) 첫 지문을 교과서 순서대로 탭 → 정답
        name = pg.inner_text('#od-name')
        passage = next(p for p in first['passages'] if p['name'] == name)
        shown = pg.locator('#od-list button').all_inner_texts()
        if [t.strip() for t in shown] == passage['lines']: errs.append('섞였어야 할 문장이 교과서 순서 그대로 나옴')
        for line in passage['lines']:
            pg.locator('#od-list button', has_text=line).first.click()
        go = pg.locator('#od-go'); ok_enabled = go.is_enabled()
        if shot: pg.screenshot(path=shot.replace('.png', '-pick.png'), full_page=True)
        go.click(); pg.wait_for_timeout(300)
        hint_ok = pg.inner_text('#od-hint')
        if '다 제자리' not in hint_ok: errs.append('교과서 순서로 놓았는데 정답 처리가 안 됨: ' + hint_ok)
        if shot: pg.screenshot(path=shot.replace('.png', '-ok.png'), full_page=True)
        pg.click('#od-next'); pg.wait_for_timeout(300)
        # 2) 다음 지문을 화면에 나온 순서(섞인 순서)대로 탭 → 오답
        name2 = pg.inner_text('#od-name')
        for btn in pg.locator('#od-list button').all(): btn.click()
        pg.click('#od-go'); pg.wait_for_timeout(300)
        hint_bad = pg.inner_text('#od-hint')
        if '다시 봐' not in hint_bad: errs.append('섞인 순서로 놓았는데 오답 처리가 안 됨: ' + hint_bad)
        miss = pg.locator('#od-list .miss').count()
        if shot: pg.screenshot(path=shot.replace('.png', '-miss.png'), full_page=True)
        # 3) 목록으로 돌아가면 진행 중 표시
        pg.click('#od-back'); pg.wait_for_timeout(300)
        chip = pg.locator('.chip').first.inner_text() if pg.locator('.chip').count() else ''
        if '진행 중' not in chip: errs.append('목록에 진행 중 표시가 없음')
        detail = f'첫 지문 {name!r} {len(passage["lines"])}문장 · 확인 버튼 {"켜짐" if ok_enabled else "꺼짐"} → {hint_ok} / 둘째 지문 {name2!r} 틀리게 놓음 → {hint_bad} (빨간 문장 {miss}) / 목록: {chip}'
    b.close()
print(f'그룹 {groups}\n세트 {titles}\n{detail}\n가로 넘침 {wide} · 오류 {errs or "없음"}')
sys.exit(1 if errs or wide else 0)

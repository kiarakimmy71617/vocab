"""폰 화면(390px)으로 열어서 목록 → 첫 세트 외우기 시작까지 오류 없는지 확인: python3 _build/smoke.py <page>.html [캡처.png]"""
import sys, os
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
    pg.click('[data-act="full"]'); pg.wait_for_timeout(500)
    sub = pg.inner_text('#st-sub')
    word = pg.inner_text('#ek-word')
    b.close()
print(f'그룹 {groups}\n세트 {titles}\n첫 화면: {sub} · 첫 단어 {word!r} · 가로 넘침 {wide} · 오류 {errs or "없음"}')
sys.exit(1 if errs or wide else 0)

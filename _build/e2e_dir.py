"""단어 방향(둘 다 / 영→한만 / 한→영만)을 세트 하나씩 끝까지 돌려 보는 점검: python3 _build/e2e_dir.py [저장소] [캡처 폴더]
단어 학습 엔진(거르기·집중·마지막 점검·방향·제출 조건)을 고쳤을 때 smoke.py에 더해 돌린다(2026-11-08 방향 기능 때 만듦).
- 페이지 스크립트는 (() => { ... })() 안에 있어서 밖에서 못 부르므로, 끝에 시험용 훅(window.__T)을 단 복사본을 캡처 폴더/pages에 만들어 연다.
  카드는 화면 버튼이 부르는 것과 같은 함수(reveal·gradeEK·onKESubmit·finishKE)로 답한다. 처음 몇 장·틀린 답·버튼·키보드는 화면으로 누른다.
- 쓰는 페이지: haesong.html(단어 + 순서 · 주 시험), songdo1.html(섞인 페이지, 방향 고르기 위치·페이지마다 따로 기억), donga3.html(순서만 · 방향 고르기 없어야 함).
  페이지 구성이 바뀌어 맞지 않으면 이 세 이름만 고친다. 한→영만 시험 세트는 '철자 쓰기 없는 표현'이 있는 첫 단어 세트(없으면 첫 세트).
- 캡처: home-both/ek/ke/resume/320, study-ke-wrong, result-ek/ke, songdo1-dirpick (.png)"""
import sys, os, json
from playwright.sync_api import sync_playwright

repo = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..'))
shots = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else '/tmp/e2e_dir')
os.makedirs(shots, exist_ok=True)
HOOK = "\nwindow.__T = { S, get C() { return C; }, get SET() { return SET; }, get R() { return R; }, reveal, gradeEK, onKESubmit, finishKE, dunno, prepareSet, findRaw, getRec, K, BUILTIN };"
pages = os.path.join(shots, 'pages'); os.makedirs(pages, exist_ok=True)
for nm in ['haesong', 'songdo1', 'donga3']:
    h = open(os.path.join(repo, nm + '.html'), encoding='utf-8').read()
    i = h.rindex('\n})();')
    open(os.path.join(pages, nm + '.html'), 'w', encoding='utf-8').write(h[:i] + HOOK + h[i:])
repo = pages
fails, notes = [], []
def ok(cond, msg):
    (notes if cond else fails).append(('OK ' if cond else 'FAIL ') + msg)

# 카드 하나씩 엔진 함수로 답함(화면 버튼이 부르는 것과 같은 함수). stopAt: 이 단계가 되면 멈춤. wrongIds: 이 단어는 처음 세 번 틀리게(거르기 1 + 집중 2 → 끈질긴 단어)
FF = """([stopAt, wrongIds]) => {
  const T = window.__T;
  const seen = { sort: {ek:0, ke:0}, learn: {ek:0, ke:0}, final: {ek:0, ke:0} };
  const miss = {}, bad = [];
  let steps = 0, banner = '', pauses = [];
  const wrong = new Set(wrongIds || []);
  while (steps < 4000) {
    if (T.S.view === 'pause') {
      pauses.push({ eb: document.querySelector('.pause .eyebrow').textContent, note: document.querySelector('.pause .note').textContent,
                    dt: Array.from(document.querySelectorAll('.pause dt')).map(e => e.textContent) });
      document.getElementById('go-next').click(); continue;
    }
    if (T.S.view !== 'study' || !T.C || !T.S.sess) break;
    const s = T.S.sess;
    if (stopAt && s.phase === stopAt) break;
    if (s.phase === 'learn' && !banner && !document.getElementById('st-banner').hidden) banner = document.getElementById('st-banner').textContent;
    steps++;
    seen[s.phase][T.C.d]++;
    const id = T.C.id, it = T.SET.items[id];
    const w = wrong.has(id) && (miss[id] = (miss[id] || 0) + 1) <= 3;
    if (T.C.d === 'ek') { T.reveal(true); T.gradeEK(w ? 'no' : 'yes'); }
    else {
      T.R['ke-input'].value = w ? 'zzzz' : it.vars[0];
      T.onKESubmit({ preventDefault() {} });
      if (T.C.state === 'ask') { bad.push(it.en); T.dunno(); }
      else if (!w && T.C.pending !== 'ok') bad.push(it.en + ' → ' + T.C.pending);
      T.finishKE();
    }
  }
  return { seen, steps, view: T.S.view, banner, pauses, bad };
}"""

def home_card(pg, sid):
    return pg.locator(f'article.set:has([data-set="{sid}"])').first

def btn_texts(pg, sid):
    return [t.strip() for t in home_card(pg, sid).locator('.set-actions button').all_inner_texts()]

def status_text(pg, sid):
    return home_card(pg, sid).locator('.set-status').inner_text()

import traceback
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2)
        pg = ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('console', lambda m: m.type == 'error' and errs.append(m.text))
        url = 'file://' + os.path.join(repo, 'haesong.html')
        pg.goto(url); pg.wait_for_timeout(400)

        # ---------- 1. 목록: 방향 고르기 ----------
        ok(pg.locator('.dir-pick').count() == 1, 'dir-pick 한 번만 있음')
        first = pg.evaluate("() => __T.BUILTIN.find(s => (s.kind || 'vocab') === 'vocab' && !s.inactive).id")
        info = pg.evaluate("(id) => { const s = __T.prepareSet(__T.findRaw(id)); return { n: s.items.length, keN: s.items.filter(i => i.ke).length, title: s.title, nonKe: s.items.filter(i => !i.ke).map(i => i.en) } }", first)
        notes.append(f'   첫 단어 세트 {info["title"]}: {info["n"]}개, 철자 쓰기 가능 {info["keN"]}개, 빠지는 것 {info["nonKe"]}')
        ksid = pg.evaluate("() => { const v = __T.BUILTIN.filter(s => (s.kind || 'vocab') === 'vocab'); const x = v.find(s => __T.prepareSet(s).items.some(i => !i.ke)); return (x || v[0]).id; }")
        kinfo = pg.evaluate("(id) => { const s = __T.prepareSet(__T.findRaw(id)); return { n: s.items.length, keN: s.items.filter(i => i.ke).length, title: s.title, nonKe: s.items.filter(i => !i.ke).map(i => i.en) } }", ksid)
        notes.append(f'   한→영 시험 세트 {kinfo["title"]}: {kinfo["n"]}개, 철자 쓰기 가능 {kinfo["keN"]}개, 빠지는 것 {kinfo["nonKe"]}')
        checked = pg.locator('.dir-seg [aria-checked="true"]').inner_text()
        ok(checked == '둘 다', f'처음엔 둘 다 선택 ({checked})')
        ok(btn_texts(pg, first)[:2] == ['외우기', '빠른 점검'], f'둘 다일 때 버튼 이름 그대로 {btn_texts(pg, first)}')
        # 방향 고르기가 첫 단어 세트 바로 앞에 있는지
        order_ok = pg.evaluate("(id) => { const d = document.querySelector('.dir-pick'); const c = document.querySelector(`article.set [data-set=\"${id}\"]`).closest('article'); return d.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING ? true : false; }", first)
        ok(order_ok, '방향 고르기가 첫 단어 세트보다 위')
        pg.locator('.dir-pick').scroll_into_view_if_needed()
        pg.evaluate("window.scrollBy(0, -120)")
        pg.screenshot(path=f'{shots}/home-both.png')

        # ---------- 2. 영→한만 고르기 · 저장 ----------
        y0 = pg.evaluate('window.scrollY')
        pg.click('[data-dir="ek"]'); pg.wait_for_timeout(200)
        y1 = pg.evaluate('window.scrollY')
        ok(abs(y1 - y0) < 2, f'방향 바꿔도 스크롤 그대로 ({y0}→{y1})')
        ok(pg.locator('.dir-seg [aria-checked="true"]').inner_text() == '영→한만', '영→한만 선택됨')
        ok('뜻 말하기만 나와' in pg.inner_text('.dir-note') and '제출은 ‘둘 다’로' in pg.inner_text('.dir-note'), '영→한만 설명')
        ok(btn_texts(pg, first)[:2] == ['외우기 · 영→한만', '빠른 점검 · 영→한만'], f'버튼에 영→한만 {btn_texts(pg, first)}')
        pg.screenshot(path=f'{shots}/home-ek.png')
        ok(pg.evaluate("localStorage.getItem('kd1:dir:haesong.html')") == '"ek"', '기기에 저장됨')
        pg.reload(); pg.wait_for_timeout(400)
        ok(pg.locator('.dir-seg [aria-checked="true"]').inner_text() == '영→한만', '새로고침해도 영→한만')

        # ---------- 3. 영→한만 외우기 끝까지 ----------
        pg.click(f'[data-act="full"][data-set="{first}"]'); pg.wait_for_timeout(400)
        ok('영→한만' in pg.inner_text('#st-sub'), f'상단에 영→한만 ({pg.inner_text("#st-sub")})')
        ok(pg.is_visible('#ek-word') and not pg.is_visible('#ke-input'), '첫 카드 영→한')
        # 화면 버튼으로 두 장: 뜻 보기 → 알았어
        for _ in range(2):
            pg.wait_for_timeout(350); pg.click('#ek-show'); pg.click('#ek-grade [data-g="yes"]')
        r = pg.evaluate(FF, [None, []])
        ok(r['seen']['sort']['ke'] == 0 and r['seen']['learn']['ke'] == 0 and r['seen']['final']['ke'] == 0, f'영→한만: 한→영 카드 0장 {r["seen"]}')
        ok(r['view'] == 'result', '결과 화면까지 감')
        ok(all('영→한만' in x['eb'] for x in r['pauses']), '배치 끝 화면에 영→한만')
        ok(r['pauses'] and '영→한으로만 나와' in r['pauses'][-1]['note'], f'마지막 점검 안내 ({r["pauses"][-1]["note"] if r["pauses"] else "-"})')
        eb = pg.inner_text('.result .eyebrow')
        ok(eb.startswith('외우기 · 영→한만 끝'), f'결과 제목 {eb}')
        ok(pg.locator('.submit').count() == 0, '영→한만은 제출 칸 없음')
        ok('한쪽만 한 건 연습 기록' in pg.inner_text('.result'), '연습 기록 안내')
        pg.screenshot(path=f'{shots}/result-ek.png', full_page=True)
        rec = pg.evaluate(f"JSON.parse(localStorage.getItem(__T.K.rec('{first}')))")
        ok(rec['last']['dir'] == 'ek' and 'best' not in rec, f'기록 dir=ek, 최고 기록 안 남김 {rec["last"]}')
        pg.click('#r-home'); pg.wait_for_timeout(300)
        ok('(영→한만)' in status_text(pg, first), f'목록 지난 기록에 영→한만 ({status_text(pg, first)})')

        # ---------- 4. 한→영만 외우기 끝까지 ----------
        pg.click('[data-dir="ke"]'); pg.wait_for_timeout(200)
        st = status_text(pg, ksid)
        if kinfo['keN'] < kinfo['n']:
            ok(f'한→영만 {kinfo["keN"]}개 · 영→한 전용 표현 {kinfo["n"] - kinfo["keN"]}개 빠짐' in st, f'빠지는 개수 안내 ({st})')
        pg.screenshot(path=f'{shots}/home-ke.png')
        pg.click(f'[data-act="full"][data-set="{ksid}"]'); pg.wait_for_timeout(400)
        ok(pg.is_visible('#ke-input') and not pg.is_visible('#ek-word'), '첫 카드 한→영(철자 쓰기)')
        ok('한→영' in pg.inner_text('#c-dir'), f'카드 방향 표시 {pg.inner_text("#c-dir")}')
        pool = pg.evaluate('__T.S.sess.pool.length')
        ok(pool == kinfo['keN'], f'한→영만 세션 단어 수 = 철자 가능 단어 수 ({pool}/{kinfo["keN"]})')
        ok(pg.evaluate("__T.S.sess.pool.every(id => __T.SET.items[id].ke)"), '긴 표현 안 들어감')
        # 첫 카드 일부러 틀리게(화면으로)
        pg.fill('#ke-input', 'zzzz'); pg.click('#ke-go'); pg.wait_for_timeout(150)
        fb = pg.inner_text('#ke-fb')
        ok('거르기 끝나고 다시 나와' in fb, f'거르기에서 틀리면 안내 ({fb.splitlines()[-1] if fb else "-"})')
        pg.screenshot(path=f'{shots}/study-ke-wrong.png')
        pg.click('#ke-go'); pg.wait_for_timeout(150)
        r = pg.evaluate(FF, ['learn', []])
        ok(r['seen']['sort']['ek'] == 0, '거르기도 한→영')
        r2 = pg.evaluate(FF, [None, []])
        ok(r2['banner'].startswith('거르기 끝') and '바로 맞힘' in r2['banner'] and '틀린 1개 다시' in r2['banner'], f'거르기 끝 안내 ({r2["banner"]})')
        allek = sum(r2['seen'][k]['ek'] for k in r2['seen'])
        ok(allek == 0, f'한→영만: 영→한 카드 0장 {r2["seen"]}')
        ok(not r['bad'] and not r2['bad'], f'정답 입력이 다 맞음 {r["bad"] + r2["bad"]}')
        ok(r2['pauses'] and '한→영(철자 쓰기)으로만 나와' in r2['pauses'][-1]['note'], '마지막 점검 안내(한→영)')
        ok(all('바로 맞힌 단어' in x['dt'] for x in r2['pauses']), '배치 끝 칸 이름 바로 맞힌 단어')
        eb = pg.inner_text('.result .eyebrow')
        ok(eb.startswith('외우기 · 한→영만 끝'), f'결과 제목 {eb}')
        ok('바로 맞힌 단어' in pg.inner_text('.result .stats'), '결과 칸 이름')
        ok(pg.locator('.submit').count() == 0, '한→영만은 제출 칸 없음')
        pg.screenshot(path=f'{shots}/result-ke.png', full_page=True)
        pg.click('#r-home'); pg.wait_for_timeout(300)

        # ---------- 5. 둘 다 외우기 끝까지 (끈질긴 단어 만들기) ----------
        pg.click('[data-dir="both"]'); pg.wait_for_timeout(200)
        ids = pg.evaluate(f"(() => {{ const s = __T.prepareSet(__T.findRaw('{ksid}')); const ke = [], no = []; s.items.forEach((it, i) => (it.ke ? ke : no).push(i)); return {{ ke: ke.slice(0, 3), no: no.slice(0, 2) }}; }})()")
        wrong = ids['ke'] + ids['no']
        pg.click(f'[data-act="full"][data-set="{ksid}"]'); pg.wait_for_timeout(400)
        ok('영→한만' not in pg.inner_text('#st-sub') and '한→영만' not in pg.inner_text('#st-sub'), '둘 다는 상단 표시 없음')
        r = pg.evaluate(FF, [None, wrong])
        ok(r['seen']['sort']['ke'] == 0 and r['seen']['learn']['ke'] > 0 and r['seen']['final']['ke'] > 0 and r['seen']['final']['ek'] > 0, f'둘 다: 섞여 나옴 {r["seen"]}')
        ok(r['pauses'] and '섞여 나와' in r['pauses'][-1]['note'], '마지막 점검 안내(섞임)')
        eb = pg.inner_text('.result .eyebrow')
        ok(eb.startswith('외우기 끝'), f'결과 제목 {eb}')
        ok(pg.locator('.submit').count() == 1, '둘 다 외우기는 제출 칸 있음')
        pg.fill('#sub-name', '테스트')
        href = pg.get_attribute('#sub-go', 'href')
        from urllib.parse import unquote
        ok(f'{kinfo["title"]} · 외우기' in unquote(href) and '영→한' not in unquote(href), '폼 세트 칸은 예전 그대로')
        rec = pg.evaluate(f"JSON.parse(localStorage.getItem(__T.K.rec('{ksid}')))")
        ok(rec['last']['dir'] == 'both' and rec.get('best'), '둘 다는 최고 기록 남김')
        hard = rec['hard']
        ok(set(wrong) <= set(hard), f'세 번 틀린 단어는 끈질긴 단어 ({hard} ⊇ {wrong})')
        notes.append(f'   끈질긴 단어 {len(hard)}개 (철자 가능 {sum(1 for i in hard if i in ids["ke"])}, 긴 표현 {sum(1 for i in hard if i in ids["no"])})')
        pg.click('#r-home'); pg.wait_for_timeout(300)

        # ---------- 6. 한→영만 끈질긴 단어 · 빠른 점검 ----------
        ok(f'끈질긴 단어 {len(hard)}' in btn_texts(pg, ksid), f'둘 다일 땐 끈질긴 단어 전부 {btn_texts(pg, ksid)}')
        pg.click('[data-dir="ke"]'); pg.wait_for_timeout(200)
        bt = btn_texts(pg, ksid)
        keHard = pg.evaluate(f"(() => {{ const s = __T.prepareSet(__T.findRaw('{ksid}')); return __T.getRec('{ksid}').hard.filter(i => s.items[i].ke).length; }})()")
        ok(f'끈질긴 단어 {keHard} · 한→영만' in bt, f'끈질긴 단어 수는 철자 가능한 것만 {bt}')
        pg.click(f'[data-act="hard"][data-set="{ksid}"]'); pg.wait_for_timeout(400)
        ok(pg.evaluate('__T.S.sess.pool.length') == keHard and pg.evaluate("__T.S.sess.pool.every(id => __T.SET.items[id].ke)"), '끈질긴 단어 세션도 철자 가능한 것만')
        ok('끈질긴 단어' in pg.inner_text('#st-sub') and '한→영만' in pg.inner_text('#st-sub'), f'상단 {pg.inner_text("#st-sub")}')
        r = pg.evaluate(FF, [None, []])
        ok(sum(r['seen'][k]['ek'] for k in r['seen']) == 0, '끈질긴 단어(한→영만) 영→한 0장')
        ok(pg.locator('.submit').count() == 0 and '외우기’를 끝까지' in pg.inner_text('.result'), '끈질긴 단어는 제출 없음')
        pg.click('#r-home'); pg.wait_for_timeout(300)
        pg.click(f'[data-act="quick"][data-set="{ksid}"]'); pg.wait_for_timeout(400)
        ok(pg.evaluate('__T.S.sess.phase') == 'final' and pg.evaluate('__T.S.sess.pool.length') == kinfo['keN'], '빠른 점검(한→영만) 철자 가능한 것 전부')
        ok('빠른 점검' in pg.inner_text('#st-sub') and '한→영만' in pg.inner_text('#st-sub'), f'상단 {pg.inner_text("#st-sub")}')
        r = pg.evaluate(FF, [None, []])
        ok(sum(r['seen'][k]['ek'] for k in r['seen']) == 0 and r['view'] == 'result', '빠른 점검(한→영만) 영→한 0장')
        ok(pg.inner_text('.result .eyebrow').startswith('빠른 점검 · 한→영만 끝'), pg.inner_text('.result .eyebrow'))
        pg.click('#r-home'); pg.wait_for_timeout(300)

        # ---------- 7. 이어서 하기는 시작한 방향 그대로 ----------
        pg.click('[data-dir="ek"]'); pg.wait_for_timeout(200)
        pg.click(f'[data-act="full"][data-set="{first}"]'); pg.wait_for_timeout(400)
        pg.evaluate(FF.replace('while (steps < 4000)', 'while (steps < 3)'), [None, []])
        pg.click('#st-back'); pg.wait_for_timeout(300)
        pg.click('[data-dir="ke"]'); pg.wait_for_timeout(200)
        bt = btn_texts(pg, first); st = status_text(pg, first)
        ok(bt[:2] == ['이어서 하기 · 영→한만', '처음부터 · 한→영만'], f'이어서/처음부터 이름 {bt}')
        ok('진행 중 · 배치 1/' in st and '영→한만' in st, f'진행 중 칩 ({st})')
        pg.screenshot(path=f'{shots}/home-resume.png')
        pg.click(f'[data-act="resume"][data-set="{first}"]'); pg.wait_for_timeout(400)
        ok(pg.evaluate('__T.S.sess.dir') == 'ek' and pg.is_visible('#ek-word'), '이어서 하기 = 영→한만 그대로')
        # 이어서 끝까지(틀린 단어 몇 개) → 결과의 '끈질긴 단어만 다시'도 방금 한 방향(영→한만)으로
        wr = pg.evaluate("__T.S.sess.pool.slice(0, 2)")
        r = pg.evaluate(FF, [None, wr])
        rb = pg.inner_text('#r-hard') if pg.locator('#r-hard').count() else '-'
        ok(rb == '끈질긴 단어만 다시 · 영→한만', f'결과 다시 버튼 이름 ({rb})')
        pg.click('#r-hard'); pg.wait_for_timeout(400)
        ok(pg.evaluate('__T.S.sess.dir') == 'ek' and pg.evaluate('__T.S.sess.mode') == 'hard', '결과에서 다시 = 영→한만 끈질긴 단어 (목록 방향은 한→영만이어도)')
        pg.click('#st-back'); pg.wait_for_timeout(300)
        # 키보드: 화살표로 방향 옮기기, 마우스로 누른 뒤엔 초점 테두리 없음
        fv = pg.evaluate("document.activeElement && document.activeElement.matches('[data-dir]') ? document.activeElement.matches(':focus-visible') : null")
        ok(fv in (None, False), f'마우스로 고른 뒤 초점 테두리 없음 ({fv})')
        pg.focus('.dir-seg [aria-checked="true"]'); pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(200)
        now = pg.locator('.dir-seg [aria-checked="true"]').inner_text()
        act = pg.evaluate("document.activeElement.dataset.dir + '/' + document.activeElement.getAttribute('aria-checked') + '/' + document.activeElement.matches(':focus-visible')")
        tabs = pg.evaluate("Array.from(document.querySelectorAll('.dir-seg button')).map(b => b.tabIndex)")
        ok(now == '둘 다' and act == 'both/true/true' and tabs == [0, -1, -1], f'화살표 → 다음 방향(끝에서 처음으로) ({now}, {act}, {tabs})')
        pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(200)
        ok(pg.locator('.dir-seg [aria-checked="true"]').inner_text() == '한→영만', '화살표 ← 이전 방향')
        pg.click(f'[data-act="full"][data-set="{first}"]'); pg.wait_for_timeout(200)
        ok(pg.locator('.confirm').count() == 1, '처음부터 누르면 확인')
        pg.click(f'[data-act="yes-full"][data-set="{first}"]'); pg.wait_for_timeout(400)
        ok(pg.evaluate('__T.S.sess.dir') == 'ke' and pg.is_visible('#ke-input'), '지우고 시작 = 한→영만 새로')
        pg.click('#st-back'); pg.wait_for_timeout(300)

        # ---------- 8. 페이지마다 따로 기억 · 섞인 페이지 위치 · 순서만 있는 페이지 ----------
        pg.goto('file://' + os.path.join(repo, 'songdo1.html')); pg.wait_for_timeout(500)
        ok(pg.locator('.dir-seg [aria-checked="true"]').inner_text() == '둘 다', '다른 페이지는 따로(둘 다)')
        pos = pg.evaluate("""() => { const d = document.querySelector('.dir-pick'); const prev = d.previousElementSibling, next = d.nextElementSibling;
          return [prev ? prev.tagName + '.' + prev.className : '-', next ? next.tagName + '.' + next.className : '-', next ? next.querySelector('.set-title').textContent : ''] }""")
        notes.append(f'   송도고1 방향 고르기 위치: 앞 {pos[0]} / 뒤 {pos[1]} ({pos[2]})')
        ok(pos[1].startswith('ARTICLE'), '바로 뒤가 단어 세트 카드')
        pg.evaluate("document.querySelector('.dir-pick').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(100)
        y0 = pg.evaluate('window.scrollY'); pg.click('[data-dir="ke"]'); pg.wait_for_timeout(200); y1 = pg.evaluate('window.scrollY')
        ok(y0 > 200 and abs(y1 - y0) < 2, f'송도고1: 방향 바꿔도 스크롤 그대로 ({y0}→{y1})')
        pg.screenshot(path=f'{shots}/songdo1-dirpick.png')
        pg.click('[data-dir="both"]'); pg.wait_for_timeout(100)
        pg.goto('file://' + os.path.join(repo, 'donga3.html')); pg.wait_for_timeout(400)
        ok(pg.locator('.dir-pick').count() == 0, '순서만 있는 페이지엔 방향 고르기 없음')
        # 좁은 폰(320px)
        pg.set_viewport_size({'width': 320, 'height': 700})
        pg.goto(url); pg.wait_for_timeout(400)
        over = pg.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        seg = pg.evaluate("Array.from(document.querySelectorAll('.dir-seg button')).map(b => b.scrollWidth <= b.clientWidth)")
        ok(not over and all(seg), f'320px에서 넘침 없음 (가로 {over}, 버튼 {seg})')
        pg.locator('.dir-pick').scroll_into_view_if_needed(); pg.evaluate("window.scrollBy(0, -100)")
        pg.screenshot(path=f'{shots}/home-320.png')
        ok(not errs, f'페이지 오류 없음 {errs[:3]}')
        b.close()
except Exception as ex:
    fails.append('CRASH ' + traceback.format_exc().strip().splitlines()[-1][:300])
print('\n'.join(notes))
print('\n'.join(fails) if fails else '--- 모두 통과')
sys.exit(1 if fails else 0)

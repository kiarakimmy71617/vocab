"""단어장이 PDF로만 왔을 때: 단어장 PDF(번호 | 영어 | 단어 뜻 | 참고 표, 지문 머리줄 '[1] UNIT 10 · ANALYSIS | 제목 50개')
→ build.py import가 읽는 엑셀(번호 · 지문 · 영어 · 단어 뜻 · 참고)

  python3 _build/extract_vocab_pdf.py <단어장.pdf> <out.xlsx> [_build/src/<데이터이름>.joins.json]

- 글자를 세로 중심으로 묶어 화면의 한 줄씩 만들고(한글·영문 글꼴 높이 차이 흡수), x 위치로 칸을 나눈다.
- 칸 안에서 줄이 바뀐 곳은 PDF에 띄어쓰기 정보가 없다. 한글로 끝나고 한글로 시작하는 곳(또는 영문·')' 다음 한글)은
  자동으로 정할 수 없어서 '확인할 줄바꿈' 목록으로 출력한다 → 읽어 보고 joins 파일에 {"키": " " 또는 ""}로 적고 다시 돌린다.
  (줄 끝 글자 폭으로 판단하는 방법은 해송고 U10~16에서 17곳 중 10곳이 틀려서 안 씀)
- 확인할 것: 번호가 1부터 빠짐없이 이어지는지, 지문 머리줄의 'N개'와 실제 개수가 같은지 — 다르면 멈춘다.
- 2026-10-27 해송고1 올림포스 기본2 UNIT 10~16 단어장(1,116개, WeasyPrint로 만든 PDF)에서 처음 씀.
"""
import sys, re, json, collections
import pdfplumber, openpyxl

src, out = sys.argv[1], sys.argv[2]
joins = json.load(open(sys.argv[3], encoding='utf-8')) if len(sys.argv) > 3 else {}
COL = [('n', 30, 66), ('en', 66, 205), ('ko', 205, 345), ('note', 345, 600)]  # 단어장 PDF 표의 칸 위치(pt)
HANGUL = re.compile(r'[가-힣]')
LATIN = re.compile(r'[A-Za-z0-9]')
LIG = {'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬅ': 'st', 'ﬆ': 'st'}


def text_of(cs):
    cs = sorted(cs, key=lambda c: c['x0'])
    txt, prev = '', None
    for c in cs:
        if prev is not None and c['text'] != ' ' and not txt.endswith(' ') and c['x0'] - prev['x1'] > 0.9: txt += ' '
        txt += c['text']; prev = c
    return re.sub(r'\s+', ' ', re.sub('[ﬀ-ﬆ]', lambda m: LIG[m.group(0)], txt)).strip()


def visual_lines(page):
    cs = sorted((c for c in page.chars if c['text'].strip() or c['text'] == ' '), key=lambda c: (c['top'] + c['bottom']) / 2)
    lines, cur, cy = [], [], None
    for c in cs:
        y = (c['top'] + c['bottom']) / 2
        if cur and abs(y - cy) > 2.6: lines.append(cur); cur = []
        cur.append(c); cy = y if len(cur) == 1 else (cy * (len(cur) - 1) + y) / len(cur)
    if cur: lines.append(cur)
    return lines


segs, sections, title_lines = [], [], []
with pdfplumber.open(src) as pdf:
    for pi, page in enumerate(pdf.pages, 1):
        lines = [sorted(cs, key=lambda c: c['x0']) for cs in visual_lines(page)]
        head = next((sum((c['top'] + c['bottom']) / 2 for c in cs) / len(cs) for cs in lines
                     if text_of(cs).replace(' ', '') == '번호영어단어뜻참고'), 0)
        for cs in lines:
            full = text_of(cs); mid = (min(c['top'] for c in cs) + max(c['bottom'] for c in cs)) / 2
            if mid < head - 1:
                if pi == 1: title_lines.append(full)
                continue
            if mid > 805 or re.search(r'— \d+ / \d+$', full) or full.replace(' ', '') == '번호영어단어뜻참고' or full.startswith('▶'): continue
            if cs[0]['x0'] < 45 and full.startswith('['):
                m = re.match(r'\[(\d+)\]\s*(.*?)\s*\|\s*(.*?)\s*(?:(\d+)개)?\s*$', full)
                if not m: sys.exit(f'{pi}쪽 지문 머리줄을 못 읽음: {full}')
                name = re.sub(r'UNIT\s*(\d+)\s*·\s*', r'U\1 ', m.group(2)).strip()  # 'UNIT 10 · ANALYSIS' → 'U10 ANALYSIS'
                sec = {'name': name, 'count': int(m.group(4)) if m.group(4) else None}
                if sec['count'] is not None: sections.append(sec)
                segs.append((pi, mid, 'sec', name)); continue
            for col, a, b in COL:
                part = [c for c in cs if a <= c['x0'] < b]
                if part and text_of(part):
                    segs.append((pi, mid, 'cell', {'col': col, 'text': text_of(part)}))

rows, review, cur = [], [], None
for pi in sorted({s[0] for s in segs}):
    here = sorted((s for s in segs if s[0] == pi), key=lambda s: s[1])
    anchors = []
    for _, mid, kind, d in here:
        if kind == 'sec': cur = d
        elif d['col'] == 'n' and re.fullmatch(r'\d+', d['text']):
            anchors.append({'n': int(d['text']), 'mid': mid, 'sec': cur, 'cells': {'en': [], 'ko': [], 'note': []}})
    for _, mid, kind, d in here:
        if kind == 'cell' and d['col'] != 'n':
            if not anchors: sys.exit(f'{pi}쪽: 번호 없는 줄 {d["text"]}')
            min(anchors, key=lambda a: abs(a['mid'] - mid))['cells'][d['col']].append((mid, d['text']))
    for a in anchors:
        cell = {}
        for col, ls in a['cells'].items():
            ls.sort()
            txt = ls[0][1] if ls else ''
            for (_, p), (_, l) in zip(ls, ls[1:]):
                e, s = p[-1:], l[:1]
                key = f"{a['n']}|{col}|{p[-6:]}|{l[:6]}"
                if key in joins: sep = joins[key]
                elif e in '(-' or s in '),.:;': sep = ''
                elif (HANGUL.match(e) or LATIN.match(e) or e == ')') and HANGUL.match(s) or (LATIN.match(e) and l[:1] == '(' and HANGUL.match(l[1:2])):
                    sep = ''; review.append(f'  "{key}": ""    ← …{p[-14:]}⏎{l[:14]}…')
                else: sep = ' '
                txt += sep + l
            cell[col] = txt.strip()
        rows.append({'n': a['n'], 'sec': a['sec'], **cell})

rows.sort(key=lambda r: r['n'])
nums = [r['n'] for r in rows]
gaps = [k for k in range(1, max(nums) + 1) if k not in set(nums)]
dup = [k for k, v in collections.Counter(nums).items() if v > 1]
cnt = collections.Counter(r['sec'] for r in rows)
bad = [(s['name'], s['count'], cnt[s['name']]) for s in sections if s['count'] != cnt[s['name']]]
empty = [r['n'] for r in rows if not r['en'] or not r['ko']]
if gaps or dup or bad or empty:
    sys.exit(f'멈춤: 번호 빠짐 {gaps[:10]} / 중복 {dup[:10]} / 지문 개수 다름 {bad} / 영어·뜻 빈 행 {empty[:10]}')

wb = openpyxl.Workbook(); ws = wb.active; ws.title = '단어장'
for t in title_lines[:2]: ws.append([t])
ws.append([]); ws.append(['번호', '지문', '영어', '단어 뜻', '참고'])
for r in rows: ws.append([r['n'], r['sec'], r['en'], r['ko'], r['note']])
wb.save(out)
print(f'{out}: 단어 {len(rows)}개 · 지문 {len(sections)}개 (머리줄 개수와 모두 같음)')
if review:
    print(f'확인할 줄바꿈 {len(review)}곳 (지금은 붙여 씀 — 띄어 써야 하는 곳만 " "로 joins 파일에 적기):')
    print('\n'.join(review))

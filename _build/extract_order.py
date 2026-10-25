#!/usr/bin/env python3
"""본문학습지 PDF(좌 영어 원문 / 우 해석, 문장 번호 01~) → 순서 세트용 문장 뽑기

  python3 _build/extract_order.py text <pdf> <out.json> [--skeleton out.txt]   글자가 살아 있는 PDF
  python3 _build/extract_order.py ocr  <pdf> <out.json> [--skeleton out.txt]   글자가 그림으로 된 PDF(아이패드에서 내보낸 것 등)

결과 JSON: [{key, page, pages, rows: [{num, summary, text}]}]  — 지문 하나당 한 항목, 이어지는 쪽((계속))은 합쳐 둠.
--skeleton을 주면 import-order 형식의 뼈대(문장만, 흐름·단서는 비움)도 써 줌. 요약문 칸(summary)은 뼈대에서 뺌.

text: pdfplumber 글자 좌표로 'ENGLISH' 머리글 아래, '해석' 머리글보다 왼쪽에 있는 단어만 영어로 읽는다.
      (pdftotext -layout 줄을 글자 위치로 자르면 해석 칸 경계가 줄마다 흔들려 한글이 섞이는 PDF가 있음)
ocr:  300dpi로 그려서 회색 가로줄로 문장 칸을 나누고 영어 칸만 tesseract로 읽는다. 크기를 바꿔 한 번 더 읽어
      두 결과가 다른 문장을 'check' 목록에 남긴다 — 그 문장은 그림을 직접 보고 고칠 것. '|'는 거의 항상 'I'.
지문 머리줄(소제목)은 '… | 교재 p.N' 또는 '… | 문제지 p.N' 꼴이어야 한다(정상어학원 본문학습지 틀)."""
import sys, os, re, json, io, glob, subprocess, tempfile, difflib
from concurrent.futures import ThreadPoolExecutor

HEAD = re.compile(r'^\s*(?P<key>.+?)(?:\s*\(계속\))?\s*\|\s*(?:교재|문제지)\s*p\.(?P<page>\d+)')


def join_parts(parts):
    t = ''
    for part in parts:
        t += part if t.endswith('-') and not t.endswith(' -') else (' ' if t else '') + part
    return re.sub(r'\s+', ' ', t).strip()


# ---------- 글자 PDF ----------
def from_text(pdf_path):
    import pdfplumber, logging
    logging.getLogger('pdfminer').setLevel(logging.ERROR)
    passages = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ''
            m = next((HEAD.search(l) for l in text.split('\n') if HEAD.search(l)), None)
            if not m: continue
            words = page.extract_words()
            eh = [w for w in words if w['text'] == 'ENGLISH']; kh = [w for w in words if w['text'] == '해석']
            if not eh or not kh: continue
            kx, y0, left = kh[0]['x0'], eh[0]['bottom'] + 1, eh[0]['x0']
            eng = sorted([w for w in words if w['top'] > y0 and w['x1'] <= kx - 1], key=lambda w: (w['top'], w['x0']))
            lines = []
            for w in eng:
                if lines and abs(w['top'] - lines[-1]['top']) <= 3.5: lines[-1]['ws'].append(w)
                else: lines.append({'top': w['top'], 'ws': [w]})
            key = m.group('key').strip()
            cont = bool(passages) and passages[-1]['key'] == key
            expect = int(passages[-1]['rows'][-1]['num']) + 1 if cont and passages[-1]['rows'] else 1
            rows, cur = [], None
            for ln in lines:
                ws = sorted(ln['ws'], key=lambda w: w['x0']); toks = [w['text'] for w in ws]
                if toks[0] in ('지문의', '메모') or toks == ['요약문']: break
                if re.fullmatch(r'\d{1,3}', ' '.join(toks)) and ws[0]['x0'] - left > 100: continue  # 쪽 번호
                if toks[0] == '요약문' and len(toks) > 1 and re.fullmatch(r'\d{2}', toks[1]):
                    cur = {'num': toks[1], 'summary': True, 'parts': toks[2:]}; rows.append(cur); expect = int(toks[1]) + 1; continue
                if re.fullmatch(r'\d{2}', toks[0]) and int(toks[0]) == expect and abs(ws[0]['x0'] - left) < 6:
                    cur = {'num': toks[0], 'summary': False, 'parts': toks[1:]}; rows.append(cur); expect += 1; continue
                if cur is not None: cur['parts'] += toks
            if cont: passages[-1]['rows'] += rows; passages[-1]['pages'].append(pno)
            else: passages.append({'key': key, 'page': m.group('page'), 'pages': [pno], 'rows': rows})
    for p in passages:
        for r in p['rows']: r['text'] = join_parts(r.pop('parts'))
    return passages


# ---------- 그림 PDF ----------
X0, X1, LEFT, NUM = 170, 2310, (170, 1236), (175, 300)   # A4 300dpi 기준: 표 가로 범위, 영어 칸, 문장 번호 자리


def _ocr(png_bytes, psm, extra=()):
    return subprocess.run(['tesseract', 'stdin', 'stdout', '--psm', str(psm), *extra], input=png_bytes, capture_output=True).stdout.decode('utf-8', 'replace')


def _png(im):
    b = io.BytesIO(); im.save(b, 'PNG'); return b.getvalue()


def _runs(mask):
    out, start = [], None
    for y, v in enumerate(mask):
        if v and start is None: start = y
        if not v and start is not None: out.append((start, y)); start = None
    if start is not None: out.append((start, len(mask)))
    return out


def _page_rows(path):
    import numpy as np
    from PIL import Image
    g = Image.open(path).convert('L'); a = np.asarray(g).astype(int); H = a.shape[0]
    band = a[:, X0:X1]
    darks = _runs((band < 110).mean(1) > 0.5)
    lights = _runs((((band > 170) & (band < 248)).mean(1)) > 0.85)
    if len(darks) < 2: return None
    rule = darks[1]
    label = _ocr(_png(g.crop((X0, darks[0][1] + 10, X1, rule[0] - 2))), 7).strip()
    after = [l for l in lights if l[0] > rule[1]]
    if not after: return None
    eng = after[0][1]
    end = min([d[0] for d in darks[2:] if d[0] > eng] + [l[0] for l in lights if l[0] > eng and l[1] - l[0] > 12] + [H - 230])
    seps = [eng] + [l[0] for l in lights if eng < l[0] < end and l[1] - l[0] <= 12] + [end]
    rows = []
    for t, b in zip(seps, seps[1:]):
        if b - t < 60: continue
        if (np.asarray(g.crop((LEFT[0], t + 8, LEFT[1], b - 4))) < 120).mean() < 0.002: continue
        rows.append((t, b))
    return {'label': label, 'rows': rows}


def _read_row(path, t, b):
    import numpy as np
    from PIL import Image, ImageOps
    g = Image.open(path).convert('L')
    crop = g.crop((LEFT[0], t + 8, LEFT[1], b - 4))
    first = ' '.join(l.strip() for l in _ocr(_png(crop), 6).split('\n') if l.strip())
    big = crop.resize((int(crop.width * 1.6), int(crop.height * 1.6)), Image.LANCZOS)
    second = ' '.join(l.strip() for l in _ocr(_png(big), 4, ('--oem', '1')).split('\n') if l.strip())
    na = np.asarray(g.crop((NUM[0], t + 8, NUM[1], min(b, t + 110)))).astype(int)
    bw = Image.fromarray(np.where(na < 215, 0, 255).astype('uint8'))
    bw = ImageOps.expand(bw.resize((bw.width * 2, bw.height * 2)), border=20, fill=255)
    num = _ocr(_png(bw), 7, ('-c', 'tessedit_char_whitelist=0123456789')).strip()
    return num, first, second


def from_ocr(pdf_path):
    tmp = tempfile.mkdtemp(prefix='order-ocr-')
    subprocess.run(['pdftoppm', '-r', '300', '-gray', '-png', pdf_path, os.path.join(tmp, 'p')], check=True)
    pages = sorted(glob.glob(os.path.join(tmp, 'p-*.png')))
    structs = [(p, _page_rows(p)) for p in pages]
    jobs = [(p, t, b) for p, s in structs if s for (t, b) in s['rows']]
    with ThreadPoolExecutor(8) as ex: res = dict(zip(jobs, ex.map(lambda j: _read_row(*j), jobs)))
    passages = []
    for pno, (p, s) in enumerate(structs, 1):
        if not s or not s['rows']: continue
        page = (re.search(r'p\.\s*(\d+)', s['label']) or re.search(r'(\d+)\s*$', s['label']))
        page = page.group(1) if page else ''
        tail = s['label'].split('|')[-2] if s['label'].count('|') >= 2 else s['label']
        cont = bool(passages) and passages[-1]['page'] == page and '(' in tail   # '(계속)'은 OCR에서 괄호만 남음
        rows = []
        for (t, b) in s['rows']:
            num, first, second = res[(p, t, b)]
            norm = lambda x: re.sub(r'\s+', ' ', x.replace('|', 'I').replace("'", '’')).strip()
            A, B = norm(first).split(' '), norm(second).split(' ')
            diffs = [(' '.join(A[i1:i2]), ' '.join(B[j1:j2])) for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, A, B).get_opcodes() if op != 'equal']
            diffs = [d for d in diffs if not (d[0] == '' and len(d[1]) <= 3) and d[0].lower() != d[1].lower()]   # 번호 찌꺼기·대소문자 차이는 무시
            text = re.sub(r'(^|\s)\|(\s)', r'\1I\2', first).replace("'", '’')
            rows.append({'num': num, 'summary': False, 'text': text, 'check': diffs, 'at': [os.path.basename(p), t, b]})
        if cont: passages[-1]['rows'] += rows; passages[-1]['pages'].append(pno)
        else: passages.append({'key': s['label'], 'page': page, 'pages': [pno], 'rows': rows})
    for p in passages:
        for i, r in enumerate(p['rows'], 1): r['num'] = f'{i:02d}'   # 번호는 순서대로 다시 매김(작은 회색 숫자는 OCR이 자주 틀림)
    print(f'그린 쪽: {tmp}  (check에 걸린 문장은 여기 그림의 at 위치를 직접 볼 것)')
    return passages


if __name__ == '__main__':
    if len(sys.argv) < 4 or sys.argv[1] not in ('text', 'ocr'): sys.exit(__doc__)
    mode, pdf_path, out = sys.argv[1:4]
    skel = sys.argv[sys.argv.index('--skeleton') + 1] if '--skeleton' in sys.argv else None
    P = from_text(pdf_path) if mode == 'text' else from_ocr(pdf_path)
    json.dump(P, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for p in P:
        n = [r for r in p['rows'] if not r['summary']]
        chk = sum(1 for r in p['rows'] if r.get('check'))
        print(f"{p['key'][:56]:56} | p.{p['page']:>4} | 쪽 {p['pages']} | {len(n)}문장{' + 요약문' if len(n) < len(p['rows']) else ''}{f' | 확인할 문장 {chk}' if chk else ''}")
    print(f"→ {out}: {len(P)}지문 {sum(len([r for r in p['rows'] if not r['summary']]) for p in P)}문장")
    if skel:
        lines = ['# KEY | 세트 제목 | 설명(선택)']
        for p in P:
            lines.append(f"\n## {re.sub(r'\s*\|\s*', ' · ', p['key'])} · p.{p['page']} | 본문 | ")
            lines += [f"{r['text']} | " for r in p['rows'] if not r['summary']]
        open(skel, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        print(f'→ 뼈대 {skel} (지문 이름·세트 줄·흐름·단서를 채운 뒤 import-order)')

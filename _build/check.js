// 올리기 전 점검: node _build/check.js <page>.html
// 스크립트 구문 · 세트별 단어 수와 묶음 · 한→영 정답 인식(모든 표제어가 자기 자신을 정답으로 받는지) · 제출 폼 설정
// 순서 세트: 지문·문장 수, 똑같은 문장 없음, 섞기가 교과서 순서를 그대로 내지 않음, 채점이 정답/오답을 가림, 해설(흐름·문장 단서)이 빠짐없이 있음
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
const main = scripts[scripts.length - 1][1];
new vm.Script(main); // 구문 오류면 여기서 멈춤
const block = id => { const m = scripts.find(s => s[0].includes(`id="${id}"`)); return m ? JSON.parse(m[1]) : null; };
const sets = block('sets-data'), cfg = block('page-config') || {};
const pure = main.split('/*PURE-START*/')[1].split('/*PURE-END*/')[0];
const P = new Function(pure + '; return {prepareSet, makeBatches, matchItem, expTokens, prepareOrder, shuffleOrder, gradeOrder};')();
const bad = [];
for (const raw of sets) {
  if (raw.kind === 'order') {
    const set = P.prepareOrder(raw);
    const counts = set.passages.map(p => p.lines.length);
    const cued = set.passages.filter(p => p.cues.some(Boolean)).length;
    console.log(`${raw.title}: ${set.passages.length}지문 · 문장 [${counts.join('+')}] = ${counts.reduce((a, b) => a + b, 0)} · 해설 ${cued}/${set.passages.length}지문`);
    if (set.passages.length !== (raw.passages || []).length) bad.push(`${raw.title}: 문장이 2개 미만이라 빠진 지문 있음`);
    set.passages.forEach(p => {
      const low = p.lines.map(x => x.toLowerCase());
      if (new Set(low).size !== low.length) bad.push(`${raw.title} ${p.name}: 똑같은 문장이 두 번`);
      if (p.cues.length !== p.lines.length) bad.push(`${raw.title} ${p.name}: 단서 수가 문장 수와 다름`);
      const nc = p.cues.filter(Boolean).length;
      if (nc && nc < p.lines.length) bad.push(`${raw.title} ${p.name}: 단서가 일부 문장에만 있음 (${nc}/${p.lines.length})`);
      if (nc && !p.flow) bad.push(`${raw.title} ${p.name}: 흐름 요약이 없음`);
      const n = p.lines.length, ident = [...Array(n).keys()];
      for (let t = 0; t < 50; t++) {
        const o = P.shuffleOrder(n);
        if (o.length !== n || new Set(o).size !== n) { bad.push(`${p.name}: 섞은 결과가 순열이 아님`); break; }
        if (o.every((v, i) => v === i)) { bad.push(`${p.name}: 섞었는데 교과서 순서 그대로`); break; }
        if (P.gradeOrder(o, n).ok) { bad.push(`${p.name}: 틀린 순서를 정답 처리`); break; }
      }
      const g = P.gradeOrder(ident, n);
      if (!g.ok || g.right !== n) bad.push(`${p.name}: 교과서 순서를 정답으로 안 받음`);
      if (P.gradeOrder(ident.slice(0, n - 1), n).ok) bad.push(`${p.name}: 덜 놓았는데 정답 처리`);
    });
    continue;
  }
  const set = P.prepareSet(raw);
  const b = P.makeBatches(set, set.items.map((_, i) => i)).map(x => x.length);
  const off = set.items.filter(i => !i.ke).map(i => i.en);
  console.log(`${raw.title}: ${set.items.length}개 · 묶음 ${b.length} [${b.join('+')}]${off.length ? ` · 한→영 제외 ${off.join(', ')}` : ''}`);
  set.items.forEach(it => {
    if (!it.ke) return;
    const bare = P.expTokens(it.vars[0]).filter(x => !x.ph).map(x => x.w).join(' ');
    if (!P.matchItem(it.en, it)) bad.push('표제어 그대로 입력: ' + it.en);
    if (!P.matchItem(bare, it)) bad.push('자리표시 빼고 입력: ' + it.en + ' → ' + bare);
  });
}
const ids = sets.map(s => s.id), dupIds = ids.filter((x, i) => ids.indexOf(x) !== i);
if (dupIds.length) bad.push('세트 ID 중복: ' + dupIds.join(', '));
if (cfg.form && !/^https:\/\/docs\.google\.com\/forms\//.test(cfg.form.url || '')) bad.push('제출 폼 주소가 이상함');
const title = (html.match(/<title>([^<]*)<\/title>/) || [])[1] || '-';
console.log(`탭 제목: ${title} · 학교: ${cfg.school || '-'} · 제출 폼: ${cfg.form ? '연결됨' : '없음'} · 직접 넣기: ${cfg.paste === false ? '숨김' : '보임'}`);
if (bad.length) { console.log('실패\n  ' + bad.join('\n  ')); process.exit(1); }
console.log('점검 통과');

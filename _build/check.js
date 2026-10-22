// 올리기 전 점검: node _build/check.js <page>.html
// 스크립트 구문 · 세트별 단어 수와 묶음 · 한→영 정답 인식(모든 표제어가 자기 자신을 정답으로 받는지) · 제출 폼 설정
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
const main = scripts[scripts.length - 1][1];
new vm.Script(main); // 구문 오류면 여기서 멈춤
const block = id => { const m = scripts.find(s => s[0].includes(`id="${id}"`)); return m ? JSON.parse(m[1]) : null; };
const sets = block('sets-data'), cfg = block('page-config') || {};
const pure = main.split('/*PURE-START*/')[1].split('/*PURE-END*/')[0];
const P = new Function(pure + '; return {prepareSet, makeBatches, matchItem, expTokens};')();
const bad = [];
for (const raw of sets) {
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
console.log(`학교: ${cfg.school || '-'} · 제출 폼: ${cfg.form ? '연결됨' : '없음'} · 직접 넣기: ${cfg.paste === false ? '숨김' : '보임'}`);
if (bad.length) { console.log('실패\n  ' + bad.join('\n  ')); process.exit(1); }
console.log('점검 통과');

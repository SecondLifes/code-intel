// static/index.html'deki renderCompareTable() + srcCard() GERÇEK koşumu.
//
// Kilitlenen bağ: tablodan "ilgili fonksiyona git" ancak tablonun ürettiği
// hedef, kaynak kartının gerçek DOM id'siyle AYNI şemayı kullanırsa çalışır
// (srcCard: id="s"+hit.id  <->  cmpJump: $('s'+hit.id)). Bu iki yer birbirinden
// habersiz değişirse atlama SESSİZCE bozulur — test tam olarak bunu yakalar.
//
// Çıktı: tek satır JSON.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const HTML = fs.readFileSync(process.argv[2] || path.join(ROOT, 'static', 'index.html'), 'utf-8');

function extractFn(src, name) {
  for (const head of [`function ${name}(`, `async function ${name}(`]) {
    const start = src.indexOf(head);
    if (start < 0) continue;
    let depth = 0;
    for (let j = src.indexOf('{', start); j < src.length; j++) {
      if (src[j] === '{') depth++;
      else if (src[j] === '}' && --depth === 0) return src.slice(start, j + 1);
    }
  }
  throw new Error(`fonksiyon bulunamadi: ${name}`);
}

globalThis.T = (tr) => tr;
globalThis.esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
globalThis.escJs = (s) => String(s).replace(/'/g, "\\'");
globalThis.hljsLangFor = () => 'delphi';
globalThis.inferLangFromUnit = () => 'pascal';
globalThis.whyText = () => '';
globalThis.CMP_HITS = [
  { id: 4242, collection: 'mORMot2', name: 'CompressMem', unit: 'core.pas', line_start: 10, line_end: 20, code: 'x', score: '0.1' },
  { id: 7777, collection: 'mORMot2', name: 'Compress', unit: 'core.pas', line_start: 30, line_end: 40, code: 'y', score: '0.1' },
];

const code = ['cmpScoreClass', 'renderCompareTable', 'srcCard'].map((n) => extractFn(HTML, n)).join('\n') +
  '\nglobalThis.renderCompareTable=renderCompareTable; globalThis.srcCard=srcCard;';
new Function(code)();

const rows = [
  { i: 1, name: 'CompressMem', unit: 'core.pas', collection: 'mORMot2', stability: 9, performance: 4, reason: 'r1' },
  { i: 2, name: 'Compress', unit: 'core.pas', collection: 'mORMot2', stability: 5, performance: 8, reason: 'r2' },
];
const table = globalThis.renderCompareTable(rows);
const card = globalThis.srcCard(globalThis.CMP_HITS[0], 0);

// srcCard'in gercek kart id'si  vs  tablonun atlama hedefi
const cardId = (card.match(/<div class="src" id="([^"]+)"/) || [])[1];
const jumpIdx = [...table.matchAll(/cmpJump\((\d+)\)/g)].map((m) => +m[1]);
const targetFromTable = jumpIdx.length ? 's' + globalThis.CMP_HITS[jumpIdx[0] - 1].id : null;

console.log(JSON.stringify({
  jump_target_matches_card_id: cardId === targetFromTable,
  card_id: cardId,
  target_from_table: targetFromTable,
  // isim VE dosya adi ayri ayri tiklanabilir olmali (kullanici: "dosya/fonksiyon adina")
  jump_hooks: jumpIdx.length,
  jump_indexes_are_1_based_and_in_range: jumpIdx.every((i) => i >= 1 && i <= globalThis.CMP_HITS.length),
  // her satirda dogrudan "Tarayicida Goster"
  browser_buttons: [...table.matchAll(/cmpShowInBrowser\((\d+)\s*,/g)].map((m) => +m[1]),
  rows_rendered: (table.match(/<tr>/g) || []).length - 1,   // basligi dus
}));

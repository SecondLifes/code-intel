// static/index.html'deki run() + runAskStream() eş zamanlılık davranışının GERÇEK
// koşumu — string araması değil. index.html'den bu iki fonksiyon (ve gerektiği
// kadar global) çıkarılıp sahte bir DOM üzerinde çalıştırılır.
//
// Yakaladığı hata (kullanıcı ekran görüntüsü): akış sürerken ikinci bir arama
// başlarsa $('out') sıfırlanır, #ans/#anssrc/#cmpwrap DOM'dan silinir ve hâlâ
// dönen ESKİ akış döngüsü null'a innerHTML yazarak
// "TypeError: Cannot set properties of null (setting 'innerHTML')" fırlatırdı.
//
// Çıktı: tek satır JSON — pytest tarafı bunu okur.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// argv[2] ile başka bir index.html verilebilir — testin GERÇEKTEN hatayı
// yakaladığını düzeltme ÖNCESİ sürüme karşı koşarak doğrulamak için.
const HTML = fs.readFileSync(process.argv[2] || path.join(ROOT, 'static', 'index.html'), 'utf-8');

/** `async function <ad>(` ile başlayan bloğu süslü parantez sayarak çıkarır. */
function extractFn(src, name) {
  const start = src.indexOf(`async function ${name}(`);
  if (start < 0) throw new Error(`fonksiyon bulunamadi: ${name}`);
  let i = src.indexOf('{', start), depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}' && --depth === 0) return src.slice(start, j + 1);
  }
  throw new Error(`kapanmayan blok: ${name}`);
}

// ---------------- sahte DOM ----------------
// Gerçek davranışı taklit eder: #out'a yazmak icindeki id'leri YOK EDER; yazilan
// html'de id="x" varsa o element yeniden dogar. Eksik element icin $() null
// doner — null.innerHTML ataması JS'te zaten TypeError firlatir, yani hatayi
// simule etmiyoruz, gercekten olusturuyoruz.
const els = new Map();
function mkEl(id) {
  return {
    id, _html: '', value: '5', disabled: false, scrollHeight: 10,
    classList: { add() {}, remove() {}, contains: () => false, toggle() {} },
    get innerHTML() { return this._html; },
    set innerHTML(v) {
      this._html = String(v);
      if (this.id === 'out') {
        for (const k of ['ans', 'anstoggle', 'ansmeta', 'anssrc', 'cmpwrap', 'hitlist', 'reslabel', 'loadmore', 'cmp-btn']) els.delete(k);
        for (const m of String(v).matchAll(/id="([^"]+)"/g)) els.set(m[1], mkEl(m[1]));
      }
    },
    focus() {}, remove() { els.delete(this.id); },
  };
}
for (const id of ['q', 'go', 'out', 'rk-select']) els.set(id, mkEl(id));
const $ = (id) => els.get(id) ?? null;

// ---------------- akış denetimi ----------------
// 1. akış elle beslenir, boylece "yarida kalmisken ikinci arama" durumu kesin
// olarak kurulabilir (zamanlama yarisina birakilmaz).
// Her akışın KENDİ kapısı var — iki eş zamanlı akış tek bir kapıyı paylaşırsa
// birbirinin okumasını yutar ve senaryo anlamsızlaşır.
const enc = new TextEncoder();
const readers = [];
const tick = async (n = 1) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0)); };

function sseReader() {
  const st = { pending: null };
  readers.push(st);
  return {
    read: async () => {
      const v = await new Promise((res) => { st.pending = res; });
      return v === null ? { done: true, value: undefined } : { done: false, value: enc.encode(v) };
    },
  };
}

/** idx numaralı akışa bir SSE bloğu (ya da bitiş için null) verir. */
async function feed(idx, v) {
  for (let i = 0; i < 100 && !readers[idx]?.pending; i++) await tick();
  const st = readers[idx];
  if (!st?.pending) return false;
  const p = st.pending; st.pending = null; p(v);
  await tick(3);
  return true;
}

let ABORTED = 0;
globalThis.fetch = async (url, opt) => {
  if (opt?.signal) opt.signal.addEventListener('abort', () => { ABORTED++; });
  if (String(url).includes('/stream')) {
    return { ok: true, body: { getReader: () => sseReader() } };
  }
  return { ok: true, json: async () => ({ hits: [], total: 0, ms: 1 }) };
};

// ---------------- run()/runAskStream()'in ihtiyac duydugu globaller ----------------
globalThis.$ = $;
globalThis.T = (tr) => tr;
globalThis.esc = (s) => String(s);
globalThis.err = (m) => `<div class="answer">HATA ${m}</div>`;
globalThis.none = () => '<div class="hero"></div>';
globalThis.renderHitList = () => '';
globalThis.applyCodeEnhancements = () => {};
globalThis.searchBody = () => ({});
globalThis.srcCard = () => '<div class="src"></div>';
globalThis.citeFmt = (t) => t;
globalThis.updateAnsToggle = () => {};
globalThis.chatChip = () => '';
globalThis.persistChat = () => {};
globalThis.localStorage = { getItem: () => '', setItem() {} };
globalThis.LANG = 'tr'; globalThis.MODE = 'hybrid';
globalThis.SELECTED_COLLS = ['mORMot2'];
globalThis.CHAT_HISTORY = [];
globalThis.LAST_Q = ''; globalThis.LAST_OFFSET = 0; globalThis.ALL_HITS = [];
globalThis.CMP_Q = ''; globalThis.CMP_HITS = [];
globalThis.RUN_SEQ = 0; globalThis.RUN_ABORT = null;
globalThis.ACT = 'research';

// Fonksiyonlar globalThis uzerine kurulur (var/function scope taklidi).
const code = extractFn(HTML, 'run') + '\n' + extractFn(HTML, 'runAskStream') + '\n' +
  'globalThis.run=run; globalThis.runAskStream=runAskStream;';
new Function(code)();

// ---------------- senaryo ----------------
const errors = [];
process.on('unhandledRejection', (e) => errors.push(String(e && e.message || e)));

const result = { crashed: null, aborted: 0, out_belongs_to_second: null, errors };
try {
  $('q').value = 'ayrac yardimi ile string bolme fonksiyonu';
  const p1 = run();                       // 1. arama (Derin) — akmaya basliyor
  await tick(3);
  await feed(0, 'event: meta\ndata: {"hits":[],"total":0}\n\n');   // #ans artik var

  // KRITIK AN: 1. akis yarida iken kullanici "Bul"a gecip Enter'a basiyor.
  // 'find' dali BILEREK secildi: o dal #ans'i YENIDEN YARATMAZ, yani eski
  // akisin yazacagi dugum kalici olarak yok olur. (Ikinci arama da 'research'
  // olsaydi kendi #ans'ini yaratir ve hatayi maskelerdi — o durumda da hata
  // kaybolmaz, sadece sekil degistirir: eski akis YENI aramanin cevap kutusuna
  // yazmaya baslar. Ayni RUN_SEQ korumasi ikisini birden kapatir.)
  globalThis.ACT = 'find';
  $('q').value = 'ikinci sorgu';
  const p2 = run();
  await tick(5);

  // 1. akisi beslemeye DEVAM et — eski kodda tam burada patliyordu.
  await feed(0, 'data: {"t":"merhaba"}\n\n');
  await feed(0, null);
  await p1;

  // Hata ekrana NASIL yansiyor: eski kodda TypeError run()'in kendi catch'ine
  // dusuyor ve err() ile kirmizi kutu olarak ciziliyordu — kullanicinin ekran
  // goruntusundeki tam olarak bu. Yani dogru olcum "islenmemis istisna" degil,
  // #out'un ICERIGI.
  result.out_html = String($('out').innerHTML);
  result.crashed = /Cannot set properties of null/.test(result.out_html)
    ? 'TypeError #out\'a yazildi'
    : (errors.find((e) => /Cannot set properties of null/.test(e)) || null);
  result.aborted = ABORTED;
  // Ekranda 2. aramanin (bos sonuc) ciktisi olmali, hata kutusu DEGIL.
  result.out_belongs_to_second = !/HATA/.test(result.out_html);

  await p2;              // 'find' dali akis kullanmaz, dogrudan biter
  await tick(3);

} catch (e) {
  result.crashed = String(e && e.message || e);
}
console.log(JSON.stringify(result));

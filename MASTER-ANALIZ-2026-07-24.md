# CodeIntel — Birleşik Master Analiz ve Yol Haritası (24 Temmuz 2026)

Üç bağımsız analizin sentezi:

| Kaynak | Belge | Karakter | Güncellik notu |
|---|---|---|---|
| **Claude** | `ANALIZ-2026-07-24.md` | Etki/emek puanlı 16 özellik + sprint planı | Güncel (dünkü 7 özellik paketi sonrası) |
| **Codex** | `CODEINTEL-EK-OZELLIK-MIMARI-ANALIZI-2026-07-24.md` | Derin mimari risk analizi (P0/P1/P2) + 10 özellik | Güncel; kod doğrulamalı |
| **Gemini** | `implementation_plan.md` | 3 özellik + 2 yapısal öneri | **Kısmen bayat**: önerdiği Streaming (B) dün gece zaten yapıldı; "kararsız chunk ID" tespiti (E) bugünkü kod için geçersiz (ID'de satır numarası bilinçli olarak YOK, chunker.py:87-93'te belgeli) |

---

## 1. Konsensüs Matrisi — üç analiz nerede buluşuyor?

| Özellik / Tespit | Claude | Codex | Gemini | Birleşik karar |
|---|:-:|:-:|:-:|---|
| **Sembol/referans grafiği** (kalıtım, uses, referanslar) | ✅ B1+B2 | ✅ #1 | ✅ C | **EN GÜÇLÜ KONSENSÜS — ana yön bu** |
| **Agent bağlam derinliği** (context pack / derin araştırma) | ✅ C1 | ✅ #2 | ~ (1-hop bağlam) | Konsensüs — sembol grafiğinin üstüne |
| **Eval büyütme + kalite kapısı** | ✅ E1 | ✅ #4 | — | Konsensüs — her arama işinin ön koşulu |
| **Arama geri bildirimi** (👍/👎, açıklanabilir sıralama) | ~ (analitik altyapısı dün kuruldu) | ✅ #5 | — | Hızlı kazanım — telemetri şeması hazır |
| **Kopya/benzer kod raporu** | ~ (find_similar dün eklendi) | ✅ #8 "en hızlı teslim" | — | Hızlı kazanım — altyapı hazır |
| **panel.py modülerleşme** | ✅ (düşük öncelik demiştim) | ✅ P1 (ön koşul diyor) | — | Codex haklı: büyük özelliklerden ÖNCE |
| Streaming SSE sohbet | ✅ yapıldı | — | ✅ önerdi | **TAMAMLANDI** (23 Tem gecesi) |
| Çok dilli chunker | ✅ #1 stratejik | ⛔ ertele | — | **ÇELİŞKİ — karar: §4.1** |
| Agentic kod düzenleme (diff üret/uygula) | — | ⛔ ertele | ✅ #1 önerisi | **ÇELİŞKİ — karar: §4.2** |
| Git-aware etki analizi | — | ✅ #3 | — | Orta vade (Faz 3) |
| Bellek/OOM riskleri (indeksleme + call graph + export) | ~ | ✅ P1 | ✅ D | Konsensüs — temel pakete |

---

## 2. Birleşik Teknik Borç Listesi (özelliklerden önce)

Kod üzerinde doğrulanmış, üç analizden birleştirilmiş:

### P0 — Veri bütünlüğü
1. **İş yarış durumu (DOĞRULANDI):** `/api/index/start` (panel.py:890) çalışan iş kontrolünde `diffing`/`linking` fazlarını atlıyor — bu fazlardayken ikinci iş başlatılabilir ve `STATE` ezilir. *(Codex; tek satırlık ucuz düzeltme)*
2. **Merge'de sessiz ID çakışması:** 48-bit ID iki kütüphanede aynı yol+imzada çakışırsa merge ikinci noktayı **sessizce atlar** → birleşik koleksiyonda veri kaybı. En azından collision raporu verilmeli. *(Codex)*
3. **"Tam kod" tam değil:** payload `code[:4000]` kesiliyor, >400 satırlık düğümler tamamen atlanıyor; `get_chunk(full_code=True)` adına rağmen kesik dönebiliyor. `truncated` bayrağı + diskten tam kaynak okuma yolu (reveal altyapısı zaten var). *(Codex)*
4. **Atomik olmayan indeks güncellemesi:** canlı koleksiyon üzerinde çalışılıyor; staging + alias-swap modeli hedeflenmeli. İş durumu yalnız bellekte (panel restart → kayıp). *(Codex)*

### P1 — Ölçek ve yapı
5. **Bellek baskısı (3 nokta):** diffing scroll'u tüm vektörleri RAM'e alıyor (Jedi 375K × dense+sparse → GB'lar); `_link_call_graph` aynı şekilde + tamamını yeniden upsert ediyor; export/import tüm dosyayı bellekte kuruyor. Streaming/parçalı işleme. *(Gemini D + Codex)*
6. **panel.py monoliti (1193 satır):** services/routes ayrımı — mikroservis DEĞİL, modüler monolit. Büyük özelliklerin ön koşulu. *(Codex P1; Claude aynı tespit, önceliği Codex'ten alıyoruz)*
7. **Yapılandırma tek kaynak değil (DOĞRULANDI):** mcp-config.json'daki `qdrant_url`/`ollama_url` fiilen **etkisiz** — retrieval.py sabit 127.0.0.1 kullanıyor. Tek `Settings` (env > dosya > varsayılan). *(Codex)*
8. **Güvenlik sınırı:** `/api/view-file` mutlak yol alıyor (path traversal), viewer iframe'i sandbox'sız, auth varsayılan kapalı. Yerelde risk düşük; LAN'dan ÖNCE şart. *(Codex)*

### P2 — Bakım
9. **`src/indexer.py` tuzak/ölü kod** — eski şemayla koleksiyon açar; silinmeli. *(Claude)*
10. **Tool tanımları 4 yerde elle çoğaltılıyor** (mcp_server, panel, api.html×2) — tek registry veya en azından contract testi. *(Codex)*
11. **Test kapsamı dar:** tüm otomatik testler chunker'da; füzyon/dedup/merge/import-export/SSE/MCP sözleşmeleri testsiz. *(Codex + Claude E3)*
12. `data/` test artıkları; `default_collections: ["unidac"]` gözden geçirilmeli; dünkü değişiklikler commit'lenmeli. *(Claude)*

---

## 3. Birleşik Yol Haritası

### Faz 0 — Temel Paket (1 hafta) *"genişlemeye hazırlık"*
Konsensüs: büyük özellikler bu temelin ÜSTÜNE gelmeli.
- P0 düzeltmeleri: iş fazı kontrolü, merge collision raporu, truncated bayrağı + tam kaynak yolu
- Bellek: diffing'i hash-only scroll'a çevir (vektör kopyalama yerine kısmi güncelleme), link-graph'ı değişen unit'lerle sınırla
- `Settings` tekleştirme + `indexer.py` temizliği + commit disiplini
- **Eval büyütme:** golden set 10→50+ (sıfır-sonuç sorgulardan), koleksiyon başına set, nDCG + p50/p95, `--compare` A/B

### Faz 1 — Hızlı Ürün Kazanımları (1 hafta)
Hepsi mevcut altyapının ürünleştirilmesi (düşük risk, yüksek görünürlük):
- **Arama geri bildirimi**: sonuç kartında 👍/👎 + "neden geldi" (dense/sparse sırası, isim boost'u) → `_search_log`'a; golden set'e tek tık aday ekleme
- **Kopya kod raporu**: `find_similar` üstüne koleksiyon-geneli benzerlik taraması + kümeleme (Codex: "en hızlı teslim edilebilir yüksek görünürlüklü özellik")
- **Otomatik yedek** (export→`backups\` rotasyonlu) + açılışta otomatik başlatma (schtasks)
- Sorgu genişletme pilotu (TR→EN rewrite, eval'le kanıt; geçemezse çöpe)

### Faz 2 — Ayırt Edici Kod Zekâsı (2-3 hafta) *"üç analizin ortak ana yönü"*
- **Sembol/referans grafiği**: kalıtım (`class X = class(Y)`), uses-bağımlılıkları, interface implementasyonları — **ayrı sembol/edge koleksiyonunda** (Codex'in uyarısı: `_link_call_graph`'ı büyüterek DEĞİL; payload'a liste gömme yaklaşımı 375K'lık Jedi'da ölçeklenmez)
- MCP: `find_references`, `get_type_hierarchy` + panelde mermaid görselleştirme
- **`get_context_pack(task, token_budget, ...)`**: sembol + tanım + çağıranlar + ilgili tipler + testleri bütçe içinde seçen tek çağrı — CodeIntel'i "arama aracı"ndan "ajan bağlam motoruna" çevirir
- **Derin araştırma modu** (Claude C1): context pack'i çok adımlı orkestrasyonla kullanan sohbet modu — Gemini'nin "1-hop bağlam enjeksiyonu" fikri bunun basit ilk adımı olarak Faz 2 başında yapılabilir

### Faz 3 — Repository Zekâsı (2+ hafta)
- Git provenance (repo_id, commit_sha, indexed_at manifest'i) → staging+alias'lı atomik indeks nesli bununla birlikte gelir
- Diff/etki analizi ("bu değişiklik hangi çağıranları/public API'leri etkiler")
- Kaydedilmiş çalışma alanları (workspace) + otomatik unit/API dokümantasyonu

### Faz 4 — Platform ve Ölçek
- **Çok dilli chunker** (karar: §4.1) — parser abstraction + dil başına golden set ile
- Rol tabanlı auth + güvenli LAN/HTTP MCP + streaming import/export
- (Ancak talep doğarsa) çoklu kullanıcı

---

## 4. Çelişki Kararları

### 4.1 Çok dilli chunker: Claude "#1 stratejik" vs Codex "ertele"
**Birleşik karar: Faz 4'e (ama pilotu Faz 2 sonunda değerlendir).** Codex'in iki itirazı yerinde: (1) Delphi uzmanlığı — sembol grafiği gibi derinlik özellikleri — seyrelmeden önce tamamlanmalı; (2) parser abstraction kurulmadan dil eklemek chunker'ı kırılganlaştırır. Claude'un "altyapı zaten dil-bağımsız" tespiti doğru ama *arama* için doğru, *sembol grafiği* için değil — grafik dil-özel kurallara dayanır. Sıralama: önce Delphi'de derinleş (Faz 2), platform hamlesi sonra. Faz 2 biterken tek dillik (C# veya C++) sınırlı bir pilot, parser abstraction'ı test etmek için öne alınabilir.

### 4.2 Agentic kod düzenleme: Gemini "#1 öneri" vs Codex "ertele"
**Birleşik karar: ertele; okuma-modunda küçük bir ara adım kabul.** Codex'in gerekçesi güçlü: ürünün değeri güvenilir read-only zekâda; diski değiştiren agent hem güven hem güvenlik sınırı (P1 güvenlik borcu kapanmadan) ister. Gemini'nin fikrinin riski düşük dilimi — "öneri diff'i **yalnızca göster**, asla uygulama" — Faz 2'deki context pack'ten sonra ucuzlar ve istenirse o zaman eklenir. "Apply to disk" yalnız Faz 4 güvenlik sınırlarından sonra düşünülür.

### 4.3 Gemini'nin geçersiz/bayat maddeleri (kayıt için)
- **B (Streaming):** 23 Tem gecesi `/api/ask/stream` + UI ile tamamlandı.
- **E (Chunk ID satır numarası):** Bugünkü chunker'da ID'ye satır numarası bilinçli olarak katılmıyor (chunker.py'de belgeli, canlı test edilmiş) — tespit eski bir sürüme ait.
- **D (OOM):** Geçerli ve değerli — Faz 0'a alındı (Codex'in bellek tespitleriyle birleştirildi).

---

## 5. Net Birleşik Öneri

> **Ana yön (3/3 konsensüs): Delphi sembol grafiği + agent context pack.** Ama doğrudan değil — önce 1 haftalık Faz 0 temel paketi (P0 düzeltmeleri + bellek + eval büyütme), araya 1 haftalık hızlı kazanımlar (geri bildirim, kopya kod raporu, yedek), sonra ana hamle. Çok dillilik ve kod-düzenleme bilinçli olarak sona bırakıldı: ilki uzmanlık seyrelmesin diye, ikincisi güven ve güvenlik sınırı kurulmadan diski değiştirmemek için.

| Faz | Süre | İçerik | Kaynak analiz |
|---|---|---|---|
| 0 | ~1 hafta | P0 + bellek + Settings + eval büyütme | Codex temel + Gemini D + Claude E1 |
| 1 | ~1 hafta | Geri bildirim, kopya kod raporu, yedek, autostart | Codex #5/#8 + Claude D1/D2/A2 |
| 2 | 2-3 hafta | Sembol grafiği, find_references, context pack, derin araştırma | Codex #1/#2 + Claude B1/B2/C1 + Gemini C |
| 3 | 2+ hafta | Git provenance, etki analizi, workspace | Codex #3/#6 |
| 4 | — | Çok dil, auth/LAN, ölçek | Claude A1 + Codex Aşama 4 |

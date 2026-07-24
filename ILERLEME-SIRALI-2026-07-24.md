# CodeIntel — Bağımlılık-Sıralı Yol Haritası Uygulama Raporu (24 Temmuz 2026, akşam)

12 sıralık birleşik planın **1-9'u tamamen bitti ve commit'lendi.** 23/23 test yeşil, tüm özellikler canlı sistemde doğrulandı. MCP **16 tool'a** çıktı.

## Sıra Karnesi

| Sıra | İş | Durum | Commit |
|---|---|---|---|
| 1 | API smoke + MCP/REST sözleşme testleri | ✅ | `7e2dcd1` |
| 2 | Modüler monolit (panel.py 1518→80 satır, services/+api/) | ✅ | `1a1bb64` |
| 3 | Tool registry (tek kayıt; REST uçları imzadan otomatik) | ✅ | `8bc8278` |
| 4 | Güvenlik sınırı (path allowlist, sandbox, admin kilidi, rate limit, audit) | ✅ | `5b765c9` |
| 5 | Chunker v2 (repo-ID + unithead/uses + dev-metod + parser soyutlama) + **GPU'suz ID migrasyonu** | ✅ | `3edff1b` |
| 6 | Atomik import (doğrula-önce-sil) | ✅ | `3edff1b` |
| 7 | **get_context_pack** — token bütçeli agent bağlam motoru | ✅ | `de3acdf` |
| 8 | **Derin araştırma modu** (🔬 UI + SSE adımlar + [S1] atıflı sentez) | ✅ | `de3acdf` |
| 9 | Yaprak paket: workspace, oto-dok, yanıt önbelleği, MMR, vurgu, kalıcı sohbet+md, hiyerarşi UI, log rotasyonu, impact head, sorgu genişletme | ✅ | `3edff1b` |
| 10 | Çok dil pilotu (C#/C++) | ⏳ sonraki oturum — parser soyutlaması hazır, "bir sınıf ekle" işi |
| 11 | Paylaşım: API-key UI/roller, LAN MCP, agentic edit (göster-only) | ⏳ sonraki oturum |
| 12 | Öğrenen reranker | ⏸ veri-kapılı: yeterli 👍/👎 birikince |

## Öne Çıkan Sonuçlar

**GPU'suz ID migrasyonu tezi canlıda kanıtlandı:** 513K nokta repo-kimlikli v2 ID'lere, vektörler payload'dan kopyalanarak taşındı — Jedi 375K nokta ~8 dk migrasyon + 102 sn reindex (yeniden embed edilseydi ~85 dk GPU). mORMot2 111K: 26 sn reindex. Çeviri önbellekleri (tr/tr_deep) payload ile birlikte taşındı.

**uses-bağımlılık grafı canlı:** `get_unit_deps("unidac","MemData.pas")` → 176 bağımlı dosya. Tüm koleksiyonlarda toplam ~100K+ sembol kenarı (kalıtım + interface + uses).

**Eval (v2 indeks, 60 soru):** baseline Recall %83 / MRR 0.634 → **rerank %92 / 0.681 / nDCG 0.738** (+152ms). **Sorgu genişletme pilotu eval kapısından geçemedi:** +%2 recall'a karşılık 12× gecikme, MRR sabit → bilinçli olarak opt-in bırakıldı (ölçümle karar, tahminle değil).

**Kapsam deliği kapandı:** >400 satırlık dev metodlar artık indekste (huge=true, tam kod diskten); her dosyanın unithead chunk'ı aranabilir.

## Sonraki Oturum İçin Notlar
- Sıra 10: `chunker.py`'deki `_CHUNKERS` kaydına C#/C++ sınıfı eklemek + dil golden set'i. tree-sitter-language-pack kurulu.
- Sıra 11: güvenlik sınırı (Sıra 4) hazır olduğundan LAN açılımı artık güvenli temele oturuyor.
- Bilinen küçük borçlar: staging+alias tam indeks-nesli modeli (in-place artımlı akış + atomik import + yedeklerle risk büyük ölçüde kapatıldı; alias modeli istenirse ayrı iş), araştırma modunun kaynak kartlarında skor alanı boş görünüyor (kozmetik).

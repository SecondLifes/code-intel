# Code-Intel — Gece Vardiyası Kurulum Raporu (2026-07-22/23)

Kapsam: `E:\system\dev\son ayrım\01-Component\2026.6.6\UniDAC 10.3.0\Source`
(520 .pas, 538.064 satır, 84 MB — pilot korpus)

## ÇALIŞTIRILARAK doğrulananlar (statik okuma değil)

| Bileşen | Durum | Kanıt |
|---|---|---|
| Python 3.12.13 (uv ile) | ✅ | `uv python install 3.12` → venv kuruldu |
| tree-sitter + language-pack | ✅ Pascal grameri PAKETTE VAR | Uni.pas: 643 bildirim + 324 metod, satır aralıklarıyla |
| Korpus parse hızı | ✅ 314 dosya/sn | 520 dosya 1.7 sn'de, **20.590 metod gövdesi** çıktı |
| Parse hata düğümü oranı | ⚠️ %73 dosyada yerel hata | Klasik {$IFDEF} etkisi — chunk çıkarımını ENGELLEMİYOR; Phase-1'de hafif IFDEF ön-çözümleyici planlandı |
| Qdrant 1.18.3 (Windows binary) | ✅ ÇALIŞIYOR | healthz OK, http://localhost:6333, storage: ./data/qdrant |
| Embed → upsert → TÜRKÇE arama | ✅ UÇTAN UCA | "veritabanı bağlantısını açan ve kapatan fonksiyon" → TUniMetaData.EndConnection @0.81 |
| fastembed'de BGE-M3 | ❌ YOK (canlı doğrulandı) | `list_supported_models()` boş döndü → Phase 3'te BGE-M3 `sentence-transformers` ile gelecek (stack'te zaten vardı); gece testi `multilingual-e5-large` ile yapıldı |
| Ollama | ❌ KURULU DEĞİL | `ollama` komutu yok — SİZİN adımınız: ollama.com'dan kurup model çekin (öneri: `qwen2.5-coder:32b` q4) |

## Sabah sizi bekleyenler
1. **Ollama kurulumu + model** (tek eksik dış bağımlılık — Phase 6'ya kadar acelesi yok)
2. Phase-0 kararlarının 6'sı da dünkü önerilerimle uyumlu ilerledi (Postgres kurulmadı — Qdrant tek başına yetti, roundtrip kanıtlı)

## Dosyalar
- `.venv/` — Python ortamı  ·  `qdrant-bin/qdrant.exe` — sunucu  ·  `data/qdrant/` — depo
- `test_parse.py`, `test_corpus.py`, `test_e2e.py` — bu rapordaki kanıtların yeniden koşturulabilir halleri
- Qdrant'ı başlat: `QDRANT__STORAGE__STORAGE_PATH=./data/qdrant ./qdrant-bin/qdrant.exe`

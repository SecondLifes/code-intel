# Yönetim Paneli — Plan (onaylı: 2026-07-23)

**Mimari:** FastAPI (Python, mevcut venv) + React/Vite/Tailwind SPA (koyu tema varsayılan, i18n: TR varsayılan / EN)
**Hibrit arama:** e5-dense + fastembed-sparse (BM42), RRF füzyon — Karar #7 KAPANDI (BGE-M3 rafta; Phase-4 ölçümü kötü çıkarsa yeniden açılır)

## API uçları (LAN'a açılabilir — Mac işçisi için)
- POST /search {q, lang, top_k, hybrid} → sonuç kartları (kod+meta)
- POST /explain {chunk_id, depth: fast|deep} → gemma4:12b | qwen3.6, cache'li
- POST /index/start {path, lib} · GET /index/status → SSE canlı ilerleme
- GET /libs · GET /health (qdrant/ollama/model durumları)
- GET/POST /eval (altın-soru seti koş, skor tablosu)
- Worker protokolü: GET /jobs/next?type=translate · POST /jobs/{id}/result  ← Mac buradan beslenir

## UI sayfaları
1. Arama (ana) — sonuç kartı: vurgulu kod, unit/satır, skor; "Türkçe Açıkla ⚡/🔬" butonları
2. Kütüphaneler — yol ekle, indeksle, chunk sayıları, son güncelleme
3. İşler — kuyruklar + canlı ilerleme çubukları
4. Değerlendirme — altın sorular, recall@k grafiği
5. Ayarlar — dil, model seçimi, LAN erişimi aç/kapa

## Mac işbölümü
PC: Qdrant + API + embedding · Mac: Ollama çeviri işçisi (LAN'dan kuyruk çeker)

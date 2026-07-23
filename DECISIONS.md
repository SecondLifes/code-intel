# Phase-0 Kararları — Durum Kaydı

| # | Karar | Durum | Not |
|---|---|---|---|
| 1 | Depo | ✅ Sadece Qdrant | Postgres kurulmadı; payload+arama roundtrip kanıtlı |
| 2 | Parser | ✅ Isopod tree-sitter-pascal (language-pack içinde) | Gramer yazımı gerekmedi; 520 dosya → 25.201 chunk |
| 3 | Çeviri modeli | 🔄 Yarışma sürüyor | Adaylar yerelde: gemma4:12b + qwen3.6. **Kısıt gevşetildi (2026-07-23, sahip kararı): bulut serbest, ücretsiz/ucuz tercih** — :cloud modeller ve ücretsiz çeviri API'leri de aday havuzunda |
| 4 | MCP araç yüzeyi | ✅ 5 araç onaylı | search_code, get_chunk, explain_tr, find_symbol, list_units |
| 5 | Embed kapsamı | ✅ Paralel vektörler | kod (şimdi) + unit-TR-özet (Phase 6) + chunk-TR (cache'lendikçe) |
| 6 | Çeviri stratejisi | ✅ Katmanlı | Unit özetleri önden; chunk çevirisi on-demand+cache. Bulut serbestisi bu stratejiyi güçlendirir (kaliteli özet için :cloud kullanılabilir) |

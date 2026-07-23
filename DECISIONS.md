# Phase-0 Kararları — Durum Kaydı

| # | Karar | Durum | Not |
|---|---|---|---|
| 1 | Depo | ✅ Sadece Qdrant | Postgres kurulmadı; payload+arama roundtrip kanıtlı |
| 2 | Parser | ✅ Isopod tree-sitter-pascal (language-pack içinde) | Gramer yazımı gerekmedi; 520 dosya → 25.201 chunk |
| 3 | Çeviri modeli | ✅ 1. tur tamam | Katmanlı: toplu iş=gemma4:12b (5.6sn/chunk), on-demand derin=qwen3.6 (26.8sn, nil-pointer tespiti yaptı). Gerekirse :cloud devleri kalite-kritik işlere eklenebilir |
| 4 | MCP araç yüzeyi | ✅ 5 araç onaylı | search_code, get_chunk, explain_tr, find_symbol, list_units |
| 5 | Embed kapsamı | ✅ Paralel vektörler | kod (şimdi) + unit-TR-özet (Phase 6) + chunk-TR (cache'lendikçe) |
| 7 | Embedding | ✅ e5-dense + fastembed-sparse hibrit (sahip onayı 2026-07-23) | BGE-M3 rafta; Phase-4 kalite ölçümü zayıf çıkarsa yeniden değerlendirilir |
| 6 | Çeviri stratejisi | ✅ Katmanlı | Unit özetleri önden; chunk çevirisi on-demand+cache. Bulut serbestisi bu stratejiyi güçlendirir (kaliteli özet için :cloud kullanılabilir) |

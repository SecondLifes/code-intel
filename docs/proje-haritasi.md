# Proje Haritası — CodeIntel

> Bu dosya, `.agents/`/`.claude/`/`.cursor/`/`.gemini/`/`.github/`/`.kiro/`/`AGENTS.md` AI-talimat katmanının **sonradan, mevcut gerçek bir uygulamanın üzerine eklendiğini** açıklar. CodeIntel, `rad-template-builder` ile baştan üretilmiş bir spec-kit değil — Delphi/Pascal (ve ~45 dil) için gerçek, çalışan bir hibrit arama + RAG + MCP sunucusu uygulamasıdır (`src/`, `tests/`, `docs/`, `static/`, `tools/`, `pyproject.toml`, `requirements.txt`, `mcp-config.json` hepsi gerçek). Bu harita sadece **eklenen AI-talimat iskeletini** kapsar — uygulamanın kendi mimarisi için `README.md`, `DECISIONS.md`, `PANEL-PLAN.md`'ye bakın.
>
> **Nasıl eklendi:** `rad-template-builder`'ın Extraction Mode'u kullanılarak (2026-08-10), gerçek koddan (pyproject.toml, requirements.txt, src/ yapısı, testler) çıkarılan konvansiyonlar önce kullanıcıyla onaylandı, sonra sadece eksik olan AI-talimat dosyaları eklendi — hiçbir gerçek uygulama dosyasına dokunulmadı/üzerine yazılmadı.

## Bu ekleme neyi kapsıyor, neyi kapsamıyor

**Kapsıyor:** `.agents/`, `.claude/`, `.cursor/`, `.gemini/`, `.github/copilot-instructions.md`, `.kiro/`, `.specify/`, `AGENTS.md`, `settings.json`, `tools/generate-ai-configs.ps1`, `tools/register.bat`, `docs/proje-haritasi.md` (bu dosya), `docs/ai-ignore-strategy.md`.

**Kapsamıyor (hiç dokunulmadı):** `README.md`/`.tr-TR`, `CONTRIBUTING.md`/`.tr-TR`, `SECURITY.md`/`.tr-TR`, `CODE_OF_CONDUCT.md`, `ACKNOWLEDGMENTS.md`/`.tr-TR`, `LICENSE`, `Prompts/`, `DECISIONS.md`, `PANEL-PLAN.md`, `src/`, `tests/`, `static/`, `tools/install.ps1` (ve diğer gerçek `tools/` script'leri), `pyproject.toml`, `requirements.txt`, `mcp-config.json`, `pytest.ini` — bunların hepsi zaten gerçek ve dolu, template-builder'ın normal akışında bunlar da kopyalanır/doldurulur ama burada atlandı.

## Mimari — tek cümlede

Kuralların, komutların ve becerilerin gerçek içeriği `.agents/` altında yaşar; `.claude/`, `.cursor/` klasörlerindeki kural dosyaları oradan **otomatik üretilir**. Nedeni ve mekanizması: [.agents/rules/sync-workflow.md](../.agents/rules/sync-workflow.md).

---

## Eklenen kök dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `AGENTS.md` | Codex CLI, Cursor, GitHub Copilot, Gemini/Antigravity ve Kiro'nun doğrudan okuduğu evrensel kural özeti — CodeIntel'in gerçek stack'i (Python/FastAPI/Qdrant/Ollama/tree-sitter), gerçek konvansiyonları (`.venv`/`uv` kullanılmaz, `onnxruntime-gpu` pin disiplini, MCP/REST paritesi, Türkçe kod yorumları) doldurulmuş hâlde. |
| `settings.json` | Bu AI-talimat katmanının kendi versiyonu (`versioning.current_version`) — uygulamanın kendi `pyproject.toml` versiyonundan (1.0.0) bağımsız, ayrı bir kavram. |

## `.agents/` — Tek Kaynak

### `.agents/rules/`

| Dosya | Konu |
|---|---|
| `sync-workflow.md` | `.agents` değişince ne yapılması gerektiği — önce bu okunur. |
| `kit-settings.md` | Kök `settings.json`'ın şeması. |
| `local-machine-registry.md` | `.rad` hub referansı — cross-kit reference, shared rules. |

Stack-özgü kurallar bu ekleme sırasında ayrı dosyalar olarak değil, doğrudan `AGENTS.md`/`.claude/CLAUDE.md`/`.gemini/rules/project-rules.md`/`.github/copilot-instructions.md` içine yazıldı (dependency-pin disiplini, MCP/REST paritesi, reindex atomicity, Türkçe yorum konvansiyonu) — CodeIntel'in kural yüzeyi henüz ayrı dosyalara bölünecek kadar büyük değil; büyüdükçe buraya `.agents/rules/qdrant-reindex.md` gibi ayrı dosyalar eklenebilir.

### `.agents/commands/`

| Dosya | Ne işe yarar |
|---|---|
| `review.md` | `/review` komutu — CodeIntel'in gerçek kontrol listesiyle (route/service ayrımı, MCP/REST paritesi, reindex atomicity) dolduruldu. |

### `.agents/skills/` — 11 klasör

| Klasör | Kaynak | Ne işe yarar |
|---|---|---|
| `python/`, `rad-prompt-studio/`, `rad-skill-finder/`, `rad-web-scraping/` | workspace `.claude/skills/` bundle | Genel Python mühendisliği, beş-mercek sistem analizi, skill/MCP keşfi, web scraping |
| `fastapi/` | `fastapi/fastapi@fastapi` (resmi, npx skills) | FastAPI routing/DI/serialization |
| `qdrant-clients-sdk/`, `qdrant-search-quality/`, `qdrant-performance-optimization/`, `qdrant-monitoring/`, `qdrant-scaling/`, `qdrant-deployment-options/` | `qdrant/skills` (resmi org, npx skills) | Qdrant client kullanımı, arama kalitesi, performans, izleme, ölçekleme, dağıtım |
| `python-mcp-server-generator/` | `github/awesome-copilot` (npx skills) | MCP sunucusu tasarımı — `src/mcp_server.py`'nin 17-tool yüzeyiyle doğrudan ilgili |

`qdrant-advisor` aranırken bulunamadı — o isimde bir skill `qdrant/skills` reposunda yok (gerçek 10 skill listesi kurulum sırasında doğrulandı); istenen 7 skill'den 6'sı gerçekten var ve kuruldu.

---

## Araç-özel adaptörler (üretilmiş/elle yazılmış)

| Klasör/Dosya | Durum | Ne işe yarar |
|---|---|---|
| `.claude/CLAUDE.md` | Elle yazılır | Claude Code'un okuduğu kök talimat — CodeIntel kimliğiyle dolduruldu. |
| `.claude/settings.json` | Elle yazılır | İzin ayarları. |
| `.claude/rules/*.md`, `.claude/commands/*.md` | ⚙️ Üretilmiş | `.agents/`'ın kopyası. |
| `.cursor/rules/*.md` | ⚙️ Üretilmiş | `.agents/rules/`'ın Cursor formatı. |
| `.gemini/rules/project-rules.md` | Elle yazılır | Gemini/Antigravity özeti — dolduruldu. |
| `.github/copilot-instructions.md` | Elle yazılır | Copilot ön-prompt — dolduruldu. |
| `.kiro/steering/*.md` (4 dosya) | Elle yazılır | Kiro steering — CodeIntel'in gerçek stack/yapı bilgisiyle dolduruldu. |
| `.specify/*.md` (4 şablon) | Elle yazılır | `constitution.md` dolduruldu; `spec-template.md`/`plan-template.md`/`tasks-template.md` özellik-bazlı doldurulacak genel şablonlar olarak kaldı (opsiyonel, ileriye dönük kullanım). |

## `tools/` (eklenen)

| Dosya | Ne işe yarar |
|---|---|
| `register.bat` | Bu projeyi `.rad` hub'a kaydeder. |
| `generate-ai-configs.ps1` | `.agents/rules`+`.agents/commands`'ı `.claude/`/`.cursor/`'a senkronlar. |

Not: CodeIntel'in kendi gerçek `tools/install.ps1` vb. script'leri bu klasörde zaten vardı ve dokunulmadı.

## `docs/` (eklenen dosyalar)

| Dosya | Ne işe yarar |
|---|---|
| `proje-haritasi.md` | Bu dosya. |
| `ai-ignore-strategy.md` | AI bağlamından hariç tutulacak dosyalar — CodeIntel'in gerçek `data/`/`logs/`/`backups/`/`snapshots/`/`qdrant-bin/` klasörleriyle dolduruldu. |

`docs/images/` (hero.png, core-features.png) ve `docs/` altındaki diğer gerçek içerik zaten vardı, dokunulmadı.

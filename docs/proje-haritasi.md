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
| `GEMINI.md` | Gemini CLI'ın giriş noktası. Gemini CLI bağlamını `GEMINI.md` hiyerarşisinden kurar — `.gemini/rules/project-rules.md`'yi kendiliğinden **okumaz**. Bu dosya içerik çoğaltmaz, `@./.gemini/rules/project-rules.md` ile onu import eder; böylece o dosya düzenlendiği tek yer olarak kalır. |
| `settings.json` | Bu AI-talimat katmanının kendi versiyonu (`versioning.current_version`) — uygulamanın kendi `pyproject.toml` versiyonundan (1.0.0) bağımsız, ayrı bir kavram. |

## `.agents/` — Tek Kaynak

### `.agents/rules/`

| Dosya | Konu |
|---|---|
| `sync-workflow.md` | `.agents` değişince ne yapılması gerektiği — önce bu okunur. |
| `kit-settings.md` | Kök `settings.json`'ın şeması. |
| `analysis-output.md` | Bundle'lanmış `rad-prompt-studio`'nun üç master prompt'unun ortak girdi-çözümleme ve çıktı-adlandırma kuralı: hedef nasıl belirlenir, rapor nereye hangi adla yazılır (`%ProgramData%\rad\analysis\{repo}\{hedef}\{ai}_v{n}.md`), ve düzeltilen bulguların raporu ne zaman silinir. Bu dosya olmadan üç prompt da çıktı yolunu çözemez. |
| `local-machine-registry.md` | `.rad` hub referansı — cross-kit reference, shared rules. |
| `testing.md` | Bu projenin gerçek test disiplini: `tests/` (harici servis gerektirmeyen varsayılan koşu) ↔ `tests/manual/` (gerçek GPU/Ollama/Qdrant isteyen, `pytest.ini` ile hariç tutulan) ayrımı, regresyon-adlandırma konvansiyonu, sözleşme testlerinin (`test_mcp_rest_parity`) neden elle tatmin edilecek bir iş değil güvence ağı olduğu. |

Kalan stack-özgü kurallar (dependency-pin disiplini, MCP/REST paritesi, reindex atomicity, Türkçe yorum konvansiyonu) doğrudan `AGENTS.md`/`.claude/CLAUDE.md`/`.gemini/rules/project-rules.md`/`.github/copilot-instructions.md` içinde duruyor — bunlar dört aracın da fiziksel olarak görmesi gereken kimlik-seviyesi kurallar. Konu başına ayrı dosyaya bölünmeyi hak eden bir kural olgunlaştıkça `testing.md` gibi buraya taşınır.

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

`qdrant-advisor` aranırken bulunamadı — o isimde bir skill `qdrant/skills` reposunda yok (gerçek 12 skill listesi kurulum sırasında doğrulandı); istenen 12 skill'den 6'sı gerçekten var ve kuruldu.

---

## Araç-özel adaptörler (üretilmiş/elle yazılmış)

| Klasör/Dosya | Durum | Ne işe yarar |
|---|---|---|
| `.claude/CLAUDE.md` | Elle yazılır | Claude Code'un okuduğu kök talimat — CodeIntel kimliğiyle dolduruldu. |
| `.claude/settings.json` | Elle yazılır | İzin ayarları. |
| `.claude/rules/*.md`, `.claude/commands/*.md` | ⚙️ Üretilmiş | `.agents/`'ın kopyası. |
| `.claude/skills/<skill-adı>` | ⚙️ **Üretilmiş link** | `.agents/skills/<skill-adı>`'a işaret eden junction (Windows) / symlink. Claude Code skill'leri **sadece** `.claude/skills/` altında keşfeder; `.agents/skills/` onun keşif konumlarından biri değil. İçerik değil, link — `.gitignore`'da, commit'lenmez, klonlandıktan sonra generator yeniden üretir. |
| `.cursor/rules/*.md` | ⚙️ Üretilmiş | `.agents/rules/`'ın Cursor formatı. |
| `.gemini/rules/project-rules.md` | Elle yazılır | Gemini/Antigravity özeti — dolduruldu. |
| `.github/copilot-instructions.md` | Elle yazılır | Copilot ön-prompt — dolduruldu. |
| `.kiro/steering/*.md` (4 dosya) | Elle yazılır | Kiro steering — CodeIntel'in gerçek stack/yapı bilgisiyle dolduruldu. |
| `.specify/*.md` (4 şablon) | Elle yazılır | `constitution.md` dolduruldu; `spec-template.md`/`plan-template.md`/`tasks-template.md` özellik-bazlı doldurulacak genel şablonlar olarak kaldı (opsiyonel, ileriye dönük kullanım). |

## `tools/` (eklenen)

| Dosya | Ne işe yarar |
|---|---|
| `register.bat` | Bu projeyi `.rad` hub'a kaydeder. |
| `verify-kit.ps1` | Mekanik tutarlılık kapısı; CI'ın çalıştırdığı script'in aynısı, yerelde de `pwsh tools/verify-kit.ps1` ile çalışır. Kontroller: generator drift, `.cursor/rules` altındaki her dosya `.mdc` mi, `.claude/skills/` her skill için giriş taşıyor mu, her `SKILL.md`'nin frontmatter'ı geçerli mi, kalan `[FILL IN` var mı, README'nin gömdüğü görseller diskte var mı, `LICENSE` duruyor mu. |
| `.github/workflows/verify.yml` | CI: her push ve PR'da kit doğrulama script'ini çalıştırır (ubuntu-latest, ön-yüklü PowerShell 7). Kontrollerin kendisi script'te, burada değil — tek uygulama, iki çağıran. |
| `generate-ai-configs.ps1` | `.agents/rules`+`.agents/commands`'ı `.claude/`/`.cursor/`'a senkronlar. |

Not: CodeIntel'in kendi gerçek `tools/install.ps1` vb. script'leri bu klasörde zaten vardı ve dokunulmadı.

## `docs/` (eklenen dosyalar)

| Dosya | Ne işe yarar |
|---|---|
| `proje-haritasi.md` | Bu dosya. |
| `ai-ignore-strategy.md` | AI bağlamından hariç tutulacak dosyalar — CodeIntel'in gerçek `data/`/`logs/`/`backups/`/`snapshots/`/`qdrant-bin/` klasörleriyle dolduruldu. |

`docs/images/` (hero.png, core-features.png) ve `docs/` altındaki diğer gerçek içerik zaten vardı, dokunulmadı.

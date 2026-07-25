"""Yardım/manual sistemi — bir koleksiyon için çapraz-bağlantılı, çok bölümlü
teknik dokümantasyon üretir (HTML görüntüleme + PDF/DOCX dışa aktarma).

Tasarım: TEK bir belge modeli (düz dict — projenin geri kalanıyla aynı
sözleşme, retrieval.py'nin her yerde dict döndürmesiyle tutarlı) inşa edilip
kalıcı JSON olarak saklanır; HTML/PDF/DOCX bu TEK modelin üç ayrı
render'ıdır — mantık üçe katlanmaz. Zaten var olan yapı taşları üstüne kurulu:
  - document_unit(): dosya başına LLM özeti (ZATEN önbellekli — build_manual
    onu tekrar tekrar çağırsa bile ilk üretimden sonra bedava)
  - build_symbol_graph()/get_type_hierarchy(): tip adı -> hangi dosyada
    tanımlı bilgisi, HTML'deki çapraz-linkleme buradan gelir
  - get_profile_payload(): başlık sayfası (owner/group/kaynak/version)

Bölümleme: unit yolunun İLK klasör segmenti (örn. "jvcl/tests/..." ->
"jvcl") — büyük koleksiyonlarda (Jedi) tek düz sayfa yerine gezilebilir
kitap yapısı. `scope` verilirse yalnız o önekle başlayan dosyalar dahil
edilir (17K+ sembollü Jedi gibi bir koleksiyonun TAMAMI yerine bir alt-ağaç
için manual üretilebilsin diye).
"""
import json
import pathlib
import re
from datetime import datetime, timezone

from qdrant_client import models

try:
    from . import retrieval
except ImportError:
    import retrieval

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANUAL_DIR = ROOT / "data" / "manuals"


def _chapter_key(unit: str) -> str:
    parts = unit.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else "Genel"


def _slug(*parts: str) -> str:
    s = "-".join(parts).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "bolum"


def _topo_order(unit_paths: list[str], deps: dict[str, set[str]]) -> dict[str, int]:
    """Kahn algoritması — TEMEL (başkalarınca kullanılan/bağımlılığı az) dosyalar
    ÖNCE gelsin diye: `deps[u]` = u'nun (aynı bölüm içinde) bağımlı olduğu
    dosyalar. Bir dosya, TÜM bağımlılıkları zaten sıralanana kadar bekler.
    Çevrimli/çözülemeyen kalanlar en sona, alfabetik eklenir. Döner:
    {unit_path: sıra_indexi} — sections listesini bununla sort etmek için."""
    remaining = set(unit_paths)
    order: list[str] = []
    while remaining:
        ready = sorted(u for u in remaining if not (deps.get(u, set()) & remaining))
        if not ready:   # çevrim — kalanları alfabetik ekleyip çık
            order.extend(sorted(remaining))
            break
        order.extend(ready)
        remaining -= set(ready)
    return {u: i for i, u in enumerate(order)}


def build_manual(collection: str, scope: str = "", force: bool = False, st: dict | None = None, lang: str = "en") -> dict:
    """Koleksiyon için manual modelini kurar ve `data/manuals/<collection>.json`
    olarak kalıcı yazar. `force=True` document_unit önbelleğini de atlayıp
    tüm dosya özetlerini yeniden ürettirir (pahalı — normalde gerekmez, çünkü
    document_unit zaten kendi başına önbellekli).

    lang="en" (Sıra 5, kullanıcı kararı — "Sadece İngilizce yapalım, manuel
    içinde istediğimiz dile çevir gibi bir yer olsun"): manuel artık BAZ olarak
    İngilizce üretilir; Türkçe (veya başka bir dil) ayrı, isteğe bağlı bir AI
    ÇEVİRİ katmanı olarak translate_manual() ile SONRADAN eklenir, model.json'da
    saklanır — özgün İngilizce içerik asla kaybolmaz, çeviri onun ÜZERİNE
    yazılmaz."""
    cl = retrieval.cl
    prof = retrieval.get_profile_payload(collection)

    # ---- kapsamdaki dosyalar (unithead chunk'ları — hafif, tam kod gerekmiyor) ----
    units: list[dict] = []
    next_page = None
    while True:
        batch, next_page = cl.scroll(collection, limit=2000, offset=next_page,
            with_payload=["unit", "lang", "name", "uses"],
            scroll_filter=models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="unithead"))]))
        for p in batch:
            u = p.payload.get("unit") or ""
            if not scope or u.replace("\\", "/").startswith(scope):
                units.append({"unit": u, "lang": p.payload.get("lang") or "pascal", "chunk_id": p.id,
                              "name": p.payload.get("name") or "", "uses": p.payload.get("uses") or []})
        if next_page is None:
            break
    units.sort(key=lambda x: x["unit"])
    if not units:
        return {"error": f"kapsamda dosya bulunamadı (scope={scope!r}) — koleksiyon unithead içermiyor olabilir (v1 chunker ile indekslenmiş olabilir, yeniden indeksleyin)"}

    # ---- Sıra: "dosya sıralaması kullanım bağımlılıklarına göre olmalı" — TEMEL
    # (başkalarınca kullanılan) dosyalar önce, onları kullananlar sonra. `uses`
    # ADLARLA (unit adı/import string'i) geliyor — yalnız BU KAPSAMDAKİ diğer
    # unit'lerle eşleşenler gerçek kenar sayılır (dış bağımlılıklar sıralamayı
    # etkilemez, zaten çözülemez). Adlar hem TAM hem SON-NOKTALI-SEGMENT ile
    # eşleştirilir (Pascal "System.SysUtils" tam eşleşir; jenerik dillerde
    # import genelde son segmentle örtüşür, ör. "./utils" -> "utils.py")."""
    name_to_path: dict[str, str] = {}
    for u in units:
        if u["name"]:
            name_to_path.setdefault(u["name"].lower(), u["unit"])
        stem = pathlib.Path(u["unit"]).stem.lower()
        name_to_path.setdefault(stem, u["unit"])
    deps: dict[str, set[str]] = {}
    for u in units:
        resolved = set()
        for used in u["uses"]:
            used_l = str(used).strip().lower()
            target = name_to_path.get(used_l) or name_to_path.get(used_l.split(".")[-1]) or name_to_path.get(used_l.split("/")[-1])
            if target and target != u["unit"]:
                resolved.add(target)
        deps[u["unit"]] = resolved
    dep_order = _topo_order([u["unit"] for u in units], deps)

    if st is not None:
        st.update(phase="building", total=len(units), done=0)

    # ---- tip adı -> ev sahibi bölüm slug'ı (HTML çapraz-linkleme için) ----
    type_home: dict[str, str] = {}   # bare-lower isim -> "chapter-slug#section-slug"
    for u in units:
        ch = _chapter_key(u["unit"])
        sec = _slug(u["unit"])
        pts, _ = cl.scroll(collection, limit=200, with_payload=["name", "kind"],
            scroll_filter=models.Filter(must=[
                models.FieldCondition(key="unit", match=models.MatchValue(value=u["unit"])),
                models.FieldCondition(key="kind", match=models.MatchValue(value="type"))]))
        for p in pts:
            nm = (p.payload.get("name") or "").split("=")[0].strip()
            if nm:
                type_home[nm.lower()] = f"{_slug(ch)}.html#{sec}"

    # ---- bölüm içeriği: document_unit'in ÖNBELLEKLİ özeti ----
    chapters: dict[str, dict] = {}
    lang_counts: dict[str, int] = {}
    for i, u in enumerate(units):
        if st is not None:
            st.update(done=i, current=u["unit"])
        lang_counts[u["lang"]] = lang_counts.get(u["lang"], 0) + 1
        doc = retrieval.document_unit(collection, u["unit"], force=force, lang=lang)
        if "error" in doc:
            continue
        ch_key = _chapter_key(u["unit"])
        chapters.setdefault(ch_key, {"title": ch_key, "slug": _slug(ch_key), "sections": []})
        chapters[ch_key]["sections"].append({
            "title": pathlib.Path(u["unit"]).name, "slug": _slug(u["unit"]),
            "unit": u["unit"], "lang": u["lang"], "body_md": doc["md"], "chunk_id": u["chunk_id"],
        })
    for ch in chapters.values():
        ch["sections"].sort(key=lambda s: dep_order.get(s["unit"], len(dep_order)))

    title = f"{collection} — Kullanım Kılavuzu" if lang == "tr" else f"{collection} — User Guide"
    model = {
        "collection": collection, "scope": scope, "lang": lang, "translations": {},
        "title": title,
        "owner": prof.get("owner", ""), "group": prof.get("group", ""),
        "version": prof.get("version", ""), "kaynak": prof.get("kaynak", ""), "url": prof.get("url", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {"units": len(units), "chapters": len(chapters), "languages": lang_counts},
        "chapters": sorted(chapters.values(), key=lambda c: c["title"].lower()),
        "type_home": type_home,
    }
    _save_manual(collection, model)
    if st is not None:
        st.update(done=len(units))
    return model


def load_manual(collection: str) -> dict | None:
    f = MANUAL_DIR / f"{collection}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def _save_manual(collection: str, model: dict):
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    (MANUAL_DIR / f"{collection}.json").write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")


LANG_LABELS = {"en": "English", "tr": "Türkçe"}   # bilinen birkaçı için düzgün ad — bilinmeyen kod .title() ile düşer


def model_for_lang(model: dict, lang: str) -> dict:
    """`model`in section body_md'lerini `lang` çevirisiyle DEĞİŞTİRİLMİŞ bir
    KOPYASINI döner (özgün model asla mutasyona uğramaz). lang boşsa veya baz
    dilse model AYNEN döner. HTML/DOCX/PDF render'larının HEPSİ bunu kullanır
    — çeviri mantığı üç render'da AYRI AYRI tekrarlanmaz, tek yerde."""
    base_lang = model.get("lang", "en")
    if not lang or lang == base_lang:
        return model
    translation = (model.get("translations") or {}).get(lang)
    if not translation:
        return model
    trans_secs = translation.get("sections") or {}
    out = dict(model)
    out["title"] = model["title"]   # başlık çevrilmiyor (kısa, koleksiyon adı içeriyor) — bilinçli
    new_chapters = []
    for ch in model["chapters"]:
        new_ch = dict(ch)
        new_ch["sections"] = [
            {**sec, "body_md": trans_secs.get(f'{ch["slug"]}|{sec["slug"]}', sec["body_md"])}
            for sec in ch["sections"]]
        new_chapters.append(new_ch)
    out["chapters"] = new_chapters
    return out


def list_manual_languages(collection: str) -> list[dict]:
    """Bu manuel için mevcut diller: baz (üretildiği dil) + eklenmiş çeviriler.
    UI'daki dil seçici bunu kullanır — "her eklenen dil orada görünsün" (Sıra 5)."""
    m = load_manual(collection)
    if m is None:
        return []
    base = m.get("lang", "en")
    out = [{"code": base, "label": LANG_LABELS.get(base, base.title()), "base": True}]
    for code, t in (m.get("translations") or {}).items():
        out.append({"code": code, "label": t.get("label") or LANG_LABELS.get(code, code.title()), "base": False})
    return out


def translate_manual(collection: str, target_lang: str, target_label: str = "", model: str = "",
                      force: bool = False, st: dict | None = None) -> dict:
    """Sıra 5 (kullanıcı): var olan (baz dilde, varsayılan İngilizce) manuel
    modelini AI ile hedef dile çevirir; sonucu model.json'un `translations`
    alanında KALICI saklar. Yapı (bölüm/section sırası, slug, chunk_id) AYNEN
    korunur — yalnız gövde metni (body_md) çevrilir. section BAŞINA önbelleklidir
    (force=False iken zaten çevrilmiş bir bölüm atlanır — force=True hepsini
    yeniden çevirir). Özgün baz-dil içeriği ASLA üzerine yazılmaz, translations
    ayrı bir alanda tutulur."""
    doc_model = load_manual(collection)
    if doc_model is None:
        return {"error": f"'{collection}' için manuel henüz üretilmemiş"}
    target_lang = (target_lang or "").strip().lower()
    if not target_lang:
        return {"error": "hedef dil boş olamaz"}
    base_lang = doc_model.get("lang", "en")
    if target_lang == base_lang:
        return {"error": f"manuel zaten '{target_lang}' dilinde üretilmiş — çeviriye gerek yok"}
    mdl = model or retrieval._CFG.get("deep_model", "qwen3.6")
    translations = doc_model.setdefault("translations", {})
    existing = {} if force else dict((translations.get(target_lang) or {}).get("sections") or {})
    total = sum(len(ch["sections"]) for ch in doc_model["chapters"])
    if st is not None:
        st.update(phase="translating", total=total, done=0)
    label = target_label.strip() if target_label and target_label.strip() else LANG_LABELS.get(target_lang, target_lang.title())
    done = 0
    for ch in doc_model["chapters"]:
        for sec in ch["sections"]:
            key = f'{ch["slug"]}|{sec["slug"]}'
            if st is not None:
                st.update(done=done, current=sec["unit"])
            done += 1
            if key in existing:
                continue
            prompt = (f"Translate the following technical documentation from English to {label}. "
                      "Preserve the EXACT Markdown structure (headings, bullet lists, code blocks) — do NOT "
                      "translate content inside code blocks (```...```) or inline code (`...`), and do NOT "
                      "translate identifier/type/function names. Output ONLY the translated Markdown text, "
                      "no extra commentary before or after.\n\n" + sec["body_md"])
            existing[key] = retrieval.ollama_generate(mdl, prompt, num_predict=1400)
    translations[target_lang] = {"label": label, "model": mdl,
                                  "generated_at": datetime.now(timezone.utc).isoformat(), "sections": existing}
    _save_manual(collection, doc_model)
    if st is not None:
        st.update(done=total)
    return {"ok": True, "lang": target_lang, "label": label, "sections": len(existing)}


# ---------------- HTML render (tek paylaşılan CSS, "hepsi aynı türden") ----------------
_LINK_SKIP_RE = re.compile(r"```.*?```|`[^`]*`", re.S)   # kod bloklarına/satır-içi koda dokunma

def _cross_link(body_md: str, type_home: dict[str, str], self_href: str) -> str:
    """Bilinen tip adlarını [Ad](hedef) markdown linkine çevirir — kod
    bloklarını ve satır-içi kodu atlar, kendi sayfasına link vermez."""
    if not type_home:
        return body_md
    names = sorted(type_home, key=len, reverse=True)   # uzun adlar önce (alt-string çakışmasını önler)
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)

    def repl_outside_code(segment: str) -> str:
        def repl(m):
            href = type_home.get(m.group(1).lower())
            if not href or href == self_href:
                return m.group(1)
            return f"[{m.group(1)}]({href})"
        return pattern.sub(repl, segment)

    out, last = [], 0
    for m in _LINK_SKIP_RE.finditer(body_md):
        out.append(repl_outside_code(body_md[last:m.start()]))
        out.append(m.group(0))   # kod bloğu/satır-içi kod OLDUĞU GİBİ
        last = m.end()
    out.append(repl_outside_code(body_md[last:]))
    return "".join(out)


def _md_to_html_fragment(md: str) -> str:
    """viewer.html'deki mdToHtml'in Python karşılığı — aynı minimal alt küme
    (başlık/kalın/italik/kod/link/liste), tam CommonMark değil, bilinçli."""
    def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    blocks = []
    code_blocks = []
    def stash_code(m):
        code_blocks.append(m.group(1))
        return f"\x00CODE{len(code_blocks) - 1}\x00"
    md = re.sub(r"```\w*\n?(.*?)```", stash_code, md, flags=re.S)

    def inline(t):
        t = re.sub(r"`([^`]+)`", lambda m: f"<code>{esc(m.group(1))}</code>", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
        return t

    html, in_list = [], False
    for line in md.split("\n"):
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            if in_list: html.append("</ul>"); in_list = False
            lvl = len(m.group(1))
            html.append(f"<h{lvl}>{inline(esc(m.group(2)))}</h{lvl}>")
            continue
        m = re.match(r"^[-*]\s+(.*)", line)
        if m:
            if not in_list: html.append("<ul>"); in_list = True
            html.append(f"<li>{inline(esc(m.group(1)))}</li>")
            continue
        if in_list: html.append("</ul>"); in_list = False
        if line.strip():
            html.append(f"<p>{inline(esc(line))}</p>")
    if in_list: html.append("</ul>")
    out = "\n".join(html)
    for i, code in enumerate(code_blocks):
        out = out.replace(f"\x00CODE{i}\x00", f"<pre><code>{esc(code)}</code></pre>")
    return out


MANUAL_CSS = """
:root{
  --bg:#14110c;--panel:#1b1710;--card:#211c14;--code:#0f0d09;
  --line:#332b1f;--line2:#463b2a;--txt:#f1ebdd;--dim:#a99a83;--faint:#6f6555;
  --amber:#e0a24a;--amber-d:#c58a37;--teal:#49b39c;--teal-d:#2f7e6c;--err:#e0704a;
  --serif:Georgia,'Iowan Old Style','Palatino Linotype',serif;
  --mono:'Cascadia Code','JetBrains Mono',Consolas,monospace;
}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--txt);font:15px/1.7 'Segoe UI',system-ui,sans-serif;display:flex;min-height:100vh}
nav{width:300px;flex:none;background:var(--panel);border-right:1px solid var(--line);padding:22px 18px;overflow-y:auto;overflow-x:hidden;position:sticky;top:0;height:100vh}
nav h1{font-family:var(--serif);font-size:18px;color:var(--amber);margin-bottom:4px;line-height:1.3}
nav h1 a{color:inherit;text-decoration:none}
nav h1 a:hover{color:var(--teal)}
nav .home{display:inline-block;font-size:11.5px;color:var(--faint);text-decoration:none;margin-bottom:10px}
nav .home:hover{color:var(--amber)}
nav .meta{font-size:11.5px;color:var(--faint);margin-bottom:16px;font-family:var(--mono)}
nav input{width:100%;background:var(--card);border:1px solid var(--line2);border-radius:8px;color:var(--txt);padding:8px 10px;font-size:13px;margin-bottom:14px}
nav .chapter{margin-bottom:4px}
nav .chapter>a{display:block;font-size:12.5px;letter-spacing:.2px;color:var(--dim);padding:6px 4px;text-decoration:none;font-weight:700;overflow-wrap:anywhere}
nav .chapter a.sec{display:block;font-size:13px;color:var(--txt);padding:4px 4px 4px 14px;text-decoration:none;border-left:2px solid transparent;overflow-wrap:anywhere;line-height:1.35}
nav .chapter a.sec:hover{color:var(--amber);border-left-color:var(--amber-d)}
nav a.active{color:var(--amber)!important;border-left-color:var(--amber)!important}
main{flex:1;max-width:840px;margin:0 auto;padding:48px 40px 100px}
main h1,main h2,main h3{font-family:var(--serif);color:var(--amber);text-wrap:balance;margin:28px 0 12px;line-height:1.3}
main h1{font-size:30px;border-bottom:1px solid var(--line);padding-bottom:14px}
main h2{font-size:21px}
main h3{font-size:16px;color:var(--teal)}
main p{margin:0 0 14px;max-width:70ch}
main ul{margin:0 0 14px 22px}
main li{margin-bottom:4px}
main a{color:var(--teal)}
main code{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:1px 6px;font-family:var(--mono);font-size:13px}
main pre{background:var(--code);border:1px solid var(--line);border-radius:10px;padding:14px 16px;overflow-x:auto;margin:0 0 16px;font:12.5px/1.6 var(--mono)}
main pre code{background:none;border:0;padding:0}
.section{padding-top:8px;border-top:1px solid var(--line);margin-top:32px}
.section:first-of-type{border-top:0;margin-top:0}
.badge{display:inline-block;font-size:10.5px;color:var(--teal);background:rgba(73,179,156,.1);padding:2px 8px;border-radius:6px;font-family:var(--mono);margin-left:8px;vertical-align:middle}
.overview-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:20px 0 28px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.stat b{display:block;font-size:22px;color:var(--amber);font-family:var(--serif)}
.stat span{font-size:11.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.5px}
.sec-actions{display:inline-flex;flex-wrap:wrap;gap:6px;margin-left:10px;vertical-align:middle}
.sec-actions button{font-size:11px;padding:3px 9px;background:var(--card);border:1px solid var(--line2);color:var(--dim);border-radius:6px;cursor:pointer;font-family:inherit}
.sec-actions button:hover{border-color:var(--amber-d);color:var(--amber)}
.sec-actions button:disabled{opacity:.5;cursor:wait}
.sec-code{display:none;margin-top:10px}
.sec-code.show{display:block}
.sec-code pre{max-height:480px;overflow:auto}
.langsw{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.langsw a{font-size:11.5px;padding:3px 9px;border-radius:99px;border:1px solid var(--line2);color:var(--dim);text-decoration:none}
.langsw a:hover{border-color:var(--amber-d);color:var(--amber)}
.langsw a.cur{background:var(--amber);border-color:var(--amber);color:#1a1305!important;font-weight:700}
.langsw a.addlang{color:var(--teal);border-style:dashed}
.langsw a.addlang:hover{border-color:var(--teal-d);color:var(--teal-d)}
.swal2-popup.ci-swal{background:var(--panel);color:var(--txt);border:1px solid var(--line2);border-radius:14px;font:15px/1.6 'Segoe UI',system-ui,sans-serif}
.ci-swal .swal2-title{color:var(--txt);font-size:18px}
.ci-swal .swal2-html-container{color:var(--dim)}
.ci-swal .swal2-input{background:var(--card);border:1px solid var(--line2);color:var(--txt);box-shadow:none;font-size:14px}
.ci-swal .swal2-input:focus{border-color:var(--amber-d);box-shadow:0 0 0 3px rgba(224,162,74,.08)}
.ci-swal-btn{background:var(--amber)!important;color:#1a1305!important;border:0!important;box-shadow:none!important;font-weight:700!important;border-radius:10px!important}
.ci-swal-btn:hover{background:var(--amber-d)!important}
.ci-swal-btn-cancel{background:var(--card)!important;color:var(--dim)!important;border:1px solid var(--line2)!important;box-shadow:none!important;border-radius:10px!important}
.ci-swal-toast{background:var(--panel)!important;color:var(--txt)!important;border:1px solid var(--line2);box-shadow:0 8px 24px rgba(0,0,0,.35)}
.ci-swal-toast .swal2-title{font-size:14px;color:var(--txt)}
"""


def render_manual_html(model: dict, page: str = "index", lang: str = "") -> str:
    """page: "index" (kapak+TOC) veya bir chapter slug'ı. lang: boşsa BAZ dil
    (model["lang"]); doluysa model["translations"][lang] varsa o dilin
    body_md'si kullanılır (bir bölüm henüz çevrilmemişse baz dile SESSİZCE düşer
    — hiç eksik/boş görünmez). Sıra 5 (kullanıcı): "manuel içinde istediğimiz
    dile çevir gibi bir yer olsun" — nav'daki dil seçici bunu sağlar.

    KRİTİK düzeltme: tüm href'ler MUTLAK yol (`/manual/{collection}/...`) olmalı.
    Eskiden `"{slug}.html"` gibi GÖRECELİ üretiliyordu — bu yalnız sayfa URL'si
    SONUNDA `/` varken doğru çözülür; ama gerçek sayfa `/manual/{collection}`
    (eğik çizgisiz) adresinde sunuluyor, bu yüzden tarayıcı `src.html`'i
    `/manual/src.html` diye çözüyordu (son segment "RESTRequest4Delphi"
    DEĞİŞTİRİLİYOR, ALTINA eklenmiyor) — canlı doğrulamada yakalanan gerçek
    hata: HER link "Manual henüz üretilmemiş" gösteriyordu. Var olan
    manual.json dosyaları (type_home içinde hâlâ göreli yol saklıyor)
    YENİDEN ÜRETİLMEDEN çalışsın diye düzeltme RENDER anında yapılıyor."""
    base_lang = model.get("lang", "en")
    active_lang = lang or base_lang
    qs = f"?lang={active_lang}" if active_lang != base_lang else ""
    display_model = model_for_lang(model, active_lang)   # body_md'ler çeviriyle değiştirilmiş kopya (varsa)

    base = f"/manual/{model['collection']}/"
    index_url = f"/manual/{model['collection']}{qs}"
    # list_manual_languages(collection) DİSKTEN okur — burada BİLEREK kullanılmıyor:
    # bu fonksiyon her zaman `model` PARAMETRESİYLE tutarlı olmalı (model_for_lang de
    # aynı sözleşmeyi izliyor), aksi halde diskteki hal ile bellekteki `model` farklıysa
    # (ör. henüz kaydedilmemiş bir model, testler) dil rozeti YANLIŞ/eksik listelenirdi.
    langs_avail = [{"code": base_lang, "label": LANG_LABELS.get(base_lang, base_lang.title()), "base": True}] + [
        {"code": code, "label": t.get("label") or LANG_LABELS.get(code, code.title()), "base": False}
        for code, t in (model.get("translations") or {}).items()]
    # class="cur" (NOT "active"): "active" çakışıyordu — nav a.active{color:var(--amber)
    # !important} kuralı (chapter/section vurgusu için) genel "nav a.active" seçicisiyle
    # dil rozetini de eşliyordu, !important yüzünden .langsw a.active'i eziyor, amber
    # ÜSTÜNE amber (görünmez metin) çıkıyordu — canlı doğrulamada yakalanan gerçek hata.
    lang_switcher = '<div class="langsw">' + "".join(
        f'<a href="{"/manual/" + model["collection"] + ("/" + page + ".html" if page != "index" else "")}'
        f'{"?lang=" + l["code"] if l["code"] != base_lang else ""}" '
        f'class="{"cur" if l["code"] == active_lang else ""}">{_esc(l["label"])}</a>'
        for l in langs_avail) + (
        '<a href="#" class="addlang" onclick="manualAddLang(event)" title="Yapay zeka ile yeni bir dile çevir">+ Dil ekle</a>'
    ) + '</div><div id="langjob" class="note" style="display:none"></div>'
    nav_html = ([f'<a class="home" href="{index_url}">← İndeks / Kapak</a>'] if page != "index" else []) + [
                f'<h1><a href="{index_url}">{_esc(model["title"])}</a></h1>',
                f'<div class="meta">{_esc(model.get("version",""))} '
                f'{"· " + _esc(model["owner"]) if model.get("owner") else ""}</div>',
                lang_switcher,
                '<input placeholder="Ara…" onkeyup="filterNav(this.value)" id="navsearch">']
    for ch in model["chapters"]:
        active_ch = " active" if page == ch["slug"] else ""
        nav_html.append(f'<div class="chapter"><a href="{base}{ch["slug"]}.html{qs}" class="{active_ch}">{_esc(ch["title"])}</a>')
        for sec in ch["sections"]:
            nav_html.append(f'<a class="sec" href="{base}{ch["slug"]}.html{qs}#{sec["slug"]}">{_esc(sec["title"])}</a>')
        nav_html.append("</div>")
    nav = "\n".join(nav_html)

    if page == "index":
        pl = ", ".join(f"{k} ({v})" for k, v in sorted(model["stats"]["languages"].items(), key=lambda kv: -kv[1]))
        body = f"""<h1>{_esc(model["title"])}</h1>
<p>{_esc(model.get("group","") or "")}</p>
<div class="overview-grid">
  <div class="stat"><b>{model["stats"]["units"]}</b><span>Dosya</span></div>
  <div class="stat"><b>{model["stats"]["chapters"]}</b><span>Bölüm</span></div>
</div>
<p><b>Diller:</b> {_esc(pl)}</p>
{"<p><b>Kaynak:</b> " + _esc(model.get("kaynak","")) + (" — <a href=\"" + _esc(model.get("url","")) + "\">" + _esc(model.get("url","")) + "</a>" if model.get("url") else "") + "</p>" if model.get("kaynak") else ""}
<h2>İçindekiler</h2>
<ul>{"".join(f'<li><a href="{base}{c["slug"]}.html{qs}">{_esc(c["title"])}</a> ({len(c["sections"])})</li>' for c in model["chapters"])}</ul>"""
    else:
        ch = next((c for c in display_model["chapters"] if c["slug"] == page), None)
        if ch is None:
            return "<h1>404</h1>"
        type_home_abs = {k: base + v + qs for k, v in model.get("type_home", {}).items()}
        parts = [f'<h1>{_esc(ch["title"])}</h1>']
        for sec in ch["sections"]:
            linked = _cross_link(sec["body_md"], type_home_abs, f'{base}{ch["slug"]}.html{qs}#{sec["slug"]}')
            # "Aç" (kayıtlı varsayılan uygulamada) + "Tarayıcıda Göster" (sayfa içi
            # aç-kapa, gerçek kaynak) — YALNIZ chunk_id varsa (eski manual.json'lar
            # bu alanı henüz taşımıyor olabilir, yeniden üretilmeden de çökmesin).
            actions = ""
            if sec.get("chunk_id") is not None:
                cid = sec["chunk_id"]
                coll_esc = _esc(model["collection"])
                actions = (f'<span class="sec-actions">'
                          f'<button type="button" onclick="manualOpen(\'{coll_esc}\',{cid},this)" title="Kayıtlı varsayılan uygulamada aç">📂 Aç</button>'
                          f'<button type="button" onclick="manualOpenFolder(\'{coll_esc}\',{cid},this)" title="Dosya gezgininde, seçili olarak göster">🗂️ Klasörde Aç</button>'
                          f'<button type="button" onclick="manualShowInBrowser(\'{coll_esc}\',{cid},\'{sec["slug"]}\',this)">🖥️ Tarayıcıda Göster</button>'
                          f'</span>')
            parts.append(f'<div class="section" id="{sec["slug"]}"><h2>{_esc(sec["title"])}'
                         f'<span class="badge">{_esc(sec["lang"])}</span>{actions}</h2>'
                         f'{_md_to_html_fragment(linked)}<div class="sec-code" id="code-{sec["slug"]}"></div></div>')
        body = "\n".join(parts)

    html_lang = active_lang if active_lang in ("tr", "en") else "en"
    return f"""<!doctype html><html lang="{html_lang}"><head><meta charset="utf-8">
<title>{_esc(model["title"])}</title><style>{MANUAL_CSS}</style>
<script src="/static/vendor/sweetalert2.min.js"></script></head>
<body><nav>{nav}</nav><main>{body}</main>
<script>
var MANUAL_COLLECTION={json.dumps(model["collection"])}, MANUAL_PAGE={json.dumps(page)};
var SWAL_BASE={{background:undefined,customClass:{{popup:'ci-swal',confirmButton:'ci-swal-btn',cancelButton:'ci-swal-btn-cancel'}},buttonsStyling:false}};
function ciError(msg){{return Swal.fire(Object.assign({{}},SWAL_BASE,{{icon:'error',html:String(msg&&msg.message||msg),confirmButtonText:'Tamam'}}));}}
function ciPrompt(title,defaultValue){{
  return Swal.fire(Object.assign({{}},SWAL_BASE,{{icon:'question',title:title,input:'text',inputValue:defaultValue||'',
    showCancelButton:true,confirmButtonText:'Tamam',cancelButtonText:'Vazgeç'}})).then(function(r){{return r.isConfirmed?r.value:null;}});
}}
function ciToast(msg,icon){{
  return Swal.mixin({{toast:true,position:'top-end',showConfirmButton:false,timer:3200,timerProgressBar:true,
    customClass:{{popup:'ci-swal-toast'}},didOpen:function(t){{t.addEventListener('mouseenter',Swal.stopTimer);t.addEventListener('mouseleave',Swal.resumeTimer);}}
  }}).fire({{icon:icon||'success',title:msg}});
}}
function filterNav(q){{q=q.toLowerCase();document.querySelectorAll('nav .chapter').forEach(function(ch){{
  var any=false;ch.querySelectorAll('a.sec').forEach(function(a){{var m=a.textContent.toLowerCase().includes(q);a.style.display=m?'':'none';if(m)any=true;}});
  ch.style.display=(!q||any)?'':'none';}});}}
async function manualAddLang(ev){{
  ev.preventDefault();
  var name=await ciPrompt('Hangi dile çevrilsin? (ör. Türkçe, Deutsch, Français)');
  if(!name||!name.trim())return;
  var code=name.trim().toLowerCase().replace(/[^a-z0-9]+/g,'-');
  var box=document.getElementById('langjob');
  box.style.display='block';box.textContent='Çeviri başlatılıyor…';
  try{{
    var r=await(await fetch('/api/manual/translate',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{collection:MANUAL_COLLECTION,lang:code,label:name.trim()}})}})).json();
    if(r.error){{box.textContent='❌ '+r.error;ciError(r.error);return;}}
    var t=setInterval(async function(){{
      var s=await(await fetch('/api/manual/translate-status')).json();
      if(!s.phase||s.phase==='idle')return;
      if(s.phase==='translating')box.textContent='Çevriliyor… '+(s.done||0)+'/'+(s.total||0);
      else if(s.phase==='done'){{clearInterval(t);box.textContent='✅ Hazır, yenileniyor…';ciToast('Çeviri hazır');
        location.href='/manual/'+MANUAL_COLLECTION+(MANUAL_PAGE!=='index'?'/'+MANUAL_PAGE+'.html':'')+'?lang='+code;}}
      else if(s.phase==='error'){{clearInterval(t);box.textContent='❌ '+(s.error||'');ciError(s.error||'Çeviri hatası');}}
    }},2000);
  }}catch(e){{box.textContent='❌ '+e;ciError(e);}}
}}
async function manualOpen(collection,id,btn){{
  var old=btn.textContent;btn.disabled=true;btn.textContent='…';
  try{{
    var r=await(await fetch('/api/reveal',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{collection:collection,id:id,mode:'file'}})}})).json();
    if(r.error)ciError(r.error);
  }}catch(e){{ciError(e);}}
  btn.disabled=false;btn.textContent=old;
}}
async function manualOpenFolder(collection,id,btn){{
  var old=btn.textContent;btn.disabled=true;btn.textContent='…';
  try{{
    var r=await(await fetch('/api/reveal',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{collection:collection,id:id,mode:'folder'}})}})).json();
    if(r.error)ciError(r.error);
  }}catch(e){{ciError(e);}}
  btn.disabled=false;btn.textContent=old;
}}
async function manualShowInBrowser(collection,id,secSlug,btn){{
  var box=document.getElementById('code-'+secSlug);
  if(box.classList.contains('show')){{box.classList.remove('show');return;}}
  if(!box.dataset.loaded){{
    btn.disabled=true;var oldTxt=btn.textContent;btn.textContent='⏳ Yükleniyor…';
    try{{
      var r=await(await fetch('/api/reveal',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{collection:collection,id:id,mode:'browser'}})}})).json();
      var esc=function(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}};
      box.innerHTML=r.error?('<p style="color:var(--err)">'+esc(r.error)+'</p>'):('<pre><code>'+esc(r.content)+'</code></pre>');
      box.dataset.loaded='1';
    }}catch(e){{box.innerHTML='<p style="color:var(--err)">'+e+'</p>';}}
    btn.disabled=false;btn.textContent=oldTxt;
  }}
  box.classList.add('show');
  box.scrollIntoView({{block:'nearest',behavior:'smooth'}});
}}
</script></body></html>"""


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------- DOCX / PDF (aynı model, farklı render — HTML'in aksine
# çapraz-link YOK; sade akış metni, kod blokları anlaşılır biçimde ayrılmış) ----------------
def _plain_blocks(body_md: str) -> list[tuple[str, str]]:
    """(tür, metin) çiftleri: tür = "h2"|"h3"|"p"|"li"|"code". Basit satır bazlı
    ayrıştırma — hem DOCX hem PDF render'ı bunu ortak kullanır."""
    out = []
    in_code = False
    code_buf = []
    for line in body_md.split("\n"):
        if line.strip().startswith("```"):
            if in_code:
                out.append(("code", "\n".join(code_buf))); code_buf = []
            in_code = not in_code
            continue
        if in_code:
            code_buf.append(line); continue
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            out.append((f"h{len(m.group(1))}", m.group(2).strip())); continue
        m = re.match(r"^[-*]\s+(.*)", line)
        if m:
            out.append(("li", m.group(1).strip())); continue
        if line.strip():
            out.append(("p", re.sub(r"[*`]", "", line.strip())))
    return out


def render_manual_docx(model: dict) -> bytes:
    """python-docx ile — bkz. skill notları: sayfa/tablo/liste tuzakları
    burada yok (yalnız başlık+paragraf+kod-paragrafı kullanılıyor, düz akış)."""
    import io
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    doc.add_heading(model["title"], level=0)
    meta = f'{model.get("version","")}  {model.get("owner","")}  {model.get("group","")}'.strip()
    if meta:
        p = doc.add_paragraph(meta); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f'{model["stats"]["units"]} dosya · {model["stats"]["chapters"]} bölüm — '
                      f'{datetime.now(timezone.utc).strftime("%Y-%m-%d")}')

    for ch in model["chapters"]:
        doc.add_heading(ch["title"], level=1)
        for sec in ch["sections"]:
            doc.add_heading(f'{sec["title"]}  [{sec["lang"]}]', level=2)
            for kind, text in _plain_blocks(sec["body_md"]):
                if kind in ("h2", "h3"):
                    doc.add_heading(text, level=3)
                elif kind == "li":
                    doc.add_paragraph(text, style="List Bullet")
                elif kind == "code":
                    p = doc.add_paragraph()
                    r = p.add_run(text); r.font.name = "Consolas"; r.font.size = Pt(9)
                    p.paragraph_format.left_indent = Pt(18)
                else:
                    doc.add_paragraph(text)
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()


# reportlab'ın yerleşik Helvetica/Times fontları Latin-1/WinAnsi ile sınırlı —
# Türkçe'ye özgü ı/ş/ğ glifleri YOK (canlı testte "Kullanım" -> "Kullan■m" olarak
# bozulduğu doğrulandı). Windows'ta zaten kurulu gerçek Unicode TTF'ler
# (Georgia/Calibri/Consolas — HTML tasarımıyla aynı aile) kaydedilip kullanılır.
_FONTS_REGISTERED = False
_FONT_DIR = pathlib.Path(r"C:\Windows\Fonts")
_FONT_FILES = {"Georgia": "georgia.ttf", "Georgia-Bold": "georgiab.ttf",
               "Calibri": "calibri.ttf", "Calibri-Bold": "calibrib.ttf",
               "Consolas": "consola.ttf"}

def _ensure_pdf_fonts():
    """Idempotent — Windows dışı bir ortamda TTF bulunamazsa yerleşik fontlara
    sessizce düşülür (Türkçe glif eksik kalır ama üretim çökmez)."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return True
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        for name, fname in _FONT_FILES.items():
            pdfmetrics.registerFont(TTFont(name, str(_FONT_DIR / fname)))
        _FONTS_REGISTERED = True
    except Exception:
        pass
    return _FONTS_REGISTERED


def render_manual_pdf(model: dict) -> bytes:
    """reportlab Platypus ile — pypdf/weasyprint/playwright DEĞİL: saf Python,
    yeni sistem bağımlılığı yok (Windows'ta Cairo/Pango riski, Chromium indirmesi
    yok) — pdf skill'inin önerdiği CREATE yolu."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, ListFlowable, ListItem

    have_unicode_fonts = _ensure_pdf_fonts()
    f_head = "Georgia" if have_unicode_fonts else "Helvetica-Bold"
    f_body = "Calibri" if have_unicode_fonts else "Helvetica"
    f_code = "Consolas" if have_unicode_fonts else "Courier"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2.2 * cm, bottomMargin=2 * cm,
                            leftMargin=2.2 * cm, rightMargin=2.2 * cm)
    styles = getSampleStyleSheet()
    amber, teal, dim = colors.HexColor("#c58a37"), colors.HexColor("#2f7e6c"), colors.HexColor("#6f6555")
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName=f_head, textColor=amber, spaceAfter=10)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName=f_head, textColor=amber, spaceBefore=14, spaceAfter=6)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontName=f_head, textColor=teal, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontName=f_body, fontSize=10, leading=14, spaceAfter=6)
    codep = ParagraphStyle("Code", parent=styles["Code"], fontName=f_code, fontSize=8, leading=11,
                           backColor=colors.HexColor("#f2f0ea"), leftIndent=10, spaceAfter=8)
    metap = ParagraphStyle("Meta", parent=styles["Normal"], fontName=f_body, fontSize=9, textColor=dim, spaceAfter=16)

    def esc(s): return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = [Paragraph(esc(model["title"]), h1)]
    meta = " · ".join(x for x in (model.get("version"), model.get("owner"), model.get("group")) if x)
    if meta:
        story.append(Paragraph(esc(meta), metap))
    story.append(Paragraph(f'{model["stats"]["units"]} dosya · {model["stats"]["chapters"]} bölüm', metap))
    story.append(PageBreak())

    for ch in model["chapters"]:
        story.append(Paragraph(esc(ch["title"]), h1))
        for sec in ch["sections"]:
            story.append(Paragraph(f'{esc(sec["title"])} <font color="#{teal.hexval()[2:]}" size="8">[{esc(sec["lang"])}]</font>', h2))
            items = []
            for kind, text in _plain_blocks(sec["body_md"]):
                if kind in ("h2", "h3"):
                    story.append(Paragraph(esc(text), h3))
                elif kind == "li":
                    items.append(ListItem(Paragraph(esc(text), body)))
                elif kind == "code":
                    story.append(Paragraph(esc(text).replace("\n", "<br/>"), codep))
                else:
                    if items:
                        story.append(ListFlowable(items, bulletType="bullet")); items = []
                    story.append(Paragraph(esc(text), body))
            if items:
                story.append(ListFlowable(items, bulletType="bullet"))
        story.append(PageBreak())
    doc.build(story)
    return buf.getvalue()

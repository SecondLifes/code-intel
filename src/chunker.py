"""Phase 1 chunker v1 — Pascal kaynaklarını anlamsal chunk'lara ayırır.
Çıktı: JSONL (chunk başına: id, lib, unit, kind, name, satır aralığı, kod, doc, hash).
Hash: XXH3-64 (xxhash paketi, SSE2/AVX2 hızlandırmalı) — kriptografik olmayan,
sadece içerik değişikliği tespiti (diffleme) için kullanılıyor, sha1'den ~5x hızlı.

declProc (interface bölümündeki method BİLDİRİMLERİ) de defProc (implementation
bölümündeki method GÖVDELERİ) yanında ayrıca indeksleniyor — çünkü /// XML doc
yorumları (<summary>...</summary>) sadece bildirimlerin üzerinde bulunuyor,
gövdelerde değil. Tree-sitter bu yorumu düğümün kendi byte aralığına dahil
etmiyor (ayrı bir kardeş düğüm) — bu yüzden her declProc/defProc için bir
önceki kardeşin "comment" olup olmadığına bakılıp elle ekleniyor."""
import json, pathlib, re, sys, time
import xxhash
from tree_sitter import Query, QueryCursor
from tree_sitter_language_pack import get_language, get_parser

LANG = get_language("pascal"); PARSER = get_parser("pascal")
Q = Query(LANG, "(declProc) @decl\n(defProc) @impl\n(declType) @type")
NAME_RE = re.compile(r"(?:procedure|function|constructor|destructor)\s+([\w.]+)", re.I)
SUMMARY_TAG_RE = re.compile(r"</?summary>", re.I)

CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
# Pascal/Delphi ayrılmış sözcükleri — bunlar "(" ile takip edilse bile ÇAĞRI değildir
# (örn. "if (x > 0) then"). Gerçek dil kelime listesi eksiksiz değil, bilinen en
# yaygın olanları kapsar — eksik kalan biri en kötü ihtimalle gerçek olmayan bir
# "calls" adayı üretir, çözümleme aşamasında zaten hiçbir chunk adına denk gelmez.
PASCAL_KEYWORDS = frozenset("""
begin end if then else while do for to downto case of repeat until try except
finally var const type class record procedure function constructor destructor
property array set packed object interface implementation uses unit program
library inherited nil result true false and or not xor div mod shl shr in is
as with goto label exports threadvar resourcestring out override virtual
overload reintroduce message dynamic abstract sealed final published private
protected public strict deprecated experimental platform unsafe
""".split())

def extract_calls(code: str, own_name: str) -> list[str]:
    """Bir chunk'ın gövdesinde geçen olası çağrı hedeflerinin (bare, küçük harf)
    adlarını çıkarır — `Foo(` veya `Bar.Foo(` kalıplarından `foo` yakalanır (nokta
    öncesi niteleyici -örn. hangi nesne- YOK SAYILIR, çünkü statik tip çözümlemesi
    yapmıyoruz). Bu YALNIZCA bir sezgi (heuristic): gerçek overload/tip çözümlemesi
    YAPILMAZ, sonuç index-time'da isim eşleşmesiyle çözülür (bkz. panel.py
    _link_call_graph) ve birden fazla aday çıkabilir. Anahtar kelimeler ve chunk'ın
    kendi adı hariç tutulur; sıra korunarak tekrarsızlaştırılır, üst sınır 50."""
    own_bare = own_name.split(".")[-1].lower()
    names = []
    for m in CALL_RE.finditer(code):
        low = m.group(1).lower()
        if low in PASCAL_KEYWORDS or low == own_bare:
            continue
        names.append(low)
    return list(dict.fromkeys(names))[:50]

def extract_doc(node, code: bytes) -> str:
    """Düğümün hemen önceki kardeşi '///' ile başlayan bir yorumsa, XML
    <summary> etiketlerinden arındırılmış düz metnini döndürür; yoksa ''."""
    prev = node.prev_sibling
    if prev is None or prev.type != "comment":
        return ""
    txt = code[prev.start_byte:prev.end_byte].decode("utf-8", "replace").strip()
    if not txt.startswith("///"):
        return ""
    txt = re.sub(r"^/+\s*", "", txt)
    txt = SUMMARY_TAG_RE.sub("", txt).strip()
    return txt

def chunk_file(path: pathlib.Path, lib: str, unit: str | None = None):
    """unit: kaynak kök klasöre göre GÖRELİ yol (örn. "Providers/Utils.pas") —
    sadece dosya adı (path.name) DEĞİL. Aynı isimli ama farklı klasörlerdeki
    dosyalar (büyük çok-sağlayıcılı kütüphanelerde yaygın, örn. UniDAC'ın
    kendisinde henüz yok ama başka kütüphanelerde olabilir) aksi halde aynı
    "unit" etiketini alır ve ID'leri çakışabilirdi. Verilmezse path.name'e düşer
    (geriye dönük uyumluluk / tek dosya testleri için)."""
    unit = unit or path.name
    code = path.read_bytes()
    tree = PARSER.parse(code)
    caps = QueryCursor(Q).captures(tree.root_node)
    for kind_key, kind in (("decl", "decl"), ("impl", "method"), ("type", "type")):
        for n in caps.get(kind_key, []):
            text = code[n.start_byte:n.end_byte].decode("utf-8", "replace")
            doc = extract_doc(n, code) if kind_key in ("decl", "impl") else ""
            full_text = f"{doc}\n{text}" if doc else text
            if len(full_text) < 40 or full_text.count("\n") > 400:   # gürültü/aşırı-dev filtresi
                continue
            m = NAME_RE.search(text[:200])
            name = m.group(1) if m else text.split("\n")[0][:60].strip()
            # KRİTİK: satır numarası ID'ye KATILMIYOR — üstüne bir satır eklenince tüm
            # dosyadaki chunk'ların satır numaraları kayar, ID'ye dahil edilirse içerik
            # DEĞİŞMEMİŞ olsa bile ID değişir (doğrulandı: canlı testte tüm chunk'lar
            # "silinmiş+yeniden eklenmiş" görünüp önbellekteki Türkçe çeviriler kaybolurdu).
            # Aşırı yüklü (overload) metodları ayırt etmek için satır no yerine imzanın
            # kendisi (full_text önek) kullanılıyor — parametre listesi farklı olduğu
            # sürece bu zaten benzersiz kalır.
            cid = xxhash.xxh3_64(f"{unit}:{kind_key}:{full_text[:160]}".encode()).hexdigest()
            # calls_raw: sadece "method" (defProc/gövde) chunk'ları için anlamlı —
            # decl/type'ların gövdesi yok, boş liste çıkar (beklenen, sorun değil).
            calls_raw = extract_calls(text, name) if kind_key == "impl" else []
            yield {"id": cid, "lib": lib, "unit": unit, "kind": kind, "name": name,
                   "line_start": n.start_point[0]+1, "line_end": n.end_point[0]+1,
                   "hash": xxhash.xxh3_64(full_text.encode()).hexdigest()[:12],
                   "code": full_text, "doc": doc, "calls_raw": calls_raw}

def main(root: str, lib: str, out: str, patterns: str = "*.pas"):
    """patterns: virgülle ayrılmış bir veya birden fazla glob deseni (örn.
    "*.pas" veya "*.pas,*.dpr" veya "Src/**/*.pas") — rootp.rglob() ile eşleşen
    her desen taranır, aynı dosya birden fazla desene uysa bile TEK sayılır."""
    rootp = pathlib.Path(root); t0 = time.time(); total = 0
    pats = [p.strip() for p in patterns.split(",") if p.strip()] or ["*.pas"]
    seen_files = set()
    for pat in pats:
        seen_files.update(rootp.rglob(pat))
    with open(out, "w", encoding="utf-8") as f:
        for p in sorted(seen_files):
            unit = p.relative_to(rootp).as_posix()   # forward-slash: platformdan bağımsız, kararlı
            for ch in chunk_file(p, lib, unit):
                f.write(json.dumps(ch, ensure_ascii=False) + "\n"); total += 1
    print(f"{len(seen_files)} dosya -> {total} chunk, {time.time()-t0:.1f} sn -> {out}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "*.pas")

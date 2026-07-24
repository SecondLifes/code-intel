"""Chunker v2 — parser-SOYUTLAMALI, çok-dile hazır kaynak ayrıştırıcı (Sıra 5).
Çıktı: JSONL (chunk başına: id, lib, unit, kind, name, satır aralığı, kod, doc, hash).

v2'de değişenler (birleşik yol haritası Sıra 5 — üç borç tek reindex maliyetinde):
1. REPO-KİMLİKLİ ID: hash artık `lib`i de içerir — iki farklı kütüphanede aynı
   göreli yol+imza artık AYNI ID'yi üretmez (merge'deki sessiz çakışma kökten
   çözüldü; mevcut koleksiyonlar GPU'suz migrate edilir, bkz. indexing_svc.migrate_ids_v2).
2. UNITHEAD chunk'ları: her dosyanın `unit X;` başlığı + uses listeleri ayrı bir
   kind="unithead" chunk'ı olarak indekslenir → unit-düzeyi bağımlılık grafı
   (uses kenarları) sembol grafına buradan türer; "hangi unit'ler X'i kullanıyor"
   sorusu aranabilir hale gelir.
3. DEV metodlar artık ATLANMIYOR: >400 satırlık düğümler eskiden tamamen indeks
   dışıydı (dış analizde işaretlenen kapsam deliği). v2 bunları ilk 400 satırla
   (embedding/arama için yeterli) ve huge=true bayrağıyla indeksler — TAM kod
   get_chunk'ın diskten-okuma yoluyla zaten geri gelir.
4. Parser soyutlaması: dil başına bir Chunker sınıfı + uzantı kaydı — çok dil
   pilotu (Sıra 10) yeni bir sınıf eklemekten ibaret olacak.

Hash: XXH3-64 (kriptografik değil, içerik-değişikliği tespiti; sha1'den ~5x hızlı).
declProc'lar defProc'ların yanında AYRICA indekslenir — /// XML doc yorumları
yalnız bildirimlerin üzerinde bulunur; tree-sitter yorumu düğüme dahil etmez
(kardeş düğüm), bu yüzden önceki kardeşe elle bakılır."""
import json, pathlib, re, sys, time
import xxhash
from tree_sitter import Query, QueryCursor
from tree_sitter_language_pack import get_language, get_parser

HUGE_LINES = 400        # bu satır sayısını aşan düğümler "huge" — ilk HUGE_LINES satırla indekslenir
MIN_CHARS = 40          # gürültü filtresi: doc'suz minik bildirimler atlanır


class PascalChunker:
    """Delphi/Pascal (.pas/.dpr/.dpk/.inc) — tree-sitter tabanlı."""
    EXTS = (".pas", ".dpr", ".dpk", ".inc")
    LANG_LABEL = "Pascal/Delphi"

    NAME_RE = re.compile(r"(?:procedure|function|constructor|destructor)\s+([\w.]+)", re.I)
    SUMMARY_TAG_RE = re.compile(r"</?summary>", re.I)
    CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
    UNIT_RE = re.compile(r"^\s*unit\s+([\w.]+)\s*;", re.I | re.M)
    USES_RE = re.compile(r"\buses\b(.*?);", re.I | re.S)
    # Pascal/Delphi ayrılmış sözcükleri — "(" ile takip edilse bile ÇAĞRI değildir.
    KEYWORDS = frozenset("""
    begin end if then else while do for to downto case of repeat until try except
    finally var const type class record procedure function constructor destructor
    property array set packed object interface implementation uses unit program
    library inherited nil result true false and or not xor div mod shl shr in is
    as with goto label exports threadvar resourcestring out override virtual
    overload reintroduce message dynamic abstract sealed final published private
    protected public strict deprecated experimental platform unsafe
    """.split())

    def __init__(self):
        self.lang = get_language("pascal")
        self.parser = get_parser("pascal")
        self.query = Query(self.lang, "(declProc) @decl\n(defProc) @impl\n(declType) @type")

    def extract_calls(self, code: str, own_name: str) -> list[str]:
        """`Foo(`/`Bar.Foo(` kalıplarından bare çağrı adayları (sezgi; overload/tip
        çözümlemesi YOK — index-time'da isim eşleşmesiyle çözülür, bkz. link_call_graph)."""
        own_bare = own_name.split(".")[-1].lower()
        names = []
        for m in self.CALL_RE.finditer(code):
            low = m.group(1).lower()
            if low in self.KEYWORDS or low == own_bare:
                continue
            names.append(low)
        return list(dict.fromkeys(names))[:50]

    def extract_doc(self, node, code: bytes) -> str:
        prev = node.prev_sibling
        if prev is None or prev.type != "comment":
            return ""
        txt = code[prev.start_byte:prev.end_byte].decode("utf-8", "replace").strip()
        if not txt.startswith("///"):
            return ""
        txt = re.sub(r"^/+\s*", "", txt)
        return self.SUMMARY_TAG_RE.sub("", txt).strip()

    def _unithead(self, text: str, lib: str, unit: str):
        """`unit X;` başlığı + uses listelerinden sentetik kind="unithead" chunk'ı.
        `in '...'` yan yolları ve süslü/çift-eğik yorumlar ayıklanır. Başlıksız
        dosyalar (include parçaları, test kırpıntıları) unithead ÜRETMEZ."""
        um = self.UNIT_RE.search(text[:2000])
        if not um:
            return None
        unit_name = um.group(1)
        used: list[str] = []
        for m in self.USES_RE.finditer(text):
            blob = re.sub(r"\{[^}]*\}|//[^\n]*", " ", m.group(1))
            for part in blob.split(","):
                name = part.split(" in ")[0].strip()
                if re.fullmatch(r"[\w.]+", name or "") and name.lower() not in ("interface", "implementation"):
                    used.append(name)
        used = list(dict.fromkeys(used))
        code = f"unit {unit_name};\nuses\n  " + (",\n  ".join(used) if used else "(uses yok)")
        full = code
        cid = xxhash.xxh3_64(f"{lib}:{unit}:unithead:{full[:160]}".encode()).hexdigest()
        return {"id": cid, "lib": lib, "unit": unit, "kind": "unithead", "name": unit_name,
                "line_start": 1, "line_end": text[:um.end()].count("\n") + 1,
                "hash": xxhash.xxh3_64(("\n".join(sorted(used))).encode()).hexdigest()[:12],
                "code": full, "doc": "", "calls_raw": [], "uses": used}

    def chunk_file(self, path: pathlib.Path, lib: str, unit: str | None = None):
        """unit: kaynak köke GÖRE göreli yol (örn. "Providers/Utils.pas") — aynı
        adlı farklı klasör dosyaları ayrışsın diye. Verilmezse path.name."""
        unit = unit or path.name
        code = path.read_bytes()
        text_all = code.decode("utf-8", "replace")
        head = self._unithead(text_all, lib, unit)
        if head:
            yield head
        tree = self.parser.parse(code)
        caps = QueryCursor(self.query).captures(tree.root_node)
        for kind_key, kind in (("decl", "decl"), ("impl", "method"), ("type", "type")):
            for n in caps.get(kind_key, []):
                text = code[n.start_byte:n.end_byte].decode("utf-8", "replace")
                doc = self.extract_doc(n, code) if kind_key in ("decl", "impl") else ""
                full_text = f"{doc}\n{text}" if doc else text
                if len(full_text) < MIN_CHARS:
                    continue
                huge = full_text.count("\n") > HUGE_LINES
                if huge:
                    # v1 bunları TAMAMEN atlıyordu — artık ilk HUGE_LINES satır
                    # indekslenir (arama bulur), tam kod diskten okunur (get_chunk).
                    full_text = "\n".join(full_text.splitlines()[:HUGE_LINES]) + \
                                "\n// ... (dev metod kırpıldı — tam kod kaynak dosyada)"
                m = self.NAME_RE.search(text[:200])
                name = m.group(1) if m else text.split("\n")[0][:60].strip()
                # KRİTİK: satır numarası ID'ye KATILMAZ (satır kayması tüm ID'leri
                # değiştirirdi — canlı doğrulanmış ders). v2: `lib` ID'ye KATILIR —
                # repo-kimlikli ID, merge'de kütüphaneler arası çakışmayı bitirir.
                cid = xxhash.xxh3_64(f"{lib}:{unit}:{kind_key}:{full_text[:160]}".encode()).hexdigest()
                calls_raw = self.extract_calls(text, name) if kind_key == "impl" else []
                out = {"id": cid, "lib": lib, "unit": unit, "kind": kind, "name": name,
                       "line_start": n.start_point[0] + 1, "line_end": n.end_point[0] + 1,
                       "hash": xxhash.xxh3_64(full_text.encode()).hexdigest()[:12],
                       "code": full_text, "doc": doc, "calls_raw": calls_raw}
                if huge:
                    out["huge"] = True
                yield out


# ---------------- parser kaydı (çok-dil pilotunun giriş noktası) ----------------
_CHUNKERS: list = []

def _registry():
    if not _CHUNKERS:
        _CHUNKERS.append(PascalChunker())
    return _CHUNKERS

def chunker_for(path: pathlib.Path):
    for c in _registry():
        if path.suffix.lower() in c.EXTS:
            return c
    return None

# ---- geriye dönük modül-düzeyi API (testler ve link_call_graph kullanır) ----
def chunk_file(path: pathlib.Path, lib: str, unit: str | None = None):
    c = chunker_for(path) or _registry()[0]
    yield from c.chunk_file(path, lib, unit)

def extract_calls(code: str, own_name: str) -> list[str]:
    return _registry()[0].extract_calls(code, own_name)


def main(root: str, lib: str, out: str, patterns: str = "*.pas"):
    """patterns: virgülle ayrılmış glob desen(ler)i; rglob ile taranır, tekrarsız."""
    rootp = pathlib.Path(root); t0 = time.time(); total = 0
    pats = [p.strip() for p in patterns.split(",") if p.strip()] or ["*.pas"]
    seen_files = set()
    for pat in pats:
        seen_files.update(rootp.rglob(pat))
    with open(out, "w", encoding="utf-8") as f:
        for p in sorted(seen_files):
            if chunker_for(p) is None:
                continue
            unit = p.relative_to(rootp).as_posix()   # forward-slash: platformdan bağımsız
            for ch in chunk_file(p, lib, unit):
                f.write(json.dumps(ch, ensure_ascii=False) + "\n"); total += 1
    print(f"{len(seen_files)} dosya -> {total} chunk, {time.time()-t0:.1f} sn -> {out}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "*.pas")

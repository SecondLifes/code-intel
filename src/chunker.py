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


# ================== ÇOK DİLLİ JENERİK MOTOR (Sıra 10) ==================
# Tek tablo-güdümlü sınıf iki katmanı birden taşır:
#  - TAM DESTEK (8 dil): tabloda doc önekleri + import/kalıtım çıkarıcıları +
#    keyword listeleri dolu -> Pascal'daki tüm derinlik (doc, çağrı grafiği,
#    kalıtım kenarları, unithead/import grafiği).
#  - JENERİK (uzun kuyruk): yalnız uzantı kaydı yeter — evrensel düğüm-adı
#    kümeleriyle fonksiyon/sınıf chunk'ları çıkar, arama/rerank/açıklama tam
#    çalışır; graf özellikleri zarifçe eksik kalır (best-effort, eval'siz).
# Grammar'lar tree-sitter-language-pack'ten (306 dil, derlenmiş) lazy yüklenir.

# Evrensel düğüm kümeleri — grammar'ların büyük çoğunluğu bu adlardan birini kullanır.
UNIVERSAL_FUNC_NODES = frozenset("""
function_definition function_declaration method_definition method_declaration
constructor_declaration function_item method singleton_method function
local_function_statement generator_function_declaration fun_declaration
procedure_declaration subroutine func_literal? function_declarator
""".split())
UNIVERSAL_TYPE_NODES = frozenset("""
class_definition class_declaration class_specifier struct_specifier struct_item
enum_item enum_declaration enum_specifier interface_declaration trait_item
impl_item object_declaration record_declaration protocol_declaration
type_declaration struct_declaration module class union_specifier
""".split())

# Ortak keyword tabanı (çağrı sezgisi yanlış pozitifleri) + dil-özel ekler tabloda.
COMMON_KEYWORDS = frozenset("""
if else for while do switch case return break continue new delete try catch
finally throw sizeof typeof not and or in is as with assert yield await
""".split())


def _extract_extends(lang: str, head: str) -> list[str]:
    """Tip chunk'ının BAŞLIK satır(lar)ından üst sınıf/interface adları — dil-özel.
    Sembol grafı bu listeyi payload'dan okur; Pascal kendi yolunu kullanır."""
    def clean(names):
        out = []
        for n in names:
            n = re.sub(r"<[^>]*>", "", n).strip().rstrip("{").strip()
            n = n.split()[-1] if n and lang == "cpp" else n   # public/virtual önekleri at
            if n and re.fullmatch(r"[\w.:]+", n):
                out.append(n.split("::")[-1].split(".")[-1])
        return out
    try:
        if lang == "python":
            m = re.search(r"class\s+\w+\s*\(([^)]*)\)", head)
            return clean(m.group(1).split(",")) if m else []
        if lang in ("javascript", "typescript", "tsx"):
            m = re.search(r"extends\s+([\w.$]+)", head)
            imp = re.search(r"implements\s+([\w.,\s<>]+?)\s*\{", head)
            return clean(([m.group(1)] if m else []) + (imp.group(1).split(",") if imp else []))
        if lang == "java":
            return clean(sum((m.split(",") for m in re.findall(r"(?:extends|implements)\s+([\w.<>,\s]+?)(?=\s+extends|\s+implements|\s*\{|$)", head)), []))
        if lang == "csharp":
            m = re.search(r"(?:class|interface|struct|record)\s+[\w<>]+[^:{]*:\s*([\w.,<>\s]+?)\s*(?:\{|where|$)", head)
            return clean(m.group(1).split(",")) if m else []
        if lang == "cpp":
            m = re.search(r"(?:class|struct)\s+\w+\s*(?:final)?\s*:\s*([^{]+)", head)
            return clean(m.group(1).split(",")) if m else []
        if lang == "rust":
            m = re.search(r"impl(?:<[^>]*>)?\s+([\w:]+)(?:<[^>]*>)?\s+for\s+([\w:]+)", head)
            return clean([m.group(1)]) if m else []   # child= for'daki tip; parent= trait (name'e bakılır)
    except Exception:
        pass
    return []


def _extract_imports(lang: str, text: str) -> list[str]:
    """Dosyanın import/using/include listesi — unithead chunk'ının `uses` alanı
    (unit-düzeyi bağımlılık grafı bunu okur). Dil-özel, best-effort."""
    out: list[str] = []
    try:
        head = text[:8000]
        if lang == "python":
            for m in re.finditer(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", head, re.M):
                out.append((m.group(1) or m.group(2)).split(".")[0])
        elif lang in ("javascript", "typescript", "tsx"):
            out += re.findall(r"(?:import[^'\"]*|require\(\s*)['\"]([^'\"]+)['\"]", head)
        elif lang == "java":
            out += [m.split(".")[-1] if False else m for m in re.findall(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", head, re.M)]
        elif lang in ("c", "cpp"):
            out += re.findall(r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]", head, re.M)
        elif lang == "csharp":
            out += re.findall(r"^\s*(?:global\s+)?using\s+(?:static\s+)?([\w.]+)\s*;", head, re.M)
        elif lang == "go":
            blk = re.search(r"import\s*\(([^)]*)\)", head, re.S)
            src = blk.group(1) if blk else head
            out += re.findall(r"\"([\w./\-]+)\"", src if blk else "\n".join(
                l for l in head.splitlines() if l.strip().startswith("import")))
        elif lang == "rust":
            out += [m.split("::")[0] for m in re.findall(r"^\s*use\s+([\w:]+)", head, re.M)]
    except Exception:
        pass
    return list(dict.fromkeys(x for x in out if x))[:60]


class GenericChunker:
    """Tablo-güdümlü çok dil chunker'ı. cfg alanları:
    exts (zorunlu) · func_nodes/type_nodes (yoksa evrensel kümeler) ·
    doc_prefixes (örn. ["///","/**"]) · keywords (çağrı filtresi ekleri) ·
    full (tam-destek: import+extends+unithead üretilir)"""

    def __init__(self, lang: str, cfg: dict):
        self.lang = lang
        self.cfg = cfg
        self.EXTS = tuple(cfg["exts"])
        self._parser = None   # lazy — 45 dilin parser'ını boot'ta yüklemek israf

    def _p(self):
        if self._parser is None:
            self._parser = get_parser(self.lang)
        return self._parser

    def extract_calls(self, code: str, own_name: str) -> list[str]:
        own_bare = own_name.split(".")[-1].split("::")[-1].lower()
        kws = COMMON_KEYWORDS | frozenset(self.cfg.get("keywords", ()))
        names = []
        for m in PascalChunker.CALL_RE.finditer(code):
            low = m.group(1).lower()
            if low in kws or low == own_bare:
                continue
            names.append(low)
        return list(dict.fromkeys(names))[:50]

    def _name_of(self, node, code: bytes) -> str:
        n = node.child_by_field_name("name")
        if n is None:
            n = node.child_by_field_name("declarator")   # C/C++: isim declarator içinde
            for _ in range(4):
                if n is None:
                    break
                if n.type in ("identifier", "field_identifier", "type_identifier", "name"):
                    break
                n = n.child_by_field_name("declarator") or n.child_by_field_name("name") or \
                    next((c for c in n.children if c.type in ("identifier", "field_identifier", "type_identifier")), None)
        if n is None:   # son çare: ilk identifier torunu (sığ arama)
            stack, depth = list(node.children), 0
            while stack and depth < 60:
                c = stack.pop(0); depth += 1
                if c.type in ("identifier", "type_identifier", "field_identifier", "name", "constant"):
                    n = c; break
                stack = list(c.children)[:6] + stack
        if n is not None:
            return code[n.start_byte:n.end_byte].decode("utf-8", "replace")[:80]
        return ""

    def _python_docstring(self, node, code: bytes) -> str:
        """Python'da doc önceki YORUM değil, gövdenin İLK ifadesi olan üçlü
        tırnaklı string'dir (`def f():\\n    \"\"\"...\"\"\"`) — prev_sibling
        yaklaşımı hiç yakalayamaz, ayrı bir yol gerekir."""
        body = node.child_by_field_name("body")
        if body is None or not body.named_children:
            return ""
        first = body.named_children[0]
        if first.type != "string":
            return ""
        content = next((c for c in first.children if c.type == "string_content"), None)
        txt = code[content.start_byte:content.end_byte].decode("utf-8", "replace") if content else \
            code[first.start_byte:first.end_byte].decode("utf-8", "replace").strip("\"' \n")
        return txt.strip()[:600]

    def _doc_of(self, node, code: bytes) -> str:
        if self.lang == "python":
            return self._python_docstring(node, code)
        prefixes = self.cfg.get("doc_prefixes")
        if not prefixes:
            return ""
        prev = node.prev_sibling
        if prev is None or "comment" not in prev.type:
            return ""
        txt = code[prev.start_byte:prev.end_byte].decode("utf-8", "replace").strip()
        if not any(txt.startswith(p) for p in prefixes):
            return ""
        txt = re.sub(r"^/\*+|\*+/$", "", txt)
        txt = re.sub(r"^\s*(///?|\*|#+)\s?", "", txt, flags=re.M)
        return re.sub(r"</?\w+[^>]*>", "", txt).strip()[:600]

    def chunk_file(self, path: pathlib.Path, lib: str, unit: str | None = None):
        unit = unit or path.name
        code = path.read_bytes()
        text_all = code.decode("utf-8", "replace")
        full_support = self.cfg.get("full", False)
        if full_support:
            imports = _extract_imports(self.lang, text_all)
            if imports:
                head_code = f"// {unit}\n{self.lang} imports:\n  " + "\n  ".join(imports)
                cid = xxhash.xxh3_64(f"{lib}:{unit}:unithead:{head_code[:160]}".encode()).hexdigest()
                yield {"id": cid, "lib": lib, "unit": unit, "kind": "unithead",
                       "name": pathlib.Path(unit).stem, "line_start": 1, "line_end": 1,
                       "hash": xxhash.xxh3_64("\n".join(sorted(imports)).encode()).hexdigest()[:12],
                       "code": head_code, "doc": "", "calls_raw": [], "uses": imports,
                       "lang": self.lang}
        func_nodes = frozenset(self.cfg.get("func_nodes", ())) or UNIVERSAL_FUNC_NODES
        type_nodes = frozenset(self.cfg.get("type_nodes", ())) or UNIVERSAL_TYPE_NODES
        tree = self._p().parse(code)
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            is_func, is_type = node.type in func_nodes, node.type in type_nodes
            if not (is_func or is_type):
                continue
            text = code[node.start_byte:node.end_byte].decode("utf-8", "replace")
            doc = self._doc_of(node, code)
            # Python docstring gövdenin İÇİNDE zaten (text'e dahil) — prev-sibling
            # yorum modelinden farklı olarak ÖNE tekrar EKLENMEZ (çift olurdu).
            full_text = text if (doc and self.lang == "python") else (f"{doc}\n{text}" if doc else text)
            if len(full_text) < MIN_CHARS:
                continue
            huge = full_text.count("\n") > HUGE_LINES
            if huge:
                full_text = "\n".join(full_text.splitlines()[:HUGE_LINES]) + \
                            "\n// ... (dev blok kırpıldı — tam kod kaynak dosyada)"
            name = self._name_of(node, code) or text.split("\n")[0][:60].strip()
            kind_key = "impl" if is_func else "type"
            kind = "method" if is_func else "type"
            cid = xxhash.xxh3_64(f"{lib}:{unit}:{kind_key}:{full_text[:160]}".encode()).hexdigest()
            out = {"id": cid, "lib": lib, "unit": unit, "kind": kind, "name": name,
                   "line_start": node.start_point[0] + 1, "line_end": node.end_point[0] + 1,
                   "hash": xxhash.xxh3_64(full_text.encode()).hexdigest()[:12],
                   "code": full_text, "doc": doc, "lang": self.lang,
                   "calls_raw": self.extract_calls(text, name) if (is_func and full_support) else []}
            if huge:
                out["huge"] = True
            if is_type and full_support:
                ext = _extract_extends(self.lang, text.split("{")[0][:400] if "{" in text[:400] else text[:400])
                if self.lang == "rust" and node.type == "impl_item":
                    # impl Trait for Tip -> child=Tip, parent=Trait; name'i Tip yap
                    m = re.search(r"impl(?:<[^>]*>)?\s+([\w:]+)(?:<[^>]*>)?\s+for\s+([\w:]+)", text[:200])
                    if m:
                        out["name"] = m.group(2).split("::")[-1]
                if ext:
                    out["extends"] = ext
            yield out


# ---- dil tablosu: TAM DESTEK (full=True) + jenerik uzun kuyruk ----
LANG_TABLE: dict[str, dict] = {
    # ---- Katman 1: tam destek ----
    "python":     {"exts": [".py"], "full": True, "doc_prefixes": ["#"],
                   "func_nodes": ["function_definition"], "type_nodes": ["class_definition"],
                   "keywords": ["print", "len", "range", "str", "int", "list", "dict", "set", "type", "super", "isinstance", "enumerate", "zip", "open"]},
    "javascript": {"exts": [".js", ".mjs", ".cjs", ".jsx"], "full": True, "doc_prefixes": ["/**", "//"],
                   "func_nodes": ["function_declaration", "method_definition", "generator_function_declaration"],
                   "type_nodes": ["class_declaration"],
                   "keywords": ["console", "require", "parseint", "settimeout", "json", "object", "array", "promise", "math"]},
    "typescript": {"exts": [".ts", ".mts", ".cts"], "full": True, "doc_prefixes": ["/**", "//"],
                   "func_nodes": ["function_declaration", "method_definition", "generator_function_declaration"],
                   "type_nodes": ["class_declaration", "interface_declaration", "enum_declaration"],
                   "keywords": ["console", "require", "parseint", "settimeout", "json", "object", "array", "promise", "math"]},
    "tsx":        {"exts": [".tsx"], "full": True, "doc_prefixes": ["/**", "//"],
                   "func_nodes": ["function_declaration", "method_definition"],
                   "type_nodes": ["class_declaration", "interface_declaration"],
                   "keywords": ["console", "require", "usestate", "useeffect", "json"]},
    "java":       {"exts": [".java"], "full": True, "doc_prefixes": ["/**"],
                   "func_nodes": ["method_declaration", "constructor_declaration"],
                   "type_nodes": ["class_declaration", "interface_declaration", "enum_declaration", "record_declaration"],
                   "keywords": ["system", "string", "integer", "list", "map", "super", "tostring", "equals", "hashcode", "println"]},
    "c":          {"exts": [".c", ".h"], "full": True, "doc_prefixes": ["/**", "///"],
                   "func_nodes": ["function_definition"],
                   "type_nodes": ["struct_specifier", "enum_specifier", "union_specifier"],
                   "keywords": ["printf", "malloc", "free", "memcpy", "memset", "strlen", "strcpy", "fprintf", "exit"]},
    "cpp":        {"exts": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"], "full": True, "doc_prefixes": ["/**", "///"],
                   "func_nodes": ["function_definition"],
                   "type_nodes": ["class_specifier", "struct_specifier", "enum_specifier"],
                   "keywords": ["printf", "malloc", "free", "memcpy", "std", "cout", "cin", "endl", "static_cast", "dynamic_cast", "make_shared", "make_unique", "push_back", "size", "begin"]},
    "csharp":     {"exts": [".cs"], "full": True, "doc_prefixes": ["///"],
                   "func_nodes": ["method_declaration", "constructor_declaration", "local_function_statement"],
                   "type_nodes": ["class_declaration", "interface_declaration", "struct_declaration", "enum_declaration", "record_declaration"],
                   "keywords": ["console", "tostring", "equals", "gethashcode", "string", "int32", "dispose", "writeline", "nameof", "var"]},
    "go":         {"exts": [".go"], "full": True, "doc_prefixes": ["//"],
                   "func_nodes": ["function_declaration", "method_declaration"],
                   "type_nodes": ["type_declaration"],
                   "keywords": ["fmt", "println", "printf", "len", "cap", "make", "append", "copy", "panic", "recover", "errorf"]},
    "rust":       {"exts": [".rs"], "full": True, "doc_prefixes": ["///", "//!"],
                   "func_nodes": ["function_item"],
                   "type_nodes": ["struct_item", "enum_item", "trait_item", "impl_item"],
                   "keywords": ["println", "vec", "some", "none", "ok", "err", "box", "string", "clone", "unwrap", "expect", "into", "from"]},
    # ---- Katman 2: jenerik (evrensel düğüm kümeleri; best-effort) ----
    "ruby":       {"exts": [".rb"]},
    "php":        {"exts": [".php"]},
    "kotlin":     {"exts": [".kt", ".kts"]},
    "swift":      {"exts": [".swift"]},
    "dart":       {"exts": [".dart"]},
    "scala":      {"exts": [".scala"]},
    "lua":        {"exts": [".lua"]},
    "perl":       {"exts": [".pl", ".pm"]},
    "r":          {"exts": [".r"]},
    "julia":      {"exts": [".jl"]},
    "haskell":    {"exts": [".hs"]},
    "elixir":     {"exts": [".ex", ".exs"]},
    "erlang":     {"exts": [".erl", ".hrl"]},
    "clojure":    {"exts": [".clj", ".cljs"]},
    "ocaml":      {"exts": [".ml", ".mli"]},
    "fsharp":     {"exts": [".fs", ".fsi", ".fsx"]},
    "groovy":     {"exts": [".groovy", ".gradle"]},
    "objc":       {"exts": [".m", ".mm"]},
    "vb":         {"exts": [".vb"]},
    "sql":        {"exts": [".sql"]},
    "bash":       {"exts": [".sh", ".bash"]},
    "powershell": {"exts": [".ps1", ".psm1"]},
    "zig":        {"exts": [".zig"]},
    "nim":        {"exts": [".nim"]},
    "crystal":    {"exts": [".cr"]},
    "d":          {"exts": [".d"]},
    "fortran":    {"exts": [".f90", ".f95", ".f03", ".f"]},
    "matlab":     {"exts": [".mat"]},
    "solidity":   {"exts": [".sol"]},
    "gdscript":   {"exts": [".gd"]},
    "verilog":    {"exts": [".v", ".sv"]},
    "vhdl":       {"exts": [".vhd", ".vhdl"]},
    "tcl":        {"exts": [".tcl"]},
    "ada":        {"exts": [".adb", ".ads"]},
    "elm":        {"exts": [".elm"]},
    "haxe":       {"exts": [".hx"]},
    "odin":       {"exts": [".odin"]},
    "gleam":      {"exts": [".gleam"]},
}

# ---------------- parser kaydı ----------------
_CHUNKERS: list = []

def _registry():
    if not _CHUNKERS:
        _CHUNKERS.append(PascalChunker())
        for lang, cfg in LANG_TABLE.items():
            _CHUNKERS.append(GenericChunker(lang, cfg))
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

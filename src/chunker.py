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

def chunk_file(path: pathlib.Path, lib: str):
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
            cid = xxhash.xxh3_64(f"{path.name}:{kind_key}:{full_text[:160]}".encode()).hexdigest()
            yield {"id": cid, "lib": lib, "unit": path.name, "kind": kind, "name": name,
                   "line_start": n.start_point[0]+1, "line_end": n.end_point[0]+1,
                   "hash": xxhash.xxh3_64(full_text.encode()).hexdigest()[:12],
                   "code": full_text, "doc": doc}

def main(root: str, lib: str, out: str):
    rootp = pathlib.Path(root); t0 = time.time(); total = 0; files = 0
    with open(out, "w", encoding="utf-8") as f:
        for p in sorted(rootp.rglob("*.pas")):
            files += 1
            for ch in chunk_file(p, lib):
                f.write(json.dumps(ch, ensure_ascii=False) + "\n"); total += 1
    print(f"{files} dosya -> {total} chunk, {time.time()-t0:.1f} sn -> {out}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

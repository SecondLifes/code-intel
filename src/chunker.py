"""Phase 1 chunker v1 — Pascal kaynaklarını anlamsal chunk'lara ayırır.
Çıktı: JSONL (chunk başına: id, lib, unit, kind, name, satır aralığı, kod, hash).
Hash: XXH3-64 (xxhash paketi, SSE2/AVX2 hızlandırmalı) — kriptografik olmayan,
sadece içerik değişikliği tespiti (diffleme) için kullanılıyor, sha1'den ~5x hızlı."""
import json, pathlib, re, sys, time
import xxhash
from tree_sitter import Query, QueryCursor
from tree_sitter_language_pack import get_language, get_parser

LANG = get_language("pascal"); PARSER = get_parser("pascal")
Q = Query(LANG, "(defProc) @impl\n(declType) @type")
NAME_RE = re.compile(r"(?:procedure|function|constructor|destructor)\s+([\w.]+)", re.I)

def chunk_file(path: pathlib.Path, lib: str):
    code = path.read_bytes()
    tree = PARSER.parse(code)
    caps = QueryCursor(Q).captures(tree.root_node)
    for kind_key, kind in (("impl", "method"), ("type", "type")):
        for n in caps.get(kind_key, []):
            text = code[n.start_byte:n.end_byte].decode("utf-8", "replace")
            if len(text) < 40 or text.count("\n") > 400:   # gürültü/aşırı-dev filtresi
                continue
            m = NAME_RE.search(text[:200])
            name = m.group(1) if m else text.split("\n")[0][:60].strip()
            cid = xxhash.xxh3_64(f"{path.name}:{n.start_point[0]}:{text[:80]}".encode()).hexdigest()
            yield {"id": cid, "lib": lib, "unit": path.name, "kind": kind, "name": name,
                   "line_start": n.start_point[0]+1, "line_end": n.end_point[0]+1,
                   "hash": xxhash.xxh3_64(text.encode()).hexdigest()[:12], "code": text}

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

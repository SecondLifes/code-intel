import pathlib, time
from tree_sitter import Query, QueryCursor
from tree_sitter_language_pack import get_language, get_parser
lang = get_language("pascal"); parser = get_parser("pascal")
q = Query(lang, "(defProc) @impl")
root = pathlib.Path(r"E:\system\dev\son ayrım\01-Component\2026.6.6\UniDAC 10.3.0\Source")
files = list(root.rglob("*.pas"))
t0=time.time(); err=0; impls=0; failed=[]
for f in files:
    code=f.read_bytes(); tree=parser.parse(code)
    if tree.root_node.has_error: err+=1
    n=len(QueryCursor(q).captures(tree.root_node).get("impl",[]))
    impls+=n
    if n==0 and len(code)>2000: failed.append(f.name)
dt=time.time()-t0
print(f"{len(files)} dosya, {dt:.1f} sn ({len(files)/dt:.0f} dosya/sn)")
print(f"has_error içeren: {err} ({100*err/len(files):.1f}%)  |  toplam metod gövdesi: {impls}")
print("0 metod çıkan büyük dosyalar (ilk 5):", failed[:5])

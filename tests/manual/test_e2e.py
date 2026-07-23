import pathlib, time
from tree_sitter import Query, QueryCursor
from tree_sitter_language_pack import get_language, get_parser
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

# 1) Gerçek chunk'lar: UniDAC Uni.pas metodları
lang=get_language("pascal"); parser=get_parser("pascal")
code=open(r"E:\system\dev\son ayrım\01-Component\2026.6.6\UniDAC 10.3.0\Source\Uni.pas","rb").read()
tree=parser.parse(code)
caps=QueryCursor(Query(lang,"(defProc) @impl")).captures(tree.root_node)
chunks=[]
for n in caps["impl"][:40]:
    txt=code[n.start_byte:n.end_byte].decode("utf-8","replace")
    if 5 <= txt.count("\n") <= 60: chunks.append((txt, n.start_point[0]+1))
print(f"{len(chunks)} gerçek metod chunk'ı hazır")

# 2) BGE-M3 indir + embed
t0=time.time()
model=TextEmbedding("intfloat/multilingual-e5-large")  # gece testi: fastembed çok-dilli; BGE-M3 Phase-3te sentence-transformers ile
vecs=list(model.embed([c[0] for c in chunks]))
print(f"BGE-M3 hazır+embed: {time.time()-t0:.0f} sn | boyut: {len(vecs[0])}")

# 3) Qdrant'a yaz + Türkçe sorguyla ara
cl=QdrantClient("http://localhost:6333")
cl.recreate_collection("pilot", vectors_config=models.VectorParams(size=len(vecs[0]), distance=models.Distance.COSINE))
cl.upsert("pilot", points=[models.PointStruct(id=i, vector=v.tolist(), payload={"line":chunks[i][1],"head":chunks[i][0].split("\n")[0][:80]}) for i,v in enumerate(vecs)])
soru="veritabanı bağlantısını açan ve kapatan fonksiyon"
qv=list(model.embed([soru]))[0]
hits=cl.query_points("pilot", query=qv.tolist(), limit=3).points
print(f"\nTÜRKÇE SORGU: '{soru}'")
for h in hits: print(f"  skor {h.score:.3f} | L{h.payload['line']}: {h.payload['head']}")

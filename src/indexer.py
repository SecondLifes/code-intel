"""Phase 3 v1 — chunks JSONL -> Qdrant (dense, multilingual-e5; BGE-M3 sonra)."""
import json, sys, time
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

def main(jsonl, coll):
    rows=[json.loads(l) for l in open(jsonl,encoding='utf-8')]
    print(f"{len(rows)} chunk yükleniyor -> '{coll}'")
    model=TextEmbedding("intfloat/multilingual-e5-large")
    cl=QdrantClient("http://localhost:6333", timeout=120)
    if not cl.collection_exists(coll):
        cl.create_collection(coll, vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE))
    t0=time.time(); B=64
    for i in range(0,len(rows),B):
        batch=rows[i:i+B]
        texts=[f"passage: {r['unit']} {r['name']}\n{r['code'][:2000]}" for r in batch]
        vecs=list(model.embed(texts))
        cl.upsert(coll, points=[models.PointStruct(
            id=int(r['id'][:12],16), vector=v.tolist(),
            payload={k:r[k] for k in('lib','unit','kind','name','line_start','line_end','hash')} | {"code":r['code'][:4000]}
        ) for r,v in zip(batch,vecs)])
        if i % 1280 == 0:
            el=time.time()-t0; done=i+len(batch)
            print(f"  {done}/{len(rows)}  {done/el:.0f} chunk/sn  ETA {((len(rows)-done)/(done/el))/60:.0f} dk", flush=True)
    print(f"BITTI: {len(rows)} chunk, {(time.time()-t0)/60:.1f} dk")
    print(cl.get_collection(coll).points_count, "nokta koleksiyonda")

if __name__=="__main__": main(sys.argv[1], sys.argv[2])

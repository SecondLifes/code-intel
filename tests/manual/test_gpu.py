import os, sys, json, time, pathlib
# pip nvidia DLL'lerini ORT'un bulacağı yere ekle
venv = pathlib.Path(sys.prefix)
for p in venv.glob("Lib/site-packages/nvidia/*/bin"):
    os.add_dll_directory(str(p)); os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]
from fastembed import TextEmbedding
rows=[json.loads(l) for l in open('data/chunks-unidac.jsonl',encoding='utf-8')][:256]
texts=[f"passage: {r['unit']} {r['name']}\n{r['code'][:2000]}" for r in rows]
m=TextEmbedding("intfloat/multilingual-e5-large", providers=["CUDAExecutionProvider"])
list(m.embed(texts[:8]))  # ısınma
t0=time.time(); vecs=list(m.embed(texts)); dt=time.time()-t0
print(f"GPU: 256 chunk {dt:.1f} sn = {256/dt:.0f} chunk/sn  (CPU 2.2 idi -> {256/dt/2.2:.0f}x hızlanma)")

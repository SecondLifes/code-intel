"""Küçük bir Recall@k değerlendirme koşucusu — arama kalitesini "tahmin" değil
ÖLÇÜLEBİLİR bir sayı ile takip etmek için (Gemini/Codex analizlerinin ikisinin de
öncelik #1 önerisi). golden_qa.json'daki her soru için gerçek hibrit aramayı
çalıştırır, beklenen isimlerden HERHANGİ birinin top-k sonuçlarda geçip geçmediğine
bakar.

Çalıştır (Qdrant + Ollama + gerçek 'unidac' indeksi ayakta olmalı):
  .venv/Scripts/python.exe tests/eval.py [--collection unidac] [--mode hybrid] [--k 8]
"""
import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import retrieval  # noqa: E402


def run(collection: str, mode: str, top_k: int):
    qa = json.loads((pathlib.Path(__file__).parent / "golden_qa.json").read_text(encoding="utf-8"))
    hits, total_ms = 0, 0.0
    rows = []
    for item in qa:
        t0 = time.time()
        result = retrieval.search(item["question"], [collection], mode, top_k)
        ms = (time.time() - t0) * 1000
        total_ms += ms
        if "error" in result:
            rows.append((item["question"], False, f"HATA: {result['error']}"))
            continue
        names = [h.get("name", "") or "" for h in result["hits"]]
        found = any(exp.lower() in n.lower() for n in names for exp in item["expected_names"])
        if found:
            hits += 1
        rows.append((item["question"], found, "; ".join(names[:3])))

    print(f"\nKoleksiyon: {collection} | mod: {mode} | top_k: {top_k}\n")
    for q, ok, sample in rows:
        mark = "[OK]" if ok else "[XX]"   # Windows konsol kodlamaları (cp1254 vb.) emoji yazamayabiliyor
        print(f"  {mark}  {q}")
        print(f"        -> {sample}")
    recall = hits / len(qa) if qa else 0.0
    print(f"\nRecall@{top_k}: {hits}/{len(qa)} = {recall:.0%}   |   ortalama arama suresi: {total_ms/len(qa):.0f}ms")
    return recall


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", default="unidac")
    ap.add_argument("--mode", default="hybrid", choices=["hybrid", "dense", "sparse"])
    ap.add_argument("--k", type=int, default=8)
    args = ap.parse_args()
    run(args.collection, args.mode, args.k)

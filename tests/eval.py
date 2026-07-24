"""Arama kalitesi değerlendirme koşucusu — "tahmin" değil ÖLÇÜLEBİLİR sayılar.

golden_qa.json artık ÇOK KOLEKSİYONLU: her kayıtta "collection" alanı var
(60 soru: unidac 22, Jedi 12, Synopse-mORMot2 14, RESTRequest4Delphi 12).
Metrikler: Recall@k, MRR, nDCG@k (binary, ilk isabet), gecikme p50/p95.

Çalıştır (Qdrant + ilgili indeksler ayakta olmalı):
  .venv/Scripts/python.exe tests/eval.py                      # tüm koleksiyonlar
  .venv/Scripts/python.exe tests/eval.py --collection unidac  # tek koleksiyon
  .venv/Scripts/python.exe tests/eval.py --rerank             # rerank açık ölç
  .venv/Scripts/python.exe tests/eval.py --compare            # baseline vs rerank yan yana
"""
import argparse
import json
import math
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import retrieval  # noqa: E402


def _first_hit_rank(names: list[str], expected: list[str]) -> int | None:
    """Beklenen isimlerden herhangi birinin İLK göründüğü sıra (1 tabanlı), yoksa None."""
    for i, n in enumerate(names):
        if any(exp.lower() in n.lower() for exp in expected):
            return i + 1
    return None


def run(collections: list[str] | None, mode: str, top_k: int, rerank: bool = False,
        expand: bool = False, verbose: bool = True) -> dict:
    qa = json.loads((pathlib.Path(__file__).parent / "golden_qa.json").read_text(encoding="utf-8"))
    if collections:
        qa = [x for x in qa if x.get("collection", "unidac") in collections]
    if not qa:
        print("Seçilen koleksiyon(lar) için soru yok."); return {}

    per_coll: dict[str, dict] = {}
    latencies: list[float] = []
    for item in qa:
        coll = item.get("collection", "unidac")
        st = per_coll.setdefault(coll, {"n": 0, "hits": 0, "rr": 0.0, "ndcg": 0.0, "rows": []})
        t0 = time.time()
        # log=False: eval koşuları panel Analitik'ine (gerçek kullanıcı telemetrisi) karışmasın
        result = retrieval.search(item["question"], [coll], mode, top_k, rerank=rerank, expand=expand, log=False)
        ms = (time.time() - t0) * 1000
        latencies.append(ms)
        st["n"] += 1
        if "error" in result:
            st["rows"].append((item["question"], None, f"HATA: {result['error'][:120]}"))
            continue
        names = [h.get("name", "") or "" for h in result["hits"]]
        rank = _first_hit_rank(names, item["expected_names"])
        if rank is not None:
            st["hits"] += 1
            st["rr"] += 1.0 / rank
            st["ndcg"] += 1.0 / math.log2(rank + 1)   # binary nDCG@k, tek ilgili varsayımı (IDCG=1)
        st["rows"].append((item["question"], rank, "; ".join(names[:3])))

    total_n = sum(s["n"] for s in per_coll.values())
    total_hits = sum(s["hits"] for s in per_coll.values())
    agg = {
        "recall": total_hits / total_n,
        "mrr": sum(s["rr"] for s in per_coll.values()) / total_n,
        "ndcg": sum(s["ndcg"] for s in per_coll.values()) / total_n,
        "p50": statistics.median(latencies),
        "p95": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)],
        "per_coll": {c: {"recall": s["hits"] / s["n"], "mrr": s["rr"] / s["n"],
                          "ndcg": s["ndcg"] / s["n"], "n": s["n"]} for c, s in per_coll.items()},
    }

    if verbose:
        print(f"\nmod: {mode} | top_k: {top_k} | rerank: {rerank} | {total_n} soru\n")
        for coll, s in per_coll.items():
            m = agg["per_coll"][coll]
            print(f"[{coll}]  Recall@{top_k}: {s['hits']}/{s['n']} = {m['recall']:.0%}"
                  f"   MRR: {m['mrr']:.3f}   nDCG@{top_k}: {m['ndcg']:.3f}")
            for q, rank, sample in s["rows"]:
                mark = "[OK]" if rank else "[XX]"   # Windows konsolu (cp1254) emoji yazamayabiliyor
                rk = f"#{rank}" if rank else "yok"
                print(f"  {mark} ({rk:>4})  {q}")
                if rank is None:
                    print(f"           -> {sample}")
        print(f"\nGENEL  Recall@{top_k}: {total_hits}/{total_n} = {agg['recall']:.0%}"
              f"   MRR: {agg['mrr']:.3f}   nDCG@{top_k}: {agg['ndcg']:.3f}"
              f"   gecikme p50: {agg['p50']:.0f}ms  p95: {agg['p95']:.0f}ms")
    return agg


def compare(collections: list[str] | None, mode: str, top_k: int):
    """Baseline (rerank kapalı) ile rerank açık koşuyu yan yana karşılaştırır."""
    print("== A: baseline (rerank kapalı) ==")
    a = run(collections, mode, top_k, rerank=False, verbose=False)
    print("== B: rerank açık ==")
    b = run(collections, mode, top_k, rerank=True, verbose=False)
    if not a or not b:
        return
    print(f"\n{'':24} {'A: baseline':>14} {'B: rerank':>14} {'fark':>10}")
    for key, fmt in (("recall", ".0%"), ("mrr", ".3f"), ("ndcg", ".3f"), ("p50", ".0f"), ("p95", ".0f")):
        d = b[key] - a[key]
        print(f"{key:24} {a[key]:>14{fmt}} {b[key]:>14{fmt}} {d:>+10{fmt}}")
    print()
    for coll in a["per_coll"]:
        am, bm = a["per_coll"][coll], b["per_coll"].get(coll, {})
        if bm:
            print(f"[{coll}] MRR {am['mrr']:.3f} -> {bm['mrr']:.3f} ({bm['mrr']-am['mrr']:+.3f})"
                  f" | Recall {am['recall']:.0%} -> {bm['recall']:.0%}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", action="append", default=None,
                    help="yalnız bu koleksiyon(lar) — birden fazla kez verilebilir")
    ap.add_argument("--mode", default="hybrid", choices=["hybrid", "dense", "sparse"])
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--rerank", action="store_true", help="cross-encoder yeniden sıralamayı da ölç")
    ap.add_argument("--expand", action="store_true", help="LLM sorgu genişletmeyi de ölç (A2 pilotu)")
    ap.add_argument("--compare", action="store_true", help="baseline vs rerank yan yana")
    args = ap.parse_args()
    if args.compare:
        compare(args.collection, args.mode, args.k)
    else:
        run(args.collection, args.mode, args.k, args.rerank, args.expand)

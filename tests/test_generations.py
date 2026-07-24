"""Sıra 27: atomik staging+alias indeks nesli modeli — hem saf mekanizma
(services/generations.py) hem de _run_index(staged=True) uçtan uca testleri.
Yalnız atılabilir __test_gen_* fixture koleksiyonlarıyla çalışır; gerçek
Jedi/mORMot2/unidac/RESTRequest4Delphi koleksiyonlarına HİÇ dokunulmaz —
staged bilerek OPT-IN (varsayılan False), bu testler onu AÇIKÇA istiyor.
"""
import pathlib
import sys

import pytest
from qdrant_client import models

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.test_api import QDRANT_UP, needs_qdrant  # noqa: E402


def _cleanup(name: str):
    import retrieval
    from services import generations as gen
    cl = retrieval.cl
    for c in cl.get_collections().collections:
        if c.name == name or c.name.startswith(name + gen.GEN_SEP):
            cl.delete_collection(c.name)
    try:
        cl.update_collection_aliases(change_aliases_operations=[
            models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=name))])
    except Exception:
        pass


@needs_qdrant
def test_generations_module_lifecycle():
    """Saf mekanizma: plain->gen1+alias dönüşümü, seed'li yeni nesil, takas
    öncesi/sonrası izolasyon, eski nesil budama."""
    import retrieval
    from services import generations as gen
    cl = retrieval.cl
    name = "__test_gen_lifecycle"
    _cleanup(name)
    try:
        vcfg, scfg = {}, {"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)}
        cl.create_collection(name, vectors_config=vcfg, sparse_vectors_config=scfg)
        cl.upsert(name, points=[models.PointStruct(id=1, vector={}, payload={"v": 1})])
        assert not gen.is_generational(name)

        gen1 = gen.ensure_generational(name)
        assert gen1 == f"{name}__gen1" and gen.is_generational(name)

        gen2 = gen.start_new_generation(name, vcfg, scfg, seed=True)
        cl.upsert(gen2, points=[models.PointStruct(id=1, vector={}, payload={"v": 2})])
        # takas öncesi: alias hâlâ ESKİ nesli göstermeli (izolasyon)
        pts, _ = cl.scroll(name, limit=10, with_payload=True)
        assert pts[0].payload["v"] == 1

        gen.swap_alias(name, gen2, keep_previous=0)
        pts2, _ = cl.scroll(name, limit=10, with_payload=True)
        assert pts2[0].payload["v"] == 2
        assert not cl.collection_exists(gen1), "keep_previous=0 eski nesli silmeliydi"
    finally:
        _cleanup(name)


PAS_A = "unit A;\n\ninterface\n\nfunction Foo: Integer;\n\nimplementation\n\n/// <summary>Ilk surum.</summary>\nfunction Foo: Integer;\nbegin\n  Result := 1;\nend;\n\nend.\n"
PAS_A_V2 = "unit A;\n\ninterface\n\nfunction Foo: Integer;\n\nimplementation\n\n/// <summary>Guncellendi.</summary>\nfunction Foo: Integer;\nbegin\n  Result := 2;\nend;\n\nend.\n"
PAS_TYPE = ("unit T;\n\ninterface\n\ntype\n"
            "  /// <summary>Temel siniftir, ortak alanlari tasir.</summary>\n"
            "  TBase = class\n    FValue: Integer;\n  end;\n"
            "  /// <summary>TBase'den turer, ek davranis ekler.</summary>\n"
            "  TChild = class(TBase)\n    FExtra: Integer;\n  end;\n\n"
            "implementation\n\nend.\n")


@needs_qdrant
def test_run_index_staged_end_to_end(tmp_path):
    """_run_index(staged=True) gerçek uçtan uca: ilk indeksleme (gen1+alias),
    değişiklikle ikinci indeksleme (gen2'ye taşınır, atomik takas, eski nesil
    budanır), arama/scroll/sembol-grafı hep MANTIKSAL ada göre çalışmalı."""
    import retrieval
    from services import generations as gen
    from services.common import STATE
    from services import indexing_svc as isvc
    cl = retrieval.cl
    name = "__test_gen_e2e"
    _cleanup(name)
    src = tmp_path / "src"
    src.mkdir()
    (src / "A.pas").write_text(PAS_A, encoding="utf-8")
    (src / "T.pas").write_text(PAS_TYPE, encoding="utf-8")
    try:
        req1 = isvc.IndexReq(collection=name, path=str(src), vectors=["sparse"], device="cpu",
                              patterns="*.pas", staged=True)
        STATE["index_job"] = {"collection": name, "phase": "starting"}
        isvc._run_index(req1)
        assert STATE["index_job"]["phase"] == "done", STATE["index_job"].get("error")
        assert gen.is_generational(name)
        assert gen.current_generation(name) == f"{name}__gen1"

        r = retrieval.search("Foo", [name], mode="sparse", top_k=5, log=False)
        assert any(h["name"] == "Foo" for h in r["hits"]), r

        hier = retrieval.get_type_hierarchy(name, "TChild")
        assert any(a["name"].lower() == "tbase" for a in hier.get("ancestors", [])), hier

        # ---- ikinci koşu: içerik değişti -> gen2, atomik takas ----
        (src / "A.pas").write_text(PAS_A_V2, encoding="utf-8")
        req2 = isvc.IndexReq(collection=name, path=str(src), vectors=["sparse"], device="cpu",
                              patterns="*.pas", staged=True)
        STATE["index_job"] = {"collection": name, "phase": "starting"}
        isvc._run_index(req2)
        assert STATE["index_job"]["phase"] == "done", STATE["index_job"].get("error")
        assert gen.current_generation(name) == f"{name}__gen2"
        # keep_previous=1 (varsayılan) -> güncel + 1 ÖNCEKİ nesil tutulur (toplam 2) —
        # yalnız iki nesil üretildiği için gen1 HÂLÂ var olmalı (3. nesilde budanır,
        # bkz. services/generations.py'nin kendi doğrulaması: verify_generations.py).
        assert cl.collection_exists(f"{name}__gen1")

        pts, _ = cl.scroll(name, limit=50, with_payload=True,
                            scroll_filter=models.Filter(must=[models.FieldCondition(key="name", match=models.MatchValue(value="Foo"))]))
        assert any("Guncellendi" in p.payload.get("doc", "") for p in pts), [p.payload for p in pts]

        # sembol grafı hâlâ MANTIKSAL adla sorgulanabilir olmalı (rekey doğrulaması)
        hier2 = retrieval.get_type_hierarchy(name, "TChild")
        assert any(a["name"].lower() == "tbase" for a in hier2.get("ancestors", [])), hier2
    finally:
        _cleanup(name)
        for f in (ROOT / f"data/chunks-{name}.jsonl",):
            if f.exists():
                f.unlink()


@needs_qdrant
def test_collection_delete_removes_all_generations(tmp_path):
    """Canlı doğrulamada bulunan gerçek hata: cl.delete_collection(alias) SESSİZCE
    hiçbir şey yapmıyor (Qdrant, scroll/upsert'in aksine delete'te alias'ı
    ÇÖZMÜYOR) — /api/collection DELETE ucu bunu fark etmeden {"ok": true}
    dönüp veriyi OLDUĞU GİBİ bırakıyordu. admin_routes.collection_delete artık
    generations.is_generational() kontrolüyle bunu ayırt edip
    delete_all_generations() çağırıyor — bu test o düzeltmeyi kanıtlar."""
    import retrieval
    from services import generations as gen
    from services.common import STATE
    from services import indexing_svc as isvc
    cl = retrieval.cl
    name = "__test_gen_delete"
    _cleanup(name)
    src = tmp_path / "src"
    src.mkdir()
    (src / "A.pas").write_text(PAS_A, encoding="utf-8")
    try:
        req = isvc.IndexReq(collection=name, path=str(src), vectors=["sparse"], device="cpu",
                             patterns="*.pas", staged=True)
        STATE["index_job"] = {"collection": name, "phase": "starting"}
        isvc._run_index(req)
        assert gen.is_generational(name)
        real = gen.current_generation(name)
        assert cl.collection_exists(real)

        from fastapi.testclient import TestClient
        from src.panel import app
        with TestClient(app) as client:
            r = client.delete("/api/collection", params={"collection": name})
            assert r.status_code == 200 and r.json()["ok"] is True

        assert not gen.is_generational(name)
        assert not cl.collection_exists(real), "eski hatalı davranışta bu ASLA silinmiyordu"
        assert not any(a.alias_name == name for a in cl.get_aliases().aliases)
    finally:
        _cleanup(name)
        f = ROOT / f"data/chunks-{name}.jsonl"
        if f.exists():
            f.unlink()


@needs_qdrant
def test_run_index_non_staged_unaffected(tmp_path):
    """Varsayılan staged=False: davranış AYNEN korunmalı — alias YOK, düz koleksiyon."""
    import retrieval
    from services import generations as gen
    from services.common import STATE
    from services import indexing_svc as isvc
    name = "__test_gen_plain"
    _cleanup(name)
    src = tmp_path / "src"
    src.mkdir()
    (src / "A.pas").write_text(PAS_A, encoding="utf-8")
    try:
        req = isvc.IndexReq(collection=name, path=str(src), vectors=["sparse"], device="cpu", patterns="*.pas")
        assert req.staged is False
        STATE["index_job"] = {"collection": name, "phase": "starting"}
        isvc._run_index(req)
        assert STATE["index_job"]["phase"] == "done", STATE["index_job"].get("error")
        assert not gen.is_generational(name)
        assert retrieval.cl.collection_exists(name)
    finally:
        _cleanup(name)
        f = ROOT / f"data/chunks-{name}.jsonl"
        if f.exists():
            f.unlink()

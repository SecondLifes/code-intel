"""Yönetim rotaları: sağlık, tarihçe, profil, koleksiyon CRUD, export/import, yedek, donanım, sayfalar."""
import gzip
import json
import pathlib
import re
import subprocess
import threading
import urllib.request
from datetime import datetime

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from qdrant_client import models

try:
    from .. import retrieval
    from ..services.common import (cl, ROOT, OLLAMA, INTERNAL_COLLS, STATE, HISTORY_COLL, PROFILE_COLL,
                                    BACKUP_DIR, BACKUP_KEEP, BACKUP_AUTO_MAX_POINTS)
    from ..services.profiles import (profile_id, get_profile, set_profile, get_history,
                                      list_owners, upsert_owner, delete_owner, list_groups, upsert_group, delete_group)
    from ..services.collections_svc import _copy_all_points, _export_line_iter, _gzip_iter, _run_backup
except ImportError:
    import retrieval
    from services.common import (cl, ROOT, OLLAMA, INTERNAL_COLLS, STATE, HISTORY_COLL, PROFILE_COLL,
                                  BACKUP_DIR, BACKUP_KEEP, BACKUP_AUTO_MAX_POINTS)
    from services.profiles import (profile_id, get_profile, set_profile, get_history,
                                    list_owners, upsert_owner, delete_owner, list_groups, upsert_group, delete_group)
    from services.collections_svc import _copy_all_points, _export_line_iter, _gzip_iter, _run_backup

router = APIRouter()

# ---------------- sağlık / listeler ----------------
@router.get("/api/health")
def health():
    out = {"qdrant": False, "ollama": False, "gpu": retrieval.gpu_available(), "collections": []}
    try:
        cols = []
        for c in cl.get_collections().collections:
            if c.name in INTERNAL_COLLS:
                continue
            info = cl.get_collection(c.name)
            v = info.config.params.vectors
            vecs = list(v.keys()) if isinstance(v, dict) else (["default"] if v else [])
            sv = info.config.params.sparse_vectors
            svecs = list(sv.keys()) if isinstance(sv, dict) else []
            prof = get_profile(c.name)
            cols.append({"name": c.name, "points": info.points_count, "vectors": vecs + [f"{s}(sparse)" for s in svecs],
                         "owner": prof.get("owner", ""), "group": prof.get("group", "")})
        out["collections"] = cols
        out["qdrant"] = True
    except Exception: pass
    try:
        urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3); out["ollama"] = True
    except Exception: pass
    return out

# ---------------- indeksleme geçmişi (koleksiyon -> [{yol, tarih, vektörler, chunk}]) ----------------
@router.get("/api/history")
def history_get(collection: str = ""):
    return get_history(collection or None)

# ---------------- indeks profili (versiyon, klasör, dil gibi kullanıcı alanları) ----------------
class ProfileReq(BaseModel):
    collection: str
    version: str | None = None
    path: str | None = None       # reindex'e gerek KALMADAN düzeltilebilsin diye (disk/klasör taşındığında)
    language: str | None = None   # otomatik etiketi elle düzeltebilmek için
    priority: int | None = None   # 0-5 yıldız — çoklu koleksiyon aramasında skor boost'u için
    owner: str | None = None      # örn. "viniciussanchez" — Owner→Collection modeli, _owners kayıt defterinden seçilir
    group: str | None = None      # fonksiyonel/konu etiketi — örn. "REST Library", "Şifreleme" — _groups kayıt defterinden seçilir
    auto_refresh: bool | None = None   # açıksa watcher kaynak klasörü periyodik tarayıp değişiklikte artımlı reindex tetikler
    kaynak: str | None = None     # "git" | "ticari" | "yerel" | "diğer" — "Tümünü Güncelle" bunu filtreler
    url: str | None = None        # git ise remote URL (otomatik doldurulur), değilse ürün/ana sayfa

@router.get("/api/profile")
def profile_get(collection: str):
    return get_profile(collection)

VALID_KAYNAK = {"git", "ticari", "yerel", "diğer"}

@router.post("/api/profile")
def profile_set(r: ProfileReq):
    # yalnızca gönderilen alanlar güncellenir — None olanlara dokunulmaz (set_profile zaten filtreler)
    if r.priority is not None and not (0 <= r.priority <= 5):
        return JSONResponse({"error": "priority 0-5 aralığında olmalı"}, status_code=400)
    # boş string ("—" seçeneği) bilinçli izinli — alanı TEMİZLEMEK için kullanılır
    if r.kaynak and r.kaynak not in VALID_KAYNAK:
        return JSONResponse({"error": f"kaynak şunlardan biri olmalı: {sorted(VALID_KAYNAK)}"}, status_code=400)
    set_profile(r.collection, version=r.version, path=r.path, language=r.language, priority=r.priority,
                owner=r.owner, group=r.group, auto_refresh=r.auto_refresh, kaynak=r.kaynak, url=r.url)
    return {"ok": True}

# ---------------- koleksiyon silme (kendisi + geçmiş + profil kayıtları) ----------------
@router.delete("/api/collection")
def collection_delete(collection: str):
    if collection in INTERNAL_COLLS:
        return JSONResponse({"error": "iç sistem koleksiyonu silinemez"}, status_code=400)
    if not cl.collection_exists(collection):
        return JSONResponse({"error": f"koleksiyon yok: {collection}"}, status_code=404)
    cl.delete_collection(collection)
    if cl.collection_exists(HISTORY_COLL):
        hist_ids = [p.id for p in cl.scroll(HISTORY_COLL, limit=10000,
                    scroll_filter=models.Filter(must=[models.FieldCondition(key="collection", match=models.MatchValue(value=collection))]))[0]]
        if hist_ids:
            cl.delete(HISTORY_COLL, points_selector=models.PointIdsList(points=hist_ids))
    if cl.collection_exists(PROFILE_COLL):
        cl.delete(PROFILE_COLL, points_selector=models.PointIdsList(points=[profile_id(collection)]))
    jsonl = ROOT / f"data/chunks-{collection}.jsonl"
    if jsonl.exists():
        jsonl.unlink()
    return {"ok": True}

# ---------------- koleksiyon yeniden adlandırma ----------------
class RenameReq(BaseModel):
    old_name: str; new_name: str

@router.post("/api/collection/rename")
def collection_rename(r: RenameReq):
    if r.old_name in INTERNAL_COLLS or r.new_name in INTERNAL_COLLS:
        return JSONResponse({"error": "iç sistem koleksiyonu adı kullanılamaz"}, status_code=400)
    if not cl.collection_exists(r.old_name):
        return JSONResponse({"error": f"koleksiyon yok: {r.old_name}"}, status_code=404)
    if cl.collection_exists(r.new_name):
        return JSONResponse({"error": f"'{r.new_name}' zaten mevcut"}, status_code=409)
    # Qdrant'ta collection rename yoktur: aynı vektör şemasıyla yeni koleksiyon
    # açılır, tüm noktalar kopyalanır, geçmiş/profil taşınır, en son eski silinir —
    # büyük koleksiyonlarda zaman alır ama tek yol bu.
    info = cl.get_collection(r.old_name)
    cl.create_collection(r.new_name, vectors_config=info.config.params.vectors,
                          sparse_vectors_config=info.config.params.sparse_vectors)
    retrieval.ensure_payload_indexes(r.new_name)
    n, _ = _copy_all_points(r.old_name, r.new_name)
    if cl.collection_exists(HISTORY_COLL):
        cl.set_payload(HISTORY_COLL, payload={"collection": r.new_name},
                        points=models.Filter(must=[models.FieldCondition(key="collection", match=models.MatchValue(value=r.old_name))]))
    prof = get_profile(r.old_name)
    if prof:
        set_profile(r.new_name, **{k: v for k, v in prof.items() if k != "collection"})
        if cl.collection_exists(PROFILE_COLL):
            cl.delete(PROFILE_COLL, points_selector=models.PointIdsList(points=[profile_id(r.old_name)]))
    cl.delete_collection(r.old_name)
    old_jsonl = ROOT / f"data/chunks-{r.old_name}.jsonl"
    if old_jsonl.exists():
        old_jsonl.rename(ROOT / f"data/chunks-{r.new_name}.jsonl")
    return {"ok": True, "points_copied": n}

# ---------------- koleksiyonları birleştirme (kaynaklar SİLİNMEZ, sadece kopyalanır) ----------------
class MergeReq(BaseModel):
    sources: list[str]; target: str

@router.post("/api/collection/merge")
def collection_merge(r: MergeReq):
    if r.target in INTERNAL_COLLS or any(s in INTERNAL_COLLS for s in r.sources):
        return JSONResponse({"error": "iç sistem koleksiyonu kullanılamaz"}, status_code=400)
    missing = [s for s in r.sources if not cl.collection_exists(s)]
    if missing:
        return JSONResponse({"error": f"koleksiyon(lar) yok: {missing}"}, status_code=404)
    if not r.sources:
        return JSONResponse({"error": "en az bir kaynak koleksiyon gerekli"}, status_code=400)
    if not cl.collection_exists(r.target):
        info = cl.get_collection(r.sources[0])
        cl.create_collection(r.target, vectors_config=info.config.params.vectors,
                              sparse_vectors_config=info.config.params.sparse_vectors)
    retrieval.ensure_payload_indexes(r.target)
    existing_ids: set[int] = set()
    next_page = None
    while True:
        batch, next_page = cl.scroll(r.target, limit=10000, offset=next_page, with_payload=False, with_vectors=False)
        existing_ids.update(p.id for p in batch)
        if next_page is None:
            break
    # owner/group bilgisi: hedefte zaten yoksa İLK kaynağın profili kopyalanır —
    # kaynaklar farklı sahip/gruplarda olabilir, bunu sessizce "doğru" saymak yerine
    # yanıtta açıkça bildiriyoruz (kullanıcı isterse Ayarlar'dan elle düzeltir).
    owners = {get_profile(s).get("owner") for s in r.sources if get_profile(s).get("owner")}
    groups = {get_profile(s).get("group") for s in r.sources if get_profile(s).get("group")}
    target_prof = get_profile(r.target)
    owner_group_note = ""
    if not target_prof.get("owner") and not target_prof.get("group"):
        first_prof = get_profile(r.sources[0])
        set_profile(r.target, owner=first_prof.get("owner", ""), group=first_prof.get("group", ""))
        if len(owners) > 1 or len(groups) > 1:
            owner_group_note = (f" UYARI: kaynaklar farklı sahip/grup değerlerine sahip ({owners}, {groups}) — "
                                 f"hedefe yalnızca ilk kaynağınki ({r.sources[0]}) kopyalandı, gerekirse elle düzeltin.")

    total_copied = 0
    collisions: dict[str, int] = {}   # kaynak -> atlanan (ID çakışan) nokta sayısı
    for s in r.sources:
        copied, skipped = _copy_all_points(s, r.target, skip_ids=existing_ids)
        total_copied += copied
        if skipped:
            collisions[s] = skipped
        # bir sonraki kaynak için hedefteki id kümesini güncelle — aynı id birden
        # fazla kaynakta varsa yalnızca İLKİ kopyalanır, tekrarlanan atlanır
        next_page = None
        while True:
            batch, next_page = cl.scroll(r.target, limit=10000, offset=next_page, with_payload=False, with_vectors=False)
            existing_ids.update(p.id for p in batch)
            if next_page is None:
                break
    collision_note = ""
    if collisions:
        collision_note = (f" UYARI: ID çakışması nedeniyle atlanan noktalar var: {collisions} — aynı göreli "
                          f"yol+imzaya sahip chunk'lar aynı ID'yi üretir; atlananlar hedefe KOPYALANMADI "
                          f"(ilk gelen kazandı). Kaynaklar silinmediği için veri kaybı yok, ama birleşik "
                          f"koleksiyonda bu parçalar tek kopya olarak temsil ediliyor.")
    return {"ok": True, "target": r.target, "points_copied": total_copied, "collisions": collisions,
            "owner_group_note": owner_group_note,
            "note": "Kaynak koleksiyonlar SİLİNMEDİ — istemiyorsanız Ayarlar'dan elle silin." + collision_note}

@router.get("/api/collection/export")
def collection_export(collection: str):
    if collection in INTERNAL_COLLS or not cl.collection_exists(collection):
        return JSONResponse({"error": f"koleksiyon yok: {collection}"}, status_code=404)
    return StreamingResponse(_gzip_iter(_export_line_iter(collection)), media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{collection}.jsonl.gz"'})

@router.post("/api/backup/run")
def backup_run(full: bool = True):
    if STATE.get("backup_job") and STATE["backup_job"].get("phase") == "running":
        return JSONResponse({"error": "zaten çalışan yedekleme var"}, status_code=409)
    STATE["backup_job"] = {"phase": "starting"}
    threading.Thread(target=_run_backup, args=(full,), daemon=True).start()
    return {"ok": True}

@router.get("/api/backup/status")
def backup_status():
    files = []
    if BACKUP_DIR.exists():
        for f in sorted(BACKUP_DIR.glob("*.jsonl.gz"), key=lambda f: f.stat().st_mtime, reverse=True):
            files.append({"name": f.name, "mb": round(f.stat().st_size / 1e6, 1),
                          "date": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")})
    return {"job": STATE.get("backup_job") or {"phase": "idle"}, "files": files[:30],
            "keep": BACKUP_KEEP, "auto_max_points": BACKUP_AUTO_MAX_POINTS}

@router.post("/api/collection/import")
async def collection_import(file: UploadFile = File(...), overwrite: bool = False):
    try:
        raw = gzip.decompress(await file.read())
    except Exception as e:
        return JSONResponse({"error": f"dosya gzip olarak açılamadı: {str(e)[:150]}"}, status_code=400)
    lines = [l for l in raw.decode("utf-8", "replace").splitlines() if l.strip()]
    if not lines:
        return JSONResponse({"error": "dosya boş"}, status_code=400)
    try:
        manifest = json.loads(lines[0])
    except Exception:
        return JSONResponse({"error": "ilk satır geçerli bir manifest değil"}, status_code=400)
    if not manifest.get("_manifest"):
        return JSONResponse({"error": "bu dosya Code-Intel export formatında değil (manifest yok)"}, status_code=400)
    collection = manifest["collection"]
    if collection in INTERNAL_COLLS:
        return JSONResponse({"error": "iç sistem koleksiyonu adı kullanılamaz"}, status_code=400)

    # ATOMİKLİK (Sıra 6): TÜM satırlar önce ayrıştırılıp DOĞRULANIR, mevcut
    # koleksiyona ancak dosyanın tamamı sağlamsa dokunulur. Eski akış overwrite'ta
    # önce siliyordu — bozuk/yarım bir dosya hem eskiyi silmiş hem yenisini eksik
    # bırakmış olurdu (dış analizde işaretlenen veri kaybı riski).
    parsed: list[models.PointStruct] = []
    try:
        for i, line in enumerate(lines[1:], start=2):
            row = json.loads(line)
            if "_default" in row["vector"]:
                vec = row["vector"]["_default"]   # adsız vektör: düz liste olarak geri yazılır
            else:
                vec = {}
                for k, val in row["vector"].items():
                    vec[k] = models.SparseVector(indices=val["indices"], values=val["values"]) if isinstance(val, dict) and val.get("_sparse") else val
            parsed.append(models.PointStruct(id=row["id"], vector=vec, payload=row["payload"]))
    except Exception as e:
        return JSONResponse({"error": f"satır {i} bozuk — mevcut koleksiyona DOKUNULMADI: {str(e)[:120]}"}, status_code=400)
    expected = manifest.get("points_count")
    if expected is not None and len(parsed) != expected:
        return JSONResponse({"error": f"satır sayısı manifest ile uyuşmuyor ({len(parsed)} != {expected}) — dosya kesik olabilir, mevcut koleksiyona DOKUNULMADI"}, status_code=400)

    if cl.collection_exists(collection):
        if not overwrite:
            return JSONResponse({"error": f'"{collection}" zaten var — üzerine yazmak için overwrite=true gönderin'}, status_code=409)
        cl.delete_collection(collection)

    if manifest.get("default_vector") and not manifest.get("dense_vectors"):
        # iç koleksiyon yedeği (adsız/size-1 vektör) — export '_default' anahtarıyla yazar
        dv = manifest["default_vector"]
        vectors_cfg = models.VectorParams(size=dv["size"], distance=models.Distance(dv["distance"]))
    else:
        vectors_cfg = {k: models.VectorParams(size=vc["size"], distance=models.Distance(vc["distance"]))
                       for k, vc in manifest.get("dense_vectors", {}).items()}
    sparse_names = manifest.get("sparse_vectors", [])
    sparse_cfg = {k: models.SparseVectorParams(modifier=models.Modifier.IDF) for k in sparse_names} if sparse_names else None
    cl.create_collection(collection, vectors_config=vectors_cfg, sparse_vectors_config=sparse_cfg)
    retrieval.ensure_payload_indexes(collection)

    B = 200; count = 0
    for i in range(0, len(parsed), B):
        b = parsed[i:i + B]
        cl.upsert(collection, points=b); count += len(b)

    if manifest.get("profile"):
        prof = {k: v for k, v in manifest["profile"].items() if k != "collection"}
        set_profile(collection, **prof)
    return {"ok": True, "collection": collection, "points": count}

# ---------------- ayarlar sayfası için zengin indeks özeti ----------------
def vector_state(collection: str, name: str, total: int) -> dict:
    if total == 0:
        return {"state": "none", "count": 0}
    n = cl.count(collection, count_filter=models.Filter(must=[models.HasVectorCondition(has_vector=name)])).count
    return {"state": "full" if n == total else ("partial" if n > 0 else "none"), "count": n}

@router.get("/api/indexes")
def indexes_get():
    try:
        hist_all = get_history()
        out = []
        for c in cl.get_collections().collections:
            if c.name in INTERNAL_COLLS:
                continue
            info = cl.get_collection(c.name)
            total = info.points_count
            v, sv = info.config.params.vectors, info.config.params.sparse_vectors
            has_dense_cfg = isinstance(v, dict) and "dense" in v
            has_sparse_cfg = isinstance(sv, dict) and "sparse" in sv
            prof = get_profile(c.name)
            hist = hist_all.get(c.name, [])
            latest = hist[0] if hist else {}
            path = prof.get("path") or latest.get("path", "")
            # ucuz doğrulama: yol diskte var mı; profildeki (elle girilmiş/son) yol son
            # GERÇEK reindex'te kullanılan yoldan farklı mı (reindex edilmemiş bir düzeltme mi)
            path_missing = bool(path) and not pathlib.Path(path).exists()
            path_pending = bool(prof.get("path")) and bool(latest.get("path")) and prof.get("path") != latest.get("path")
            out.append({
                "name": c.name,
                "version": prof.get("version", ""),
                # elle düzeltilmiş değer (profil) otomatik tespit edilenden ÖNCELİKLİ —
                # kullanıcı diski/klasörü taşıdığında reindex'e gerek kalmadan düzeltebilsin diye
                "language": prof.get("language") or latest.get("language", ""),
                "priority": prof.get("priority", 0),
                "owner": prof.get("owner", ""),
                "group": prof.get("group", ""),
                "kaynak": prof.get("kaynak", ""),
                "url": prof.get("url", ""),
                "auto_refresh": bool(prof.get("auto_refresh")),
                "patterns": prof.get("patterns", "*.pas"),
                "path": path,
                "path_missing": path_missing,   # yol şu an diskte yok
                "path_pending": path_pending,   # yol elle değiştirildi ama henüz bu yolla reindex edilmedi
                "points": total,
                "dense": vector_state(c.name, "dense", total) if has_dense_cfg else {"state": "n/a", "count": 0},
                "sparse": vector_state(c.name, "sparse", total) if has_sparse_cfg else {"state": "n/a", "count": 0},
                "last_indexed": latest.get("date"),
            })
        return {"indexes": out}
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=500)

# ---------------- yerel klasör seçim diyaloğu (aynı makinede çalıştığı için) ----------------
@router.get("/api/pick-folder")
def pick_folder():
    ps = ("Add-Type -AssemblyName System.Windows.Forms | Out-Null; "
          "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
          "$f.Description = 'Kaynak klasoru sec'; "
          "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                              capture_output=True, text=True, timeout=120)
        return {"path": out.stdout.strip()}
    except Exception as e:
        return {"path": "", "error": str(e)[:200]}

@router.get("/api/ollama/models")
def ollama_models():
    try:
        d = json.loads(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5).read())
        return {"models": [m["name"] for m in d.get("models", [])]}
    except Exception as e:
        return {"models": [], "error": str(e)[:120]}

# ---------------- donanım tarama + uyumlu Ollama modeli önerisi ----------------
def _ps(cmd: str, timeout: int = 15) -> str:
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                               capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""

@router.get("/api/hardware")
def hardware():
    out = {"cpu": "", "cores": 0, "ram_gb": 0.0, "gpu": "", "vram_gb": 0.0}
    out["cpu"] = _ps("(Get-CimInstance Win32_Processor).Name")
    try:
        out["cores"] = int(_ps("(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors") or 0)
    except ValueError:
        pass
    try:
        b = int(_ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory") or 0)
        out["ram_gb"] = round(b / (1024 ** 3), 1)
    except ValueError:
        pass
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            name, vram_mb = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
            out["gpu"], out["vram_gb"] = name, round(int(vram_mb) / 1024, 1)
    except Exception:
        pass
    if not out["gpu"]:
        out["gpu"] = _ps("(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name")
    return out

GEN_RE = re.compile(r"(\d+(?:\.\d+)?)")

def model_generation(tag: str) -> float:
    """Aile adındaki (etiketten ÖNCEKİ kısım — boyut değil) ilk sayı: qwen3-coder->3,
    qwen2.5-coder->2.5, deepseek-coder-v2->2, gemma4->4. Bulunamazsa 0 (bilinmiyor,
    en düşük öncelik, boyuta göre sıralanır)."""
    family = tag.split(":")[0]
    m = GEN_RE.search(family)
    return float(m.group(1)) if m else 0.0

@router.get("/api/hardware/suggest")
def hardware_suggest():
    hw = hardware()
    try:
        d = json.loads(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5).read())
        # Ollama'nın kendi bildirdiği GERÇEK boyut (byte) kullanılıyor — isimdeki "30b" gibi bir
        # rakamdan tahmin YOK: MoE modellerde bu tür isim-tabanlı tahminler yanıltıcı olabiliyor
        # (örn. qwen3-coder:30b adında "30" geçse de gerçek Q4_K_M dosyası 18.6GB).
        sized = [(m["name"], round(m.get("size", 0) / (1024 ** 3), 1)) for m in d.get("models", [])]
        sized = [(t, gb) for t, gb in sized if gb > 0]
    except Exception as e:
        return {"hardware": hw, "error": str(e)[:150]}
    if not sized:
        return {"hardware": hw, "fast": None, "deep": None, "reason": "Kurulu model bulunamadı."}

    vram = hw["vram_gb"]
    RESERVE_GB = 3.5     # embedding modeli + Qdrant + sistem için ayrılan pay
    budget = max(0.0, vram - RESERVE_GB)
    coder = [(t, gb) for t, gb in sized if "coder" in t.lower()]
    pool = coder or sized   # kodlamaya özel model yoksa genel modellerden seç

    # boyut TEK BAŞINA kalite göstergesi değil (örn. qwen2.5-coder:32b dosyası qwen3-coder:30b'den
    # büyük ama qwen3 daha yeni/güçlü nesil) — önce aynı ailenin en yeni nesli, sonra o nesil
    # içinde boyut kıyaslanıyor.
    by_gen_size = sorted(pool, key=lambda tg: (model_generation(tg[0]), tg[1]), reverse=True)
    top_gen = model_generation(by_gen_size[0][0])
    top_tier = [(t, gb) for t, gb in pool if model_generation(t) == top_gen]

    # derin: en yeni nesildeki en büyük model. VRAM'e tam sığmasa da olur (zaten 30-40sn
    # bekleniyor, Ollama gerekirse kısmen CPU'ya taşırır; sığmayınca sadece yavaşlar).
    deep = max(top_tier, key=lambda tg: tg[1])[0]
    deep_gb = dict(sized)[deep]

    # hızlı: en yeni nesilden VRAM'e sığan en küçük model; o nesilde hiçbiri sığmıyorsa
    # bir alt nesle düş — hâlâ yoksa kurulu en küçük modele düş (hız önceliği, sık çağrılıyor).
    fast = None
    for gen in sorted({model_generation(t) for t, _ in pool}, reverse=True):
        tier_fits = [(t, gb) for t, gb in pool if model_generation(t) == gen and gb <= budget]
        if tier_fits:
            fast = min(tier_fits, key=lambda tg: tg[1])[0]
            break
    if fast is None:
        fast = min(sized, key=lambda tg: tg[1])[0]

    fits_note = "VRAM'e tam sığıyor." if deep_gb <= budget else f"VRAM'e tam sığmıyor (~{deep_gb}GB > ~{budget:.1f}GB bütçe) — kısmen CPU'ya taşabilir, yavaş ama çalışır."
    reason = (f"GPU: {hw['gpu']} (~{vram}GB VRAM, ~{budget:.1f}GB kullanılabilir bütçe, {RESERVE_GB}GB rezerv). "
               f"Kodlamaya özel modeller önceliklendirildi{'' if coder else ' (kurulu böyle bir model bulunamadı, genel modellerden seçildi)'}, "
               f"aralarında en yeni nesil (v{top_gen:g}) tercih edildi. "
               f"Hızlı: o nesilden sığan en küçük model. Derin: o nesildeki en büyük model — {fits_note}")
    return {"hardware": hw, "fast": fast, "deep": deep, "reason": reason,
            "sized": [{"model": t, "gb": gb, "coder": "coder" in t.lower(), "gen": model_generation(t)}
                      for t, gb in sorted(sized, key=lambda tg: -tg[1])]}

@router.get("/")
def index_page():
    return FileResponse(ROOT / "static" / "index.html")

@router.get("/settings")
def settings_page():
    return FileResponse(ROOT / "static" / "settings.html")

@router.get("/api")
def api_page():
    return FileResponse(ROOT / "static" / "api.html")

@router.get("/viewer")
def viewer_page():
    return FileResponse(ROOT / "static" / "viewer.html")

# ---------------- kayıtlı çalışma alanları (workspace) ----------------
# Arama tercihleri paketi (koleksiyon seçimi, mod, filtreler, rerank, gruplama)
# sunucuda saklanır — tarayıcı localStorage'ına hapsolmaz, farklı tarayıcı/makine
# aynı çalışma alanlarını görür (birleşik analiz #6 önerisi, tek-kullanıcı sürümü).
import uuid as _uuid

class WorkspaceReq(BaseModel):
    name: str
    config: dict   # {collections, mode, kind, unit, rerank, group, ...} — UI ne verirse

def _ws_id(name: str) -> str:
    return str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"ws|{name}"))

def _ensure_ws_coll():
    WC = retrieval.WORKSPACE_COLL
    if not cl.collection_exists(WC):
        cl.create_collection(WC, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))
    return WC

@router.get("/api/workspaces")
def workspaces_list():
    WC = retrieval.WORKSPACE_COLL
    if not cl.collection_exists(WC):
        return {"workspaces": []}
    pts, _ = cl.scroll(WC, limit=200, with_payload=True)
    return {"workspaces": sorted(({"name": p.payload.get("name"), "config": p.payload.get("config", {}),
                                    "date": p.payload.get("date")} for p in pts), key=lambda w: w["name"] or "")}

@router.post("/api/workspaces")
def workspaces_save(r: WorkspaceReq):
    if not r.name.strip():
        return JSONResponse({"error": "ad boş olamaz"}, status_code=400)
    WC = _ensure_ws_coll()
    cl.upsert(WC, points=[models.PointStruct(id=_ws_id(r.name.strip()), vector=[0.0],
        payload={"name": r.name.strip(), "config": r.config,
                 "date": datetime.now().isoformat(timespec="seconds")})])
    return {"ok": True}

@router.delete("/api/workspaces")
def workspaces_delete(name: str):
    WC = retrieval.WORKSPACE_COLL
    if cl.collection_exists(WC):
        cl.delete(WC, points_selector=models.PointIdsList(points=[_ws_id(name.strip())]))
    return {"ok": True}

# ---------------- owner / group kayıt defterleri (Owner→Collection modeli) ----------------
# GitHub'daki owner/repo, bir firmanın Vendor→Ürün modeliyle aynı şekle iniyor: Owner (kim
# yayınlıyor) + Group (fonksiyonel/konu etiketi, owner'dan bağımsız çapraz-kesen — "REST
# Library", "Şifreleme" gibi). Koleksiyon profilindeki owner/group alanları DÜZ METİN kalır
# (şema değişmedi) — bu defterler yalnızca Ayarlar'daki açılır listeyi besleyen KAYNAKTIR,
# foreign-key zorlaması yok (bir kayıt silinse bile onu zaten kullanmış koleksiyonlar bozulmaz).
class OwnerReq(BaseModel):
    name: str; url: str | None = None; note: str | None = None

class GroupReq(BaseModel):
    name: str; description: str | None = None

@router.get("/api/owners")
def owners_list():
    return {"owners": list_owners()}

@router.post("/api/owners")
def owners_save(r: OwnerReq):
    try:
        return {"ok": True, "owner": upsert_owner(r.name, r.url, r.note)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@router.delete("/api/owners")
def owners_delete(name: str):
    delete_owner(name)
    return {"ok": True}

@router.get("/api/groups")
def groups_list():
    return {"groups": list_groups()}

@router.post("/api/groups")
def groups_save(r: GroupReq):
    try:
        return {"ok": True, "group": upsert_group(r.name, r.description)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@router.delete("/api/groups")
def groups_delete(name: str):
    delete_group(name)
    return {"ok": True}

_VIEWABLE_EXT = {".md": "md", ".markdown": "md", ".html": "html", ".htm": "html", ".txt": "text"}

def _view_roots() -> list[pathlib.Path]:
    """view-file'ın okumasına İZİN VERİLEN kökler: proje kökü (raporlar burada)
    + kayıtlı koleksiyon kaynak klasörleri. Bunların dışı 403 — eskiden uç
    HERHANGİ bir mutlak yolu okuyabiliyordu (dış analizde işaretlenen path
    traversal açığı: ör. tarayıcıdan ?path=C:\\Users\\...\\gizli.txt)."""
    roots = [ROOT.resolve()]
    try:
        if cl.collection_exists(PROFILE_COLL):
            pts, _ = cl.scroll(PROFILE_COLL, limit=500, with_payload=["path"])
            for p in pts:
                src = p.payload.get("path")
                if src:
                    try:
                        roots.append(pathlib.Path(src).resolve())
                    except OSError:
                        pass
    except Exception:
        pass
    return roots

@router.get("/api/view-file")
def view_file(path: str):
    p = pathlib.Path(path)
    ext = p.suffix.lower()
    if ext not in _VIEWABLE_EXT:
        return JSONResponse({"error": f"desteklenmeyen dosya türü: {ext or '(uzantısız)'} — sadece .md/.html/.txt"}, status_code=400)
    try:
        rp = p.resolve()
    except OSError:
        return JSONResponse({"error": "geçersiz yol"}, status_code=400)
    if not any(rp.is_relative_to(root) for root in _view_roots()):
        return JSONResponse({"error": "bu yol izinli kökler dışında — yalnızca proje klasörü ve kayıtlı kaynak klasörler görüntülenebilir"}, status_code=403)
    if not p.exists() or not p.is_file():
        return JSONResponse({"error": f"dosya bulunamadı: {path}"}, status_code=404)
    if p.stat().st_size > 3_000_000:
        return JSONResponse({"error": "dosya çok büyük (>3MB) — panelde önizleme için değil"}, status_code=400)
    return {"content": p.read_text(encoding="utf-8", errors="replace"), "type": _VIEWABLE_EXT[ext], "name": p.name}

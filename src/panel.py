"""Code-Intel Yönetim Paneli — uygulama MONTAJI (modüler monolit, Sıra 2).
Çalıştır:  python -m uvicorn src.panel:app --port 8500  (sistemde kurulu Python; .venv KULLANMAYIN — bkz. CONTRIBUTING.md "Antivirüs uyarıları")

Yapı (birleşik analiz kararı — mikroservis DEĞİL, tek süreçte modüler monolit):
  services/common.py          ortak sabitler + paylaşılan STATE
  services/profiles.py        profil + tarihçe (_index_profiles/_index_history)
  services/collections_svc.py kopyalama, akışlı export, yedekleme
  services/indexing_svc.py    chunk→diff→embed hattı, çağrı grafiği, watcher, dup tarama
  api/admin_routes.py         sağlık, koleksiyon CRUD, import/export, donanım, sayfalar
  api/search_routes.py        arama, açıklama, ilişkiler, RAG sohbet (SSE), geri bildirim, analitik
  api/index_routes.py         indeksleme, kopya-kod, sembol rebuild, etki analizi
  api/mcp_routes.py           13 MCP tool'unun REST test uçları
Arama çekirdeği retrieval.py'de (panel + MCP ortak). Davranış sözleşmesi
tests/test_api.py ile korunur — rota taşınabilir, yol/format değişmez.
"""
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

import onnxruntime as ort
ort.preload_dlls()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

try:
    from . import retrieval
    from .services import common
    from .services.indexing_svc import _watch_loop, _run_index, load_pending_job
    from .services.apikeys import validate_api_key
    from .api import admin_routes, index_routes, mcp_routes, search_routes, manual_routes
except ImportError:
    # `uvicorn src.panel:app` paket-göreli çalışır; `python src/panel.py` (paketsiz) düşülür.
    import retrieval
    from services import common
    from services.indexing_svc import _watch_loop, _run_index, load_pending_job
    from services.apikeys import validate_api_key
    from api import admin_routes, index_routes, mcp_routes, search_routes, manual_routes

# Geriye dönük takma adlar — testler ve dış kullanıcılar panel.X olarak erişebilir.
ROOT = common.ROOT
QDRANT, OLLAMA = common.QDRANT, common.OLLAMA
HISTORY_COLL, PROFILE_COLL = common.HISTORY_COLL, common.PROFILE_COLL
SEARCH_LOG_COLL, SYMBOL_COLL = common.SEARCH_LOG_COLL, common.SYMBOL_COLL
INTERNAL_COLLS = common.INTERNAL_COLLS
STATE = common.STATE
cl = common.cl

app = FastAPI(title="Code-Intel Panel")

# ---------------- güvenlik sınırı (Sıra 4 + Sıra 11a rol ayrımı) ----------------
# Katmanlar:
#  1) API-key: CODEINTEL_API_KEY ayarlıysa, localhost dışından TÜM /api/* için zorunlu.
#     Sunulan anahtar ya bu tek "üstün" ortam-değişkeni anahtarıyla (rol=admin, geriye
#     dönük uyum) ya da Ayarlar'dan üretilen ROL'LÜ bir kayıt-defteri anahtarıyla eşleşmeli.
#  2) Admin kilidi: yönetim uçları (ADMIN_PREFIXES) localhost dışından ancak rol=admin
#     bir anahtarla açılır — CODEINTEL_API_KEY hiç ayarlanmamışsa bile Ayarlar'dan
#     üretilmiş bir admin-rollü anahtarla uzaktan yönetim artık mümkün (eskiden tamamen
#     kapalıydı). "read" rollü bir anahtarla admin uca gidilirse 403.
#  3) Rate limit: kaba, bellek-içi kayan pencere (istemci başına 300 istek/10 sn) —
#     kaçak döngülere/istek fırtınasına fren; normal panel kullanımına görünmez.
#  4) Audit log: yönetim uçlarına yazma istekleri logs\admin-audit.log'a satır satır
#     (kullanılan anahtarın adı biliniyorsa onunla birlikte).
# "testclient" starlette TestClient'ın sabit in-process işaretidir — gerçek ağ
# istemcisi bu değeri taşıyamaz (socket'ten gelir), test paketi yerel sayılır.
API_KEY = os.environ.get("CODEINTEL_API_KEY", "")
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
ADMIN_PREFIXES = ("/api/collection", "/api/index/start", "/api/backup/run",
                   "/api/duplicates/start", "/api/symbols/rebuild", "/api/profile",
                   "/api/owners", "/api/groups", "/api/apikeys", "/api/git-update-all",
                   "/api/index/migrate-ids", "/api/manual/build", "/api/manual/translate")
RATE_WINDOW_SEC, RATE_MAX = 10, 300
_rate: dict[str, deque] = {}
_AUDIT_FILE = common.ROOT / "logs" / "admin-audit.log"

def _audit(host: str, method: str, path: str, key_name: str = ""):
    try:
        _AUDIT_FILE.parent.mkdir(exist_ok=True)
        with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "ip": host,
                                 "method": method, "path": path, "key": key_name}, ensure_ascii=False) + "\n")
    except Exception:
        pass   # audit hatası isteği asla düşürmez

def _presented_key_role(raw: str | None) -> tuple[str | None, str]:
    """(rol, anahtar_adı) döndürür. Eşleşme yoksa (None, '')."""
    if not raw:
        return None, ""
    if API_KEY and raw == API_KEY:
        return "admin", "CODEINTEL_API_KEY (ortam değişkeni)"
    rec = validate_api_key(raw)
    return (rec["role"], rec["name"]) if rec else (None, "")

@app.middleware("http")
async def security_guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        host = request.client.host if request.client else ""
        now = time.time()
        dq = _rate.setdefault(host, deque())
        while dq and now - dq[0] > RATE_WINDOW_SEC:
            dq.popleft()
        if len(dq) >= RATE_MAX:
            return JSONResponse({"error": "çok fazla istek — kısa bir süre bekleyin"}, status_code=429)
        dq.append(now)
        is_local = host in LOCAL_HOSTS
        role, key_name = (None, "") if is_local else _presented_key_role(request.headers.get("x-api-key"))
        if API_KEY and not is_local and role is None:
            return JSONResponse({"error": "geçersiz veya eksik X-API-Key"}, status_code=401)
        # Dış analizde bulunan gerçek SSRF: /api/ask, /api/research/stream, /api/compare
        # istemciden bir ollama_url alıp sunucu tarafında ona istek atıyordu — "read"
        # rollü uzak bir anahtar bile sunucuyu keyfi bir iç ağ adresine yönlendirebilirdi.
        # Bu bayrak (search_routes.py'de okunur) o alanı yalnız localhost'tan veya
        # rol=admin bir anahtarla gelen isteklerde geçerli sayar; diğerlerinde sunucu
        # kendi varsayılan Ollama adresini kullanır.
        request.state.trusted_client = is_local or role == "admin"
        is_admin = any(path.startswith(p) for p in ADMIN_PREFIXES)
        if is_admin and not is_local and role != "admin":
            return JSONResponse({"error": "yönetim uçları yalnız localhost'tan veya rol=admin bir API anahtarıyla erişilebilir "
                                           "(Ayarlar'dan üretin veya CODEINTEL_API_KEY tanımlayın)"}, status_code=403)
        if is_admin and request.method in ("POST", "DELETE", "PUT"):
            _audit(host, request.method, path, key_name)
    return await call_next(request)

app.include_router(admin_routes.router)
app.include_router(search_routes.router)
app.include_router(index_routes.router)
app.include_router(mcp_routes.router)
app.include_router(manual_routes.router)

# Statik varlıklar (ör. yerelde barındırılan SweetAlert2) — proje CDN'siz/çevrimdışı
# çalışma ilkesine bağlı (bkz. Help/Manual sistemindeki aynı karar), bu yüzden
# harici bir <script src="https://..."> yerine dosya diskten sunulur.
from fastapi.staticfiles import StaticFiles
app.mount("/static/vendor", StaticFiles(directory=str(ROOT / "static" / "vendor")), name="vendor")

LOG_ROTATE_BYTES = 20_000_000   # log dosyası bu boyutu aşınca .1'e devredilir (1 eski kopya tutulur)

def _rotate_logs():
    try:
        for f in (ROOT / "logs").glob("*.log"):
            if f.stat().st_size > LOG_ROTATE_BYTES:
                old = f.with_suffix(f.suffix + ".1")
                old.unlink(missing_ok=True)
                f.rename(old)
    except Exception:
        pass

@app.on_event("startup")
def _startup():
    _rotate_logs()
    # payload index'leri geriye dönük tamamla (idempotent, eski koleksiyonlar için migrasyon)
    try:
        for c in cl.get_collections().collections:
            if c.name not in INTERNAL_COLLS:
                retrieval.ensure_payload_indexes(c.name)
    except Exception:
        pass
    threading.Thread(target=_watch_loop, daemon=True).start()
    # Sıra 26: kalıcı iş kaydı — panel bir önceki çalıştırmada indeksleme
    # ORTASINDA sert şekilde kesildiyse (kill/çökme, normal bitiş/hata YOLU hiç
    # işlemediyse) _index_jobs'ta bir kayıt kalmış olur. Aynı isteği burada
    # yeniden tetiklemek "devam etmek" anlamına gelir — indeksleme zaten hash
    # bazlı diff'li, değişmeyen noktalar otomatik atlanır (bkz. indexing_svc
    # docstring'i). Normal (başarı/hata) bitişlerde kayıt zaten silinmiş olur.
    try:
        pending = load_pending_job()
        if pending and not (STATE.get("index_job") and STATE["index_job"].get("phase") in
                             ("starting", "chunking", "diffing", "embedding", "linking")):
            STATE["index_job"] = {"collection": pending.collection, "mode": "+".join(pending.vectors),
                                  "device": pending.device, "total": 0, "done": 0, "rate": 0,
                                  "phase": "starting", "resumed": True}
            threading.Thread(target=_run_index, args=(pending,), daemon=True).start()
    except Exception:
        pass

"""Code-Intel Yönetim Paneli — uygulama MONTAJI (modüler monolit, Sıra 2).
Çalıştır:  .venv/Scripts/python.exe -m uvicorn src.panel:app --port 8500

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
import os
import threading

import onnxruntime as ort
ort.preload_dlls()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

try:
    from . import retrieval
    from .services import common
    from .services.indexing_svc import _watch_loop
    from .api import admin_routes, index_routes, mcp_routes, search_routes
except ImportError:
    # `uvicorn src.panel:app` paket-göreli çalışır; `python src/panel.py` (paketsiz) düşülür.
    import retrieval
    from services import common
    from services.indexing_svc import _watch_loop
    from api import admin_routes, index_routes, mcp_routes, search_routes

# Geriye dönük takma adlar — testler ve dış kullanıcılar panel.X olarak erişebilir.
ROOT = common.ROOT
QDRANT, OLLAMA = common.QDRANT, common.OLLAMA
HISTORY_COLL, PROFILE_COLL = common.HISTORY_COLL, common.PROFILE_COLL
SEARCH_LOG_COLL, SYMBOL_COLL = common.SEARCH_LOG_COLL, common.SYMBOL_COLL
INTERNAL_COLLS = common.INTERNAL_COLLS
STATE = common.STATE
cl = common.cl

app = FastAPI(title="Code-Intel Panel")

# ---------------- opsiyonel API-key katmanı ----------------
# CODEINTEL_API_KEY ortam değişkeni AYARLIYSA, localhost DIŞINDAN gelen tüm /api/*
# istekleri X-API-Key başlığı ister. Localhost muaf — panelin kendi tarayıcı
# arayüzü anahtar bilmeden çalışmaya devam eder; katman yalnızca panel ağa
# açıldığında (örn. LAN'daki başka bir makineden) devreye girer.
API_KEY = os.environ.get("CODEINTEL_API_KEY", "")

@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    if API_KEY and request.url.path.startswith("/api/"):
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost") and request.headers.get("x-api-key") != API_KEY:
            return JSONResponse({"error": "geçersiz veya eksik X-API-Key"}, status_code=401)
    return await call_next(request)

app.include_router(admin_routes.router)
app.include_router(search_routes.router)
app.include_router(index_routes.router)
app.include_router(mcp_routes.router)

@app.on_event("startup")
def _startup():
    # payload index'leri geriye dönük tamamla (idempotent, eski koleksiyonlar için migrasyon)
    try:
        for c in cl.get_collections().collections:
            if c.name not in INTERNAL_COLLS:
                retrieval.ensure_payload_indexes(c.name)
    except Exception:
        pass
    threading.Thread(target=_watch_loop, daemon=True).start()

"""Ortak sabitler + paylaşılan süreç durumu — modüler monolitin çekirdeği.
Tüm servis ve rota modülleri AYNI STATE sözlüğünü ve sabitleri buradan alır
(Sıra 2 modülerleşmesi: panel.py 1500 satırlık monolitten bölündü, davranış
tests/test_api.py sözleşme testleriyle korunuyor)."""
import pathlib
import threading

try:
    from .. import retrieval
except ImportError:
    import retrieval

cl = retrieval.cl
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
QDRANT, OLLAMA = retrieval.QDRANT, retrieval.OLLAMA
HISTORY_COLL = "_index_history"    # indeksleme geçmişi
PROFILE_COLL = "_index_profiles"   # koleksiyon başına TEK nokta (kullanıcı alanları)
SEARCH_LOG_COLL = retrieval.SEARCH_LOG_COLL
SYMBOL_COLL = retrieval.SYMBOL_COLL
WORKSPACE_COLL = retrieval.WORKSPACE_COLL
UNITDOC_COLL = retrieval.UNITDOC_COLL
ANSWER_COLL = retrieval.ANSWER_COLL
OWNER_COLL = retrieval.OWNER_COLL
GROUP_COLL = retrieval.GROUP_COLL
APIKEY_COLL = retrieval.APIKEY_COLL
JOB_COLL = retrieval.JOB_COLL
INTERNAL_COLLS = retrieval.INTERNAL_COLLS   # TEK kaynak: retrieval.py (kopya liste kaymasın)
STATE = {"index_job": None}   # TEK paylaşılan iş durumu — tüm modüller aynı dict'i günceller
# 4. tur — dış analizde (Codex, 2026-07-25) bulunan HATALI/Yüksek bulgu: iş
# başlatma uçları (index/start, duplicates/start, git-update-all) STATE
# üzerinde "kontrol et sonra ata" (check-then-set) yapıyordu, KİLİTSİZ.
# FastAPI'nin düz `def` rotaları Starlette'in threadpool'unda GERÇEKTEN
# paralel çalışır (async cooperative scheduling değil) — iki eşzamanlı istek
# ikisi de kontrolü GEÇİP ikisi de kendi arka plan thread'ini başlatabilirdi
# (aynı koleksiyona karşı iki eşzamanlı chunk/embed/upsert döngüsü — veri
# bozulması riski). STATE_LOCK bu kontrol+atama'yı TEK atomik adım yapar.
STATE_LOCK = threading.Lock()
WATCH_INTERVAL_SEC = 600      # auto_refresh kaynak tarama aralığı

# ---------------- uzak istemci dosya senkronu (ayna klasörler) ----------------
# bkz. api/remote_routes.py — her client_id kendi alt klasörüne yazar, bir
# koleksiyon profilinin `path`i buraya işaret edip auto_refresh=true olursa
# mevcut _watch_loop (indexing_svc.py) mtime değişikliğini görüp otomatik
# artımlı yeniden-indeksleme tetikler.
REMOTE_MIRROR_DIR = ROOT / "data" / "remote_mirrors"

# ---------------- otomatik/elle yedekleme (rotasyonlu) ----------------
BACKUP_DIR = ROOT / "backups"
BACKUP_KEEP = 3                 # koleksiyon başına saklanan yedek sayısı
BACKUP_INTERVAL_SEC = 24 * 3600
BACKUP_AUTO_MAX_POINTS = 50_000  # otomatik TAM yedek üst sınırı — daha büyük koleksiyonlar
                                 # (örn. 375K'lık Jedi, vektörlerle GB'larca dosya) sessizce
                                 # diski doldurmasın diye yalnız ELLE yedeklenir

# uzantı -> dil etiketi (gerçek ayrıştırma DEĞİL — sadece klasördeki dosyaları etiketlemek için;
# şu an chunker sadece .pas dosyalarını gerçekten ayrıştırıyor)
LANG_EXT = {
    ".pas": "Pascal/Delphi", ".dpr": "Pascal/Delphi", ".dpk": "Pascal/Delphi", ".inc": "Pascal/Delphi",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".h": "C/C++", ".hpp": "C++",
    ".c": "C", ".cs": "C#", ".java": "Java", ".py": "Python",
    ".js": "JavaScript", ".ts": "TypeScript", ".go": "Go", ".rs": "Rust",
}

def detect_language(path: str) -> str:
    counts: dict[str, int] = {}
    try:
        for p in pathlib.Path(path).rglob("*"):
            if p.is_file():
                lang = LANG_EXT.get(p.suffix.lower())
                if lang:
                    counts[lang] = counts.get(lang, 0) + 1
    except Exception:
        return "Bilinmiyor"
    if not counts:
        return "Bilinmiyor"
    total = sum(counts.values())
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:2]
    return ", ".join(f"{lang} (%{round(100*n/total)})" for lang, n in top)

"""CodeIntel uzak istemci: yerel bir klasoru izler, degisen/silinen/tasinan
dosyalari sunucudaki /api/remote-mirror/{client_id}/... uclarina gonderir.

Sunucu bu dosyalari bir "ayna" klasore yazar; auto_refresh acik bir koleksiyon
profili o klasoru gosteriyorsa, sunucunun MEVCUT watcher'i (indexing_svc.py)
degisikligi goruip otomatik artimli yeniden-indeksleme yapar (chunk->diff->
embed->upsert, sadece degisen chunk'lar). Bu script'in tek isi degisen
dosyalari HTTP ile sunucuya tasimak - indeksleme mantigi sunucuda, hic
degismedi.

Calistirma:
    python watch_client.py --config config.json
Ya da (build.ps1 ile derlenmis .exe):
    watch_client.exe --config config.json
"""
import argparse
import base64
import fnmatch
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def _post(server_url: str, api_key: str, path: str, body: dict) -> bool:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        server_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", "replace")
        print(f"[HATA] {path}: HTTP {e.code} - {body_txt}", file=sys.stderr)
    except Exception as e:
        print(f"[HATA] {path}: {e}", file=sys.stderr)
    return False


def _matches(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


class SyncHandler(FileSystemEventHandler):
    def __init__(self, cfg: dict, watch_root: pathlib.Path, patterns: list[str]):
        self.cfg = cfg
        self.watch_root = watch_root
        self.patterns = patterns

    def _rel(self, abs_path: str) -> str | None:
        try:
            return pathlib.Path(abs_path).resolve().relative_to(self.watch_root).as_posix()
        except ValueError:
            return None   # izlenen kokun disinda bir olay (olmamali, guvenlik icin yine de atla)

    def _upload(self, abs_path: str):
        p = pathlib.Path(abs_path)
        if p.is_dir() or not _matches(p.name, self.patterns):
            return
        rel = self._rel(abs_path)
        if rel is None:
            return
        try:
            content = p.read_bytes()
        except OSError:
            return   # dosya cok kisa surede silinmis/kilitli olabilir - bir sonraki olayda tekrar denenir
        b64 = base64.b64encode(content).decode("ascii")
        ok = _post(self.cfg["server_url"], self.cfg["api_key"],
                   f"/api/remote-mirror/{self.cfg['client_id']}/file",
                   {"relative_path": rel, "content_b64": b64})
        print(f"[{'YUKLENDI' if ok else 'BASARISIZ'}] {rel}")

    def on_created(self, event):
        if not event.is_directory:
            self._upload(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._upload(event.src_path)

    def on_deleted(self, event):
        if event.is_directory or not _matches(pathlib.Path(event.src_path).name, self.patterns):
            return
        rel = self._rel(event.src_path)
        if rel is None:
            return
        ok = _post(self.cfg["server_url"], self.cfg["api_key"],
                   f"/api/remote-mirror/{self.cfg['client_id']}/delete",
                   {"relative_path": rel})
        print(f"[{'SILINDI' if ok else 'BASARISIZ'}] {rel}")

    def on_moved(self, event):
        if event.is_directory:
            return
        old_matches = _matches(pathlib.Path(event.src_path).name, self.patterns)
        new_matches = _matches(pathlib.Path(event.dest_path).name, self.patterns)
        old_rel = self._rel(event.src_path)
        new_rel = self._rel(event.dest_path)
        if old_matches and new_matches and old_rel and new_rel:
            ok = _post(self.cfg["server_url"], self.cfg["api_key"],
                       f"/api/remote-mirror/{self.cfg['client_id']}/move",
                       {"old_relative_path": old_rel, "new_relative_path": new_rel})
            print(f"[{'TASINDI' if ok else 'BASARISIZ'}] {old_rel} -> {new_rel}")
        elif old_matches and old_rel:
            # yeni ad desene uymuyor (orn. .pas -> .bak) - eski konumu sil
            self.on_deleted(event)
        elif new_matches:
            # eski ad desene uymuyordu, yenisi uyuyor - yeni dosya gibi yukle
            self._upload(event.dest_path)


def initial_sync(cfg: dict, watch_root: pathlib.Path, patterns: list[str]):
    print("[BASLANGIC] ilk toplu senkron basliyor...")
    count = 0
    seen: set[pathlib.Path] = set()
    for pat in patterns:
        for f in watch_root.rglob(pat):
            if not f.is_file() or f in seen:
                continue
            seen.add(f)
            rel = f.resolve().relative_to(watch_root).as_posix()
            try:
                content = f.read_bytes()
            except OSError:
                continue
            b64 = base64.b64encode(content).decode("ascii")
            if _post(cfg["server_url"], cfg["api_key"],
                     f"/api/remote-mirror/{cfg['client_id']}/file",
                     {"relative_path": rel, "content_b64": b64}):
                count += 1
    print(f"[BASLANGIC] {count} dosya yuklendi.")


def main():
    ap = argparse.ArgumentParser(description="CodeIntel uzak istemci dosya senkronu")
    ap.add_argument("--config", default="config.json", help="config.json dosya yolu")
    args = ap.parse_args()

    cfg_path = pathlib.Path(args.config)
    if not cfg_path.exists():
        print(f"[HATA] config dosyasi yok: {cfg_path} (bkz. config.example.json)", file=sys.stderr)
        sys.exit(1)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    for req_key in ("server_url", "client_id", "api_key", "watch_path"):
        if not cfg.get(req_key):
            print(f"[HATA] config.json'da '{req_key}' eksik/bos", file=sys.stderr)
            sys.exit(1)

    watch_root = pathlib.Path(cfg["watch_path"]).resolve()
    patterns = cfg.get("patterns", ["*.pas"])
    if isinstance(patterns, str):
        patterns = [p.strip() for p in patterns.split(",") if p.strip()]

    if not watch_root.is_dir():
        print(f"[HATA] izlenecek klasor yok: {watch_root}", file=sys.stderr)
        sys.exit(1)

    if cfg.get("initial_sync", True):
        initial_sync(cfg, watch_root, patterns)

    handler = SyncHandler(cfg, watch_root, patterns)
    observer = Observer()
    observer.schedule(handler, str(watch_root), recursive=True)
    observer.start()
    print(f"[IZLENIYOR] {watch_root} -> {cfg['server_url']} (client_id={cfg['client_id']}, "
          f"desenler={','.join(patterns)})")
    print("Durdurmak icin Ctrl+C.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[DURDURULUYOR]")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()

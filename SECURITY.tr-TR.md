# Güvenlik Politikası

## Desteklenen Sürümler

CodeIntel yerel olarak çalışan bir araçtır (tek bir FastAPI süreci + Qdrant + Ollama), henüz resmi bir sürüm hattı yok. Şu an için destekleyip düzelttiğimiz:

| Sürüm | Destekleniyor mu |
| ------- | ------------------ |
| En güncel (`main`) | :white_check_mark: |
| Eski etiketler | :x: |

## Tehdit Modeli (bildirim yapmadan önce okuyun)

CodeIntel varsayılan olarak yalnız `127.0.0.1`'e bağlanır ve localhost'u tamamen güvenilir sayar. İsteğe bağlı olarak LAN'a açılabilir (Ayarlar → API Anahtarları, rol ayrımlı `read`/`admin` anahtarlar) — MCP erişimi için başka bir makineden — aşağıdakiler yalnız bu modda, aracı çalıştıran operatörden başkası için önem taşır:

- **Yönetim uçları** (`/api/collection/*`, `/api/index/start`, `/api/duplicates/start`, `/api/backup/run`, `/api/symbols/rebuild`, `/api/profile`, `/api/owners`, `/api/groups`, `/api/apikeys`, `/api/git-update-all`, `/api/index/migrate-ids`, `/api/manual/build`, `/api/manual/translate`) yerel-olmayan bir çağırandan `role=admin` veya `localhost` gerektirir.
- **Sohbet uçları** (`/api/ask`, `/api/ask/stream`, `/api/research/stream`, `/api/compare`) isteğe bağlı bir `ollama_url` geçersiz kılma alanı kabul eder, ama yalnız `localhost` veya `role=admin` çağıranlarda dikkate alınır — "read" rollü uzak bir anahtar sunucunun giden LLM çağrılarını yönlendiremez (2026-07-25'te, dış bir güvenlik incelemesinin bunun önceden sınırsız olduğunu bulmasının ardından düzeltildi — bkz. `git log --grep=SSRF`).
- Hız sınırlama (istemci başına 10 sn'de 300 istek) ve bir yönetim yazma audit log'u (`logs/admin-audit.log`) tüm yerel-olmayan trafiğe uygulanır.

Tek-operatörlü yerel bir araç için kabul edilen bilinen sınırlamalar (tek başlarına güvenlik açığı sayılmaz): LAN dinleyicisinde TLS yok, CSRF token'ı yok (bunun yerine aynı-köken API-key modeli), koleksiyon içe aktarma yüklenenin gzip/JSONL içeriğine, açıldıktan sonra günlüklenen boyut sınırları içinde güvenir.

## Bir Güvenlik Açığı Bildirme

Yukarıdaki rol/localhost kontrolünü atlayan bir uç, bir path traversal, bir enjeksiyon (SQL/komut/prompt), arama/ayarlar/manual arayüzünde saklı bir XSS, veya sunucunun istenmeyen bir giden istek yapmasını sağlayan bir yol (SSRF) bulursanız, lütfen **[FILL IN: repo URL]/issues** üzerinden `security` etiketiyle, ya da konu henüz herkese açık olmamalıysa özel olarak **baspinar99@gmail.com veya emr.pov@gmail.com** adresinden bildirin.

Lütfen şunları ekleyin:

* Açığın açıklaması.
* Bir kanıt (proof of concept) veya tekrar üretme adımları.
* Olası etki.

Bildiriminizi 48 saat içinde onaylayıp, uygulanabilirse bir düzeltme takvimi paylaşacağız.

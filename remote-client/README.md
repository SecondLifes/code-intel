# CodeIntel Uzak İstemci

Bir kod klasörünü **başka bir makinede** çalışan bir CodeIntel sunucusuna
canlı olarak senkronize eder — GPU'suz/zayıf bir makinede geliştirip, ağır
indeksleme işini (embedding) GPU'lu bir sunucuya bırakmak için.

## Nasıl çalışır

```
[bu makine]                              [GPU'lu sunucu]
kod klasörünüz                           CodeIntel panel
   │  watchdog izler                     ├─ /api/remote-mirror/{id}/... (yeni)
   └──── değişen dosya ──HTTP──POST─────►│
                                          ▼
                                  data/remote_mirrors/{id}/  (ayna klasör)
                                          │
                                          ▼
                          sunucunun MEVCUT auto_refresh watcher'ı
                          mtime değişikliğini görür, otomatik artımlı
                          yeniden-indeksleme yapar (GPU'yla)
```

Sunucu tarafında **hiçbir yeni indeksleme kodu yok** — sadece "gelen dosyayı
güvenle diske yaz" diyen 3 küçük uç var. Gerisi, koleksiyonun zaten var olan
`auto_refresh` mekanizması.

## Kurulum

### 1) Sunucuda bir kere: API anahtarı + koleksiyon profili

Sunucudaki panelin Ayarlar sayfasından (ya da doğrudan `/api/apikeys` ile)
**role=admin** bir API anahtarı üretin — istemci bunu kullanacak.

Sonra bu istemci için bir koleksiyon profili oluşturun (koleksiyonun kendisi
henüz Qdrant'ta var olmak ZORUNDA değil — `POST /api/profile` bunu
gerektirmez):

```bash
curl -X POST http://SUNUCU-IP:8500/api/profile \
  -H "x-api-key: <admin-anahtar>" -H "Content-Type: application/json" \
  -d '{"collection": "istemci1", "path": "data/remote_mirrors/istemci1", "auto_refresh": true}'
```

(Windows'ta `curl.exe` ya da panelin kendi Ayarlar arayüzünden de aynısı yapılabilir.)

Panelin de LAN'dan erişilebilir olması gerekir — bkz. ana `SECURITY.md`
("LAN exposure is opt-in via role-separated API keys").

### 2) İstemci makinede: config.json

`config.example.json`'u `config.json` olarak kopyalayıp doldurun:

```json
{
  "server_url": "http://SUNUCU-IP:8500",
  "client_id": "istemci1",
  "api_key": "<admin-anahtar>",
  "watch_path": "C:\\Projelerim\\benim-kod-tabanim",
  "patterns": ["*.pas", "*.dpr", "*.dpk", "*.inc"],
  "initial_sync": true
}
```

`client_id`, sunucudaki `/api/profile`'a verdiğiniz `collection` adıyla
**aynı** olmalı — ayna klasör tam olarak `data/remote_mirrors/<client_id>/`.

### 3) Çalıştırma

**Script olarak (önerilen — hiç AV riski yok):**
```powershell
pip install -r requirements.txt
python watch_client.py --config config.json
```

**Derlenmiş .exe olarak (çift-tıklama kolaylığı, küçük bir AV riskiyle):**
```powershell
.\build.ps1
.\dist\watch_client\watch_client.exe --config config.json
```

İlk çalıştırmada tüm `watch_path` içeriği bir kez yüklenir (`initial_sync`),
sonrasında sadece değişen/silinen/taşınan dosyalar gönderilir. Durdurmak
için `Ctrl+C`.

## Antivirüs notu

`.exe` derlerseniz (`--onedir` modunda, `--onefile` DEĞİL — bkz.
`build.ps1`'in kendi yorumu), Windows Defender yine de ilk çalıştırmada
uyarabilir, çünkü imzasız bir ikili dosya. Ana projenin
[CONTRIBUTING.md](../CONTRIBUTING.md)'sindeki "Antivirüs uyarıları"
bölümüyle aynı kök neden. Çözüm: `dist\watch_client\` klasörünü Defender
istisna listesine ekleyin, ya da doğrudan `python watch_client.py`
çalıştırın — script'in kendisi hiçbir risk taşımaz.

## Güvenlik

- İstemci-sunucu iletişimi düz HTTP (varsayılan) — üretimde sunucuyu bir
  ters vekil (reverse proxy) arkasında TLS ile açığa çıkarmayı düşünün.
- API anahtarı `config.json`'da düz metin — bu dosyayı git'e eklemeyin
  (proje kökündeki `.gitignore` zaten `remote-client/config.json`'u
  hariç tutuyor).
- Sunucu tarafı, gelen `relative_path`'i path-traversal'a (`..`, mutlak
  yol, sürücü harfi) karşı sıkı doğruluyor — bkz. `../src/api/remote_routes.py`
  ve `../tests/test_remote_mirror.py`.

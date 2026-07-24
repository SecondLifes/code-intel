# CodeIntel — Owner/Group + Help/Manual Sistemi Kapanış Raporu (24 Temmuz 2026, gece)

Bu oturumda **iki büyük özellik** tamamlandı: Owner/Group registry (kaynak/url + Tümünü Güncelle) ve baştan sona bir Help/Manual sistemi (HTML+PDF+DOCX). 4 commit, 43/43 test yeşil.

## Commit'ler
| Commit | İçerik |
|---|---|
| `b3e0fda` | Owner/Group registry, `kaynak`/`url` alanları (git otomatik doldurma), "Tümünü Güncelle" (git pull + reindex) |
| `450a945` | Help/Manual sistemi — HTML+PDF+DOCX üretimi |

## Owner/Group + Tümünü Güncelle
GitHub `owner/repo` ve TMS `Vendor→Ürün` modellerinin ortak paydası: **Owner→Collection**, Group bağımsız fonksiyonel etiket (REST Library, Şifreleme). `kaynak`/`url` git_info()'nun zaten hesaplayıp attığı `remote`'u artık kalıcı kaydediyor — ilk dokunuşta otomatik dolduruluyor, elle düzeltme asla ezilmiyor (izole sahte git deposuyla doğrulandı). "Tümünü Güncelle": kirli çalışma ağacında pull hiç denenmiyor (güvenlik önce).

## Help/Manual Sistemi
**Tasarım:** `artifact-design` skill'inin "var olanı onurlandır" ilkesi — panelin mevcut amber+teal "ink workshop" temasını genişletti (Georgia başlık + Calibri gövde + Consolas kod, hepsi tek paylaşılan CSS). **Tek belge modeli** (düz dict) üç şekilde render ediliyor (HTML/PDF/DOCX) — mantık üçe katlanmadı. `document_unit`'in zaten önbellekli özetini, sembol grafiğinin `extends` verisini yeniden kullandı.

**Canlı doğrulamada bulunan 2 gerçek hata (commit'ten önce düzeltildi):**
1. reportlab'ın `<font color>` etiketi `#` istiyor — atlanınca her PDF export'u 500 ile çöküyordu.
2. reportlab'ın yerleşik Helvetica'sı Türkçe glif taşımıyor — "Kullanım" → "Kullan■m" bozuluyordu (pypdf ile gerçek metin çıkarımı yapılmasaydı fark edilmezdi, yalnız HTTP 200 kontrolü yeterli olmazdı). Windows'taki gerçek Georgia/Calibri/Consolas TTF'leri kaydedilerek düzeltildi.

**Kullanıcı isteği üzerine eklenen üretim-yöntemi genişletmeleri** (sistem değişmedi):
- "Tümünü Oluştur" — tüm koleksiyonlar için toplu manual (orkestrasyon iki atılabilir sahte koleksiyonla doğrulandı, gerçek devasa koleksiyonlara dokunulmadı)
- Klasör-seçici scope (mevcut pick-folder'ı yeniden kullanıp göreli yol hesaplıyor) — 3 gerçek senaryoda (alt klasör/aynı klasör/dışarıda) tarayıcıda doğrulandı
- Offline çalışma teyit edildi (grep ile: hiç CDN/dış font referansı yok)

**Tam uçtan uca doğrulama:** RESTRequest4Delphi (17 dosya) → 24 sayfalık PDF + 516 paragraflı DOCX, ikisi de gerçek metin çıkarımıyla kontrol edildi.

## Genel durum
**43/43 test yeşil** (8 yenisi manual sistemi için). Panel çalışır durumda test edildi, şimdi düzenli kapatılıyor. Kalan: Sıra 11'in geri kalanı (LAN/agentic-edit), Sıra 12 (veri-kapılı).

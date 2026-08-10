<#
.SYNOPSIS
    Code-Intel'i sistemden kaldırır: servisleri durdurur, otomatik başlatma
    görevini siler; isteğe bağlı olarak pip paketlerini ve/veya yerel veriyi
    de temizler.

.DESCRIPTION
    Varsayılan olarak SADECE bu projenin kendi "ayak izini" temizler:
      1. Çalışan servisleri durdurur (tools\stop-system.ps1 -All)
      2. "CodeIntel-AutoStart" Görev Zamanlayıcı kaydını siler (kuruluysa)
    Kaynak kodu, git geçmişini veya proje klasörünü SİLMEZ — sadece silmek
    isterseniz klasörü elle silin.

.PARAMETER RemovePackages
    requirements.txt'teki paketleri sistemdeki Python'dan pip uninstall eder.
    DİKKAT: bu paketler sistem Python'unun GENEL (user/site-packages) ortamına
    kurulmuştu (bkz. CONTRIBUTING.md "Antivirüs uyarıları" — kasıtlı olarak
    .venv KULLANILMIYOR) — aynı makinedeki BAŞKA projeler de bu paketlerin
    bazılarını (fastapi, numpy, httpx gibi yaygın olanları) kullanıyor
    olabilir. Emin değilseniz bu anahtarı kullanmayın.

.PARAMETER RemoveData
    data\, backups\, logs\ klasörlerini siler (Qdrant indeksi, yedekler,
    loglar). GERİ ALINAMAZ.

.EXAMPLE
    .\tools\uninstall.ps1                              # servisleri durdur + autostart'ı kaldır
    .\tools\uninstall.ps1 -RemovePackages               # + pip paketlerini kaldır
    .\tools\uninstall.ps1 -RemoveData                   # + data/backups/logs'u sil
    .\tools\uninstall.ps1 -RemovePackages -RemoveData   # tam temizlik
#>
param(
    [switch]$RemovePackages,
    [switch]$RemoveData
)

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "== Code-Intel: kaldırılıyor ==" -ForegroundColor Cyan

# ---------- 1) SERVİSLERİ DURDUR ----------
$stopScript = Join-Path $ScriptDir "stop-system.ps1"
if (Test-Path $stopScript) {
    Write-Host "[Servisler] durduruluyor..." -ForegroundColor Yellow
    & $stopScript -All
}

# ---------- 2) OTOMATİK BAŞLATMA GÖREVİNİ SİL ----------
$null = schtasks /Query /TN "CodeIntel-AutoStart" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[Autostart] 'CodeIntel-AutoStart' görevi kaldırılıyor..." -ForegroundColor Yellow
    schtasks /Delete /TN "CodeIntel-AutoStart" /F | Out-Null
    Write-Host "[Autostart] kaldırıldı" -ForegroundColor Green
} else {
    Write-Host "[Autostart] kurulu görev yok — atlandı" -ForegroundColor DarkGray
}

# ---------- 3) (OPSİYONEL) PIP PAKETLERİ ----------
if ($RemovePackages) {
    $SystemPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($SystemPython) {
        Write-Warning "Bu paketler sistem Python'unun GENEL ortamındaydı — aynı makinedeki başka projeler de kullanıyor olabilir."
        Write-Host "[Paketler] requirements.txt'teki paketler kaldırılıyor..." -ForegroundColor Yellow
        & $SystemPython -m pip uninstall -y -r (Join-Path $ProjectRoot "requirements.txt")
        # CPU-only kurulumda (tools\install.ps1 -EmbeddingMode CPU) requirements.txt'te
        # olmayan ayrı bir `onnxruntime` (GPU değil) paketi de kurulmuş olabilir —
        # kurulu değilse pip zaten sessizce atlar, zararsız.
        & $SystemPython -m pip uninstall -y onnxruntime 2>$null
        Write-Host "[Paketler] kaldırıldı" -ForegroundColor Green
    } else {
        Write-Warning "[Paketler] sistemde 'python' bulunamadı — atlandı"
    }
} else {
    Write-Host "[Paketler] atlandı (kaldırmak için -RemovePackages verin)" -ForegroundColor DarkGray
}

# ---------- 4) (OPSİYONEL) YEREL VERİ ----------
if ($RemoveData) {
    foreach ($dir in @("data", "backups", "logs")) {
        $path = Join-Path $ProjectRoot $dir
        if (Test-Path $path) {
            Write-Host "[Veri] siliniyor: $path" -ForegroundColor Yellow
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
    Write-Host "[Veri] silindi" -ForegroundColor Green
} else {
    Write-Host "[Veri] atlandı (data\/backups\/logs\ silmek için -RemoveData verin)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "== Kaldırma tamamlandı ==" -ForegroundColor Cyan
Write-Host "Kaynak kod ve proje klasörü DOKUNULMADI — tamamen kaldırmak için klasörü elle silin."

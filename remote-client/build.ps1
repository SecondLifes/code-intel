<#
.SYNOPSIS
    watch_client.py'i tek klasörlü (--onedir) bir .exe olarak derler.

.DESCRIPTION
    --onedir (--onefile DEĞİL) kasıtlı seçim: tek-dosya self-extracting exe
    modu, çalışma zamanında kendi kendini geçici bir klasöre açıyor — bu
    davranış deseni, antivirüs heuristik motorlarının "packer/dropper"
    olarak işaretlediği klasik desen (bkz. ../CONTRIBUTING.md "Antivirüs
    uyarıları"). --onedir tek bir klasöre normal DLL/exe dosyaları
    yerleştirir, bu deseni tetiklemez — ama garanti değildir.

    Yine de ilk çalıştırmada Windows Defender uyarısı ÇIKABİLİR (imzasız
    exe) — bu durumda: (a) dist\watch_client\ klasörünü Defender istisna
    listesine ekleyin, ya da (b) doğrudan `python watch_client.py` ile
    çalıştırın (.exe'ye hiç gerek yok, aynı script, AV riski sıfır).

.EXAMPLE
    .\build.ps1
#>

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "== CodeIntel uzak istemci: derleniyor ==" -ForegroundColor Cyan

$SystemPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $SystemPython) {
    throw "Sistemde kurulu 'python' PATH'te bulunamadı. Python 3.12 veya 3.13 kurun -> https://www.python.org/downloads/windows/"
}

Write-Host "[Bağımlılıklar] pip install -r requirements.txt (watchdog + pyinstaller) ..." -ForegroundColor Yellow
Push-Location $ScriptDir
try {
    & $SystemPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Bağımlılık kurulumu başarısız oldu." }

    Write-Host "[PyInstaller] --onedir modunda derleniyor (AV yanlış-pozitif riskini azaltmak için --onefile DEĞİL) ..." -ForegroundColor Yellow
    & $SystemPython -m PyInstaller --onedir --console --name watch_client --noconfirm watch_client.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller derlemesi başarısız oldu." }
} finally { Pop-Location }

Write-Host ""
Write-Host "== Derleme tamamlandı ==" -ForegroundColor Cyan
Write-Host "Çıktı: $ScriptDir\dist\watch_client\watch_client.exe"
Write-Host "Kullanmadan önce: config.example.json'u config.json olarak kopyalayıp doldurun,"
Write-Host "sonra o klasöre koyup çalıştırın (watch_client.exe --config config.json)."
Write-Host ""
Write-Host "NOT: ilk çalıştırmada Windows Defender uyarısı çıkarsa README.md'ye bakın." -ForegroundColor Yellow

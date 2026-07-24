<#
.SYNOPSIS
    Code-Intel'i Windows oturum açılışında otomatik başlatacak Görev Zamanlayıcı
    kaydını kurar (veya -Uninstall ile kaldırır).

.DESCRIPTION
    "CodeIntel-AutoStart" adlı bir görev oluşturur: kullanıcı oturum açınca
    tools\start-system.ps1 -NoBrowser çalışır (Qdrant + panel sessizce ayağa
    kalkar; tarayıcı AÇILMAZ — sistem arka planda hazır bekler).
    Zaten çalışan servisler start-system tarafından atlandığı için görev
    tekrar tetiklense bile güvenlidir.

.EXAMPLE
    .\tools\install-autostart.ps1            # kur
    .\tools\install-autostart.ps1 -Uninstall # kaldır
#>
param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'
$TaskName  = "CodeIntel-AutoStart"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartPs1  = Join-Path $ScriptDir "start-system.ps1"

if ($Uninstall) {
    schtasks /Delete /TN $TaskName /F | Out-Null
    Write-Host "Kaldırıldı: '$TaskName' görevi silindi." -ForegroundColor Yellow
    exit 0
}

# pwsh varsa onu, yoksa Windows PowerShell'i kullan
$shell = (Get-Command pwsh -ErrorAction SilentlyContinue)?.Source
if (-not $shell) { $shell = (Get-Command powershell).Source }

$action = "`"$shell`" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartPs1`" -NoBrowser"
schtasks /Create /TN $TaskName /TR $action /SC ONLOGON /RL LIMITED /F | Out-Null

Write-Host "Kuruldu: '$TaskName' — oturum açılışında Code-Intel otomatik başlayacak (tarayıcısız)." -ForegroundColor Green
Write-Host "Kaldırmak için: .\tools\install-autostart.ps1 -Uninstall"

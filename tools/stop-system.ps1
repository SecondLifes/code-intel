<#
.SYNOPSIS
    Code-Intel sistemini durdurur: Panel (:8500) ve Qdrant (:6333).

.DESCRIPTION
    Varsayılan olarak Ollama'ya (:11434) DOKUNMAZ — Ollama sistem genelinde başka
    şeyler için de kullanılan, kendi başına açılan bir uygulamadır. Onu da
    kapatmak için -All verin.

.EXAMPLE
    .\tools\stop-system.ps1          # panel + qdrant
    .\tools\stop-system.ps1 -All     # panel + qdrant + ollama
#>
param([switch]$All)

$Ports = @(8500, 6333)
if ($All) { $Ports += 11434 }

foreach ($Port in $Ports) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "Port $Port : dinleyen yok"
        continue
    }
    # DİKKAT: değişken adı $pid OLAMAZ — $pid PowerShell'in salt-okunur otomatik
    # değişkenidir (mevcut sürecin PID'i); ona atama çalışma anında hata fırlatır.
    # (Bu betiğin eski sürümündeki gerçek hata buydu.)
    $procIds = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $procIds) {
        try {
            $proc = Get-Process -Id $procId -ErrorAction Stop
            Write-Host "Durduruluyor: $($proc.ProcessName) (PID $procId, port $Port)"
            Stop-Process -Id $procId -Force -Confirm:$false
        } catch {
            Write-Warning ("PID {0} (port {1}) durdurulamadı: {2}" -f $procId, $Port, $_.Exception.Message)
        }
    }
}

Write-Host "Bitti."

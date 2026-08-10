<#
.SYNOPSIS
    Code-Intel sistemini başlatır: Qdrant + Ollama kontrolü + FastAPI paneli.

.DESCRIPTION
    1. Qdrant  (qdrant-bin\qdrant.exe, veri: data\qdrant)  -> http://127.0.0.1:6333
    2. Ollama  (genelde kendiliğinden açık; kapalıysa 'ollama serve' denenir) -> :11434
       mcp-config.json'da uzak bir ollama_url yapılandırılmışsa (tools\install.ps1
       -OllamaMode Remote) bu adım tamamen atlanır.
    3. Panel   (sistemde kurulu Python + uvicorn src.panel:app) -> http://127.0.0.1:8500
    Her adımda port zaten dinleniyorsa o servis atlanır (tekrar çalıştırmak güvenlidir).
    Servisler gizli pencerede açılır, çıktıları logs\ altına yazılır.
    Panel sağlık kontrolünü geçince varsayılan tarayıcı açılır (-NoBrowser ile kapatılabilir).

.PARAMETER NoBrowser
    Panel açıldıktan sonra tarayıcıyı otomatik AÇMA.

.EXAMPLE
    .\tools\start-system.ps1
    .\tools\start-system.ps1 -NoBrowser
#>
param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$SystemPython = (Get-Command python -ErrorAction SilentlyContinue).Source
$QdrantExe   = Join-Path $ProjectRoot "qdrant-bin\qdrant.exe"
$QdrantData  = Join-Path $ProjectRoot "data\qdrant"
$LogDir      = Join-Path $ProjectRoot "logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Test-PortListening {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-HttpOk {
    # $Url 200 dönene kadar bekler; $TimeoutSec içinde başaramazsa $false döner.
    param([string]$Url, [int]$TimeoutSec, [string]$Label)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            return $true
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    Write-Warning "$Label $TimeoutSec sn içinde yanıt vermedi ($Url)"
    return $false
}

Write-Host "== Code-Intel: sistem başlatılıyor ==" -ForegroundColor Cyan
Write-Host "Proje kökü: $ProjectRoot"

# ---------- 1) QDRANT ----------
if (Test-PortListening 6333) {
    Write-Host "[Qdrant] zaten çalışıyor (:6333) — atlandı" -ForegroundColor Yellow
} else {
    if (-not (Test-Path $QdrantExe)) {
        throw "Qdrant bulunamadı: $QdrantExe  (qdrant-bin\qdrant-x86_64-pc-windows-msvc.zip içinden çıkarın)"
    }
    Write-Host "[Qdrant] başlatılıyor -> http://127.0.0.1:6333  (veri: data\qdrant)" -ForegroundColor Green
    # Depolama yolu ortam değişkeniyle verilir — çocuk süreç bunu miras alır.
    $env:QDRANT__STORAGE__STORAGE_PATH = $QdrantData
    Start-Process -FilePath $QdrantExe `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "qdrant.out.log") `
        -RedirectStandardError  (Join-Path $LogDir "qdrant.err.log")
    Remove-Item Env:QDRANT__STORAGE__STORAGE_PATH -ErrorAction SilentlyContinue
    if (-not (Wait-HttpOk "http://127.0.0.1:6333/collections" 30 "[Qdrant]")) {
        throw "Qdrant açılamadı — logs\qdrant.err.log dosyasına bakın."
    }
    Write-Host "[Qdrant] hazır" -ForegroundColor Green
}

# ---------- 2) OLLAMA ----------
# mcp-config.json'daki ollama_url uzak (127.0.0.1/localhost DIŞI) bir sunucuya
# işaret ediyorsa (bkz. tools\install.ps1 -OllamaMode Remote), bu makinede
# Ollama kurulu olsa bile ona hiç dokunmuyoruz — boşuna yerel bir 'ollama serve'
# başlatmak ya da "kurulu değil" diye uyarmak yanlış olur.
$mcpCfgPath = Join-Path $ProjectRoot "mcp-config.json"
$configuredOllamaUrl = "http://127.0.0.1:11434"
if (Test-Path $mcpCfgPath) {
    try {
        $mcpCfg = Get-Content $mcpCfgPath -Raw | ConvertFrom-Json
        if ($mcpCfg.ollama_url) { $configuredOllamaUrl = $mcpCfg.ollama_url }
    } catch { }
}
$isRemoteOllama = $configuredOllamaUrl -notmatch '(127\.0\.0\.1|localhost)'

if ($isRemoteOllama) {
    Write-Host "[Ollama] uzak sunucu yapılandırılmış ($configuredOllamaUrl) — bu makinede kontrol/başlatma ATLANDI" -ForegroundColor Yellow
} elseif (Test-PortListening 11434) {
    Write-Host "[Ollama] zaten çalışıyor (:11434) — atlandı" -ForegroundColor Yellow
} else {
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollamaCmd) {
        Write-Host "[Ollama] başlatılıyor -> http://127.0.0.1:11434" -ForegroundColor Green
        Start-Process -FilePath $ollamaCmd.Source -ArgumentList "serve" `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $LogDir "ollama.out.log") `
            -RedirectStandardError  (Join-Path $LogDir "ollama.err.log")
        if (Wait-HttpOk "http://127.0.0.1:11434/api/tags" 20 "[Ollama]") {
            Write-Host "[Ollama] hazır" -ForegroundColor Green
        } else {
            Write-Warning "[Ollama] açılamadı — arama yine çalışır; Türkçe açıklama/sohbet çalışmaz."
        }
    } else {
        Write-Warning "[Ollama] kurulu görünmüyor (PATH'te yok) — arama yine çalışır; açıklama/sohbet için https://ollama.com kurun."
    }
}

# ---------- 3) PANEL ----------
# Kasıtlı olarak sistemde kurulu Python kullanılıyor, proje-lokal .venv/uv
# DEĞİL: .venv\Scripts\python.exe (uv'nin oluşturduğu "trampoline" stub) ve
# uv.exe'nin kendisi imzasız + taze/taşınabilir exe oldukları için bazı
# antivirüs motorlarında yanlış-pozitif (Trojan) tetikliyor — bkz.
# CONTRIBUTING.md "Antivirüs uyarıları". Sistem Python'u uzun süredir aynı
# yolda durduğu, çoğu AV'nin itibar veritabanında zaten tanındığı için bu
# riski büyük ölçüde azaltıyor.
if (Test-PortListening 8500) {
    Write-Host "[Panel] zaten çalışıyor (:8500) — atlandı" -ForegroundColor Yellow
} else {
    if (-not $SystemPython) {
        throw "Sistemde kurulu 'python' PATH'te bulunamadı. Python 3.12 veya 3.13 kurun -> https://www.python.org/downloads/windows/  (PATH'e eklendiğinden emin olun)."
    }

    $pyVerRaw = & $SystemPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    $SupportedPyMinors = @(12, 13)
    $pyVerParts = $pyVerRaw -split '\.'
    $pyVerOk = ($pyVerParts.Count -eq 2) -and ($pyVerParts[0] -eq '3') -and ($SupportedPyMinors -contains [int]$pyVerParts[1])
    if (-not $pyVerOk) {
        throw @"
Desteklenmeyen Python sürümü: $pyVerRaw  ($SystemPython)

Code-Intel'in pinlenmiş bağımlılıkları (numpy, onnxruntime-gpu, grpcio, lxml,
mmh3...) yalnızca Python 3.12 ve 3.13 için önceden derlenmiş (wheel) paket
sunuyor. Daha yeni sürümlerde (3.14+) en azından onnxruntime-gpu'nun Windows
wheel'i henüz yok; kaynaktan derleme de bir C/C++ derleyici gerektiriyor ve
genelde başarısız oluyor.

Çözüm: Python 3.13'ü kurun -> https://www.python.org/downloads/windows/
Kurulumda "Add python.exe to PATH" işaretleyin, PATH'te 3.13'ün diğer Python
sürümlerinden ÖNCE geldiğinden emin olup bu script'i tekrar çalıştırın.
"@
    }

    & $SystemPython -c "import fastapi" *> $null
    $depsOk = ($LASTEXITCODE -eq 0)
    if (-not $depsOk) {
        Write-Host "[Panel] bağımlılıklar eksik — kuruluyor (pip)..." -ForegroundColor Yellow
        Push-Location $ProjectRoot
        try {
            & $SystemPython -m pip install -r requirements.txt
        } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { throw "Bağımlılık kurulumu başarısız oldu (pip install -r requirements.txt)." }
    }

    Write-Host "[Panel] başlatılıyor -> http://127.0.0.1:8500" -ForegroundColor Green
    Start-Process -FilePath $SystemPython `
        -ArgumentList @("-m", "uvicorn", "src.panel:app", "--host", "127.0.0.1", "--port", "8500") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "panel.out.log") `
        -RedirectStandardError  (Join-Path $LogDir "panel.err.log")
    if (-not (Wait-HttpOk "http://127.0.0.1:8500/api/health" 60 "[Panel]")) {
        throw "Panel açılamadı — logs\panel.err.log dosyasına bakın."
    }
    Write-Host "[Panel] hazır" -ForegroundColor Green
}

Write-Host ""
Write-Host "== Sistem hazır: http://127.0.0.1:8500 ==" -ForegroundColor Cyan
Write-Host "Durdurmak için: tools\stop-system.ps1   (loglar: logs\)"

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:8500"
}

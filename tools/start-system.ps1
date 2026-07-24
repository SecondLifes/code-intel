<#
.SYNOPSIS
    Code-Intel sistemini başlatır: Qdrant + Ollama kontrolü + FastAPI paneli.

.DESCRIPTION
    1. Qdrant  (qdrant-bin\qdrant.exe, veri: data\qdrant)  -> http://127.0.0.1:6333
    2. Ollama  (genelde kendiliğinden açık; kapalıysa 'ollama serve' denenir) -> :11434
    3. Panel   (.venv + uvicorn src.panel:app)             -> http://127.0.0.1:8500
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
$VenvPython  = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
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
if (Test-PortListening 11434) {
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
if (Test-PortListening 8500) {
    Write-Host "[Panel] zaten çalışıyor (:8500) — atlandı" -ForegroundColor Yellow
} else {
    if (-not (Test-Path $VenvPython)) {
        Write-Host "[Panel] .venv yok — oluşturuluyor (uv gerekli)..." -ForegroundColor Yellow
        Push-Location $ProjectRoot
        try {
            uv venv
            # Kesin (pinli) bağımlılıklar — GPU pinleri dahil; ayrıntı requirements.txt başında.
            uv pip install -r requirements.txt --python $VenvPython
        } finally { Pop-Location }
        if (-not (Test-Path $VenvPython)) { throw "Sanal ortam kurulamadı: $VenvPython" }
    }

    # .venv\Scripts\python.exe bir uv "trampoline"idir: gerçek yorumlayıcıya
    # (pyvenv.cfg'deki home yoluna) yönlendirir. O taban kurulum bozulur/silinirse
    # (YAŞANDI: yarıda kesilen bir uv işlemi sonrası klasör var ama python.exe yoktu,
    # panel "uv trampoline failed to spawn" ile hiç açılamıyordu) dosya diskte
    # görünse bile çalışmaz — bu yüzden varlık kontrolü yetmez, GERÇEKTEN çalıştırıp
    # deniyoruz ve gerekirse taban yorumlayıcıyı uv ile onarıyoruz.
    & $VenvPython --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[Panel] .venv python'u çalışmıyor — taban yorumlayıcı onarılıyor (uv python install)..." -ForegroundColor Yellow
        $pyVer = (Select-String -Path (Join-Path $ProjectRoot ".venv\pyvenv.cfg") -Pattern '^version_info\s*=\s*(.+)$').Matches.Groups[1].Value.Trim()
        uv python install $pyVer --reinstall
        & $VenvPython --version *> $null
        if ($LASTEXITCODE -ne 0) {
            throw ".venv python'u onarılamadı — '.venv' klasörünü silip betiği yeniden çalıştırın (ortam sıfırdan kurulur)."
        }
        Write-Host "[Panel] taban yorumlayıcı onarıldı" -ForegroundColor Green
    }
    Write-Host "[Panel] başlatılıyor -> http://127.0.0.1:8500" -ForegroundColor Green
    Start-Process -FilePath $VenvPython `
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

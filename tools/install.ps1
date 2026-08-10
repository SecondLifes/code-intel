<#
.SYNOPSIS
    Code-Intel'i ilk kez kurar: Python sürüm kontrolü, Ollama yerel/uzak seçimi,
    bağımlılık kurulumu.

.DESCRIPTION
    Tek seferlik kurulum adımı — start-system.ps1'i ilk kez çalıştırmadan önce
    (veya bağımlılıkları yeniden kurmak istediğinizde) çalıştırın:
      1. Sistemde kurulu Python'un sürümünü doğrular (yalnız 3.12/3.13
         desteklenir — bkz. CONTRIBUTING.md "Desteklenen Python sürümleri").
      2. qdrant-bin\qdrant.exe'nin var olduğunu doğrular.
      3. Ollama'nın nerede çalışacağını sorar:
         - Yerel: bu makinede Ollama kurulu mu diye bakar (kurulu değilse
           sadece uyarır, indirmeye ZORLAMAZ).
         - Uzak: bu makinede Ollama'yı hiç kontrol ETMEZ/kurdurmaz — sadece
           verdiğiniz uzak sunucu URL'sini mcp-config.json'a yazar.
      4. `pip install -r requirements.txt` çalıştırır.
    Kasıtlı olarak .venv veya uv KULLANMAZ, sistemde kurulu Python'a kurar —
    bkz. CONTRIBUTING.md "Antivirüs uyarıları".

.PARAMETER OllamaMode
    'Local' veya 'Remote'. Verilmezse interaktif sorulur.

.PARAMETER OllamaUrl
    OllamaMode Remote iken uzak sunucunun URL'si (örn. http://192.168.1.50:11434).
    Verilmezse interaktif sorulur.

.EXAMPLE
    .\tools\install.ps1
    .\tools\install.ps1 -OllamaMode Local
    .\tools\install.ps1 -OllamaMode Remote -OllamaUrl http://192.168.1.50:11434
#>
param(
    [ValidateSet('Local', 'Remote')]
    [string]$OllamaMode,
    [string]$OllamaUrl
)

$ErrorActionPreference = 'Stop'

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$QdrantExe   = Join-Path $ProjectRoot "qdrant-bin\qdrant.exe"

Write-Host "== Code-Intel: kurulum ==" -ForegroundColor Cyan

# ---------- 1) PYTHON SÜRÜMÜ ----------
$SystemPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $SystemPython) {
    throw "Sistemde kurulu 'python' PATH'te bulunamadı. Python 3.12 veya 3.13 kurun -> https://www.python.org/downloads/windows/  (kurulumda ""Add python.exe to PATH"" işaretleyin)."
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
Write-Host "[Python] $pyVerRaw -> $SystemPython" -ForegroundColor Green

# ---------- 2) QDRANT İKİLİ DOSYASI ----------
if (-not (Test-Path $QdrantExe)) {
    throw "Qdrant bulunamadı: $QdrantExe`nBu dosya normalde repo ile birlikte gelir (git-tracked) — eksikse repoyu yeniden indirin."
}
Write-Host "[Qdrant] ikili dosya mevcut: $QdrantExe" -ForegroundColor Green

# ---------- 3) OLLAMA: YEREL mi UZAK mı ----------
# Buradaki amaç: Ollama'yı zaten AYRI bir makinede (LAN'daki başka bir bilgisayar/
# sunucu) çalıştıranlar, bu makinede boşuna Ollama kurulum uyarısı/kontrolü
# görmesin — sadece o uzak sunucunun URL'sini mcp-config.json'a yazıp geçelim.
if (-not $OllamaMode) {
    Write-Host ""
    Write-Host "Ollama nerede çalışacak?" -ForegroundColor Cyan
    Write-Host "  [1] Bu makinede yerel (varsayılan) -> http://127.0.0.1:11434"
    Write-Host "  [2] Ağınızdaki başka bir makinede (uzak sunucu)"
    $choice = Read-Host "Seçiminiz [1/2] (varsayılan: 1)"
    if ($choice -eq '2') { $OllamaMode = 'Remote' } else { $OllamaMode = 'Local' }
}

if ($OllamaMode -eq 'Remote') {
    if (-not $OllamaUrl) {
        $OllamaUrl = Read-Host "Uzak Ollama URL'si (örn. http://192.168.1.50:11434)"
    }
    if (-not $OllamaUrl) { throw "Uzak Ollama modu seçildi ama URL verilmedi." }

    $cfgPath = Join-Path $ProjectRoot "mcp-config.json"
    $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
    $cfg.ollama_url = $OllamaUrl
    ($cfg | ConvertTo-Json -Depth 10) | Set-Content -LiteralPath $cfgPath -Encoding utf8
    Write-Host "[Ollama] uzak mod — mcp-config.json içindeki ollama_url güncellendi: $OllamaUrl" -ForegroundColor Green
    Write-Host "[Ollama] bu makinede Ollama kurulumu/kontrolü ATLANDI" -ForegroundColor DarkGray
} else {
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollamaCmd) {
        Write-Host "[Ollama] yerel kurulum bulundu: $($ollamaCmd.Source)" -ForegroundColor Green
    } else {
        Write-Warning "[Ollama] bu makinede kurulu değil. Arama yine çalışır; sohbet/açıklama/derin araştırma için kurun: https://ollama.com"
    }
}

# ---------- 4) BAĞIMLILIKLAR ----------
Write-Host ""
Write-Host "[Bağımlılıklar] pip install -r requirements.txt ..." -ForegroundColor Yellow
Push-Location $ProjectRoot
try {
    & $SystemPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Bağımlılık kurulumu başarısız oldu (pip install -r requirements.txt) — çıktıdaki hataya bakın." }
} finally { Pop-Location }
Write-Host "[Bağımlılıklar] kuruldu" -ForegroundColor Green

Write-Host ""
Write-Host "== Kurulum tamamlandı ==" -ForegroundColor Cyan
Write-Host "Başlatmak için:                                        tools\start-system.ps1"
Write-Host "Oturum açılışında otomatik başlatmak için (opsiyonel): tools\install-autostart.ps1"
Write-Host "Kaldırmak için:                                        tools\uninstall.ps1"

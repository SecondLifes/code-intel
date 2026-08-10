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
      4. Embedding/reranker'ın (kod indeksleme + arama — bu AYRI bir konu,
         Ollama'dan BAĞIMSIZ, her zaman bu makinede yerel çalışır) GPU mu CPU
         mu kullanacağını sorar:
         - GPU: requirements.txt'i olduğu gibi kurar (onnxruntime-gpu +
           nvidia-cu12 CUDA DLL'leri dahil).
         - CPU: onnxruntime-gpu / fastembed-gpu / nvidia-*-cu12 satırlarını
           requirements.txt'ten FİLTRELER (indirmez) ve yerine CPU-only
           `onnxruntime` kurar. Uzak Ollama seçimi bunu OTOMATİK yapmaz —
           GPU'suz bir makinede boşuna CUDA indirmemek için bu ayrı soruyu
           da açıkça CPU olarak yanıtlamanız gerekir.
      5. `pip install -r requirements.txt` çalıştırır (ya da CPU modundaysa
         filtrelenmiş hali + `onnxruntime`).
    Kasıtlı olarak .venv veya uv KULLANMAZ, sistemde kurulu Python'a kurar —
    bkz. CONTRIBUTING.md "Antivirüs uyarıları".

.PARAMETER OllamaMode
    'Local' veya 'Remote'. Verilmezse interaktif sorulur.

.PARAMETER OllamaUrl
    OllamaMode Remote iken uzak sunucunun URL'si (örn. http://192.168.1.50:11434).
    Verilmezse interaktif sorulur.

.PARAMETER EmbeddingMode
    'GPU' veya 'CPU'. Verilmezse interaktif sorulur (nvidia-smi ile otomatik
    algılanan varsayılanla). Ollama'nın yerel/uzak olmasından TAMAMEN BAĞIMSIZ
    bir seçimdir.

.EXAMPLE
    .\tools\install.ps1
    .\tools\install.ps1 -OllamaMode Local -EmbeddingMode GPU
    .\tools\install.ps1 -OllamaMode Remote -OllamaUrl http://192.168.1.50:11434 -EmbeddingMode CPU
#>
param(
    [ValidateSet('Local', 'Remote')]
    [string]$OllamaMode,
    [string]$OllamaUrl,
    [ValidateSet('GPU', 'CPU')]
    [string]$EmbeddingMode
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

# ---------- 4) EMBEDDING: GPU mu CPU mu ----------
# Uzak Ollama seçimi SADECE Ollama'yı (sohbet/derin araştırma LLM'i) etkiler.
# Kod indeksleme/aramadaki embedding+reranker AYRI bir aşamadır, bu makinede
# YEREL çalışır (FastEmbed/onnxruntime) — Ollama nerede olursa olsun gereklidir.
# Burada sorulan, o yerel embedding'in GPU (CUDA, ~34x daha hızlı) mi yoksa
# CPU mu kullanacağı.
if (-not $EmbeddingMode) {
    $gpuName = $null
    try {
        $smi = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null
        if ($LASTEXITCODE -eq 0 -and $smi) { $gpuName = ($smi -split ',')[0].Trim() }
    } catch { }

    Write-Host ""
    Write-Host "Embedding/reranker (kod indeksleme + arama) için GPU mu CPU mu?" -ForegroundColor Cyan
    if ($gpuName) {
        Write-Host "  Algılanan GPU: $gpuName"
        Write-Host "  [1] GPU (varsayılan — CUDA hızlandırmalı, CPU'ya göre ~34x daha hızlı)"
    } else {
        Write-Host "  NVIDIA GPU algılanamadı (nvidia-smi bulunamadı/başarısız)."
        Write-Host "  [1] GPU (yine de dene — CUDA sürücüsü/donanımı gerektirir)"
    }
    Write-Host "  [2] CPU-only (NVIDIA CUDA DLL indirmelerini tamamen ATLAR — daha küçük/hızlı kurulum, embedding daha yavaş çalışır)"
    $defaultChoice = if ($gpuName) { '1' } else { '2' }
    $choice = Read-Host "Seçiminiz [1/2] (varsayılan: $defaultChoice)"
    if (-not $choice) { $choice = $defaultChoice }
    $EmbeddingMode = if ($choice -eq '2') { 'CPU' } else { 'GPU' }
}
Write-Host "[Embedding] mod: $EmbeddingMode" -ForegroundColor Green

# ---------- 5) BAĞIMLILIKLAR ----------
Write-Host ""
Push-Location $ProjectRoot
try {
    if ($EmbeddingMode -eq 'CPU') {
        Write-Host "[Bağımlılıklar] CPU-only mod — onnxruntime-gpu/fastembed-gpu/nvidia-*-cu12 atlanıyor, pip install -r requirements.txt (filtreli) ..." -ForegroundColor Yellow
        $gpuPattern = '^(onnxruntime-gpu|fastembed-gpu|nvidia-[a-z0-9-]+-cu12)=='
        $tempReq = Join-Path ([System.IO.Path]::GetTempPath()) "code-intel-requirements-cpu.txt"
        Get-Content (Join-Path $ProjectRoot "requirements.txt") | Where-Object { $_ -notmatch $gpuPattern } | Set-Content -LiteralPath $tempReq -Encoding utf8
        try {
            & $SystemPython -m pip install -r $tempReq
            if ($LASTEXITCODE -ne 0) { throw "Bağımlılık kurulumu başarısız oldu (pip install -r requirements.txt, CPU-only filtre) — çıktıdaki hataya bakın." }
            Write-Host "[Bağımlılıklar] pip install onnxruntime==1.22.0 (CPU) ..." -ForegroundColor Yellow
            & $SystemPython -m pip install "onnxruntime==1.22.0"
            if ($LASTEXITCODE -ne 0) { throw "onnxruntime (CPU) kurulumu başarısız oldu." }
        } finally { Remove-Item -LiteralPath $tempReq -ErrorAction SilentlyContinue }
    } else {
        Write-Host "[Bağımlılıklar] pip install -r requirements.txt (GPU dahil) ..." -ForegroundColor Yellow
        & $SystemPython -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw "Bağımlılık kurulumu başarısız oldu (pip install -r requirements.txt) — çıktıdaki hataya bakın." }

        # onnxruntime-gpu VE düz onnxruntime, aynı `onnxruntime/` dosyalarını
        # paylaşıyor ama pip'e göre AYRI paketler (fastembed==0.8.0 düz
        # "onnxruntime"a bağımlı) — pip'in çözümleme sırası deterministik
        # değil, yani `pip install -r requirements.txt` bazen düz onnxruntime'ı
        # SONRADAN kurup onnxruntime-gpu'nun dosyalarının üzerine yazabiliyor
        # (canlı tekrarlandı: GPU pill'i kırmızıya döndü, gpu_available() False
        # oldu). Düzeltme: iki paketi de kaldırıp onnxruntime-gpu'yu TEK BAŞINA
        # yeniden kurarak GPU'nun her zaman kazandığını garanti ediyoruz.
        Write-Host "[Bağımlılıklar] onnxruntime-gpu/onnxruntime çakışması gideriliyor (GPU'nun kazandığından emin oluyoruz) ..." -ForegroundColor Yellow
        & $SystemPython -m pip uninstall -y onnxruntime onnxruntime-gpu 2>&1 | Out-Null
        & $SystemPython -m pip install --no-deps "onnxruntime-gpu==1.22.0"
        if ($LASTEXITCODE -ne 0) { throw "onnxruntime-gpu yeniden kurulumu başarısız oldu." }
    }
} finally { Pop-Location }
Write-Host "[Bağımlılıklar] kuruldu" -ForegroundColor Green

Write-Host ""
Write-Host "== Kurulum tamamlandı ==" -ForegroundColor Cyan
Write-Host "Başlatmak için:                                        tools\start-system.ps1"
Write-Host "Oturum açılışında otomatik başlatmak için (opsiyonel): tools\install-autostart.ps1"
Write-Host "Kaldırmak için:                                        tools\uninstall.ps1"

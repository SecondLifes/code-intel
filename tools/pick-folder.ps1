<#
.SYNOPSIS
    Bir Windows klasör seçim diyaloğu açar, seçilen yolu stdout'a yazar.

.DESCRIPTION
    src/api/admin_routes.py'deki /api/pick-folder ucu tarafından çağrılır
    (panel.py, Ayarlar sayfasındaki "Klasör Seç" düğmesi).

    Bu diyalog, HTTP isteğiyle (panel sürecinden subprocess olarak) tetiklendiği
    için Windows'un "foreground lock" kısıtına takılır: normal TopMost/Activate
    çağrıları pencereyi GÖRÜNÜR yapar (Win32 EnumWindows ile doğrulandı — "Klasöre
    Gözat" başlıklı, gerçek, görünür bir pencere) ama tarayıcının/terminalin ARKASINDA
    kalabiliyor, çünkü bu istek zincirinin "son kullanıcı girdisi" izini Windows
    HTTP→FastAPI→subprocess sıçramalarında kaybediyor. Çözüm: mevcut ön plan
    penceresinin thread input'una geçici olarak "iliş" (AttachThreadInput) — bu,
    farklı süreçler arasında SetForegroundWindow kısıtını aşmak için bilinen,
    standart bir Win32 tekniğidir.

.EXAMPLE
    powershell -NoProfile -STA -File tools\pick-folder.ps1
#>

Add-Type -AssemblyName System.Windows.Forms | Out-Null

Add-Type -Namespace CI -Name Win32 -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, IntPtr lpdwProcessId);
[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
'@

function Force-Foreground([IntPtr]$hWnd) {
    $foreWin = [CI.Win32]::GetForegroundWindow()
    $foreThread = [CI.Win32]::GetWindowThreadProcessId($foreWin, [IntPtr]::Zero)
    $thisThread = [CI.Win32]::GetCurrentThreadId()
    $attached = $false
    if ($foreThread -ne 0 -and $foreThread -ne $thisThread) {
        $attached = [CI.Win32]::AttachThreadInput($thisThread, $foreThread, $true)
    }
    [CI.Win32]::ShowWindow($hWnd, 9) | Out-Null   # SW_RESTORE
    [CI.Win32]::BringWindowToTop($hWnd) | Out-Null
    [CI.Win32]::SetForegroundWindow($hWnd) | Out-Null
    if ($attached) {
        [CI.Win32]::AttachThreadInput($thisThread, $foreThread, $false) | Out-Null
    }
}

$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.StartPosition = 'Manual'
$owner.Location = New-Object System.Drawing.Point(-2000, -2000)
$owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.ShowInTaskbar = $false
$owner.Show()
Force-Foreground $owner.Handle

$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Kaynak klasörü seç'

$result = $dialog.ShowDialog($owner)
$owner.Close()

if ($result -eq 'OK') {
    Write-Output $dialog.SelectedPath
}

#Requires -Version 5.1
# Check tools for Tauri dev + Setup packaging. UTF-8.
# Exit: 0=all ok, 2=dev missing, 3=dev ok setup missing
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Find-RepoRoot {
    $start = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    if (Test-Path (Join-Path $start "app\package.json")) { return $start }
    $cur = (Get-Location).Path
    for ($i = 0; $i -lt 6; $i++) {
        if (Test-Path (Join-Path $cur "app\package.json")) { return $cur }
        $parent = Split-Path $cur -Parent
        if (-not $parent -or $parent -eq $cur) { break }
        $cur = $parent
    }
    return $start
}

$Root = Find-RepoRoot
Set-Location -LiteralPath $Root
Write-Host ("Repo: " + $Root)
Write-Host ""

$devOk = $true
$setupOk = $true
$notes = @()

function Write-Ok([string]$msg) { Write-Host ("[OK]  " + $msg) -ForegroundColor Green }
function Write-Bad([string]$msg) { Write-Host ("[MISS] " + $msg) -ForegroundColor Red }
function Write-Info([string]$msg) { Write-Host ("[--]  " + $msg) -ForegroundColor DarkGray }
function Write-Warn2([string]$msg) { Write-Host ("[WARN] " + $msg) -ForegroundColor Yellow }

Write-Host "======== DEV (tauri:dev) ========"

$nodeOk = $false
try {
    $nv = & node -v 2>$null
    if ($LASTEXITCODE -eq 0 -and $nv) { Write-Ok ("Node " + $nv); $nodeOk = $true }
} catch {}
if (-not $nodeOk) { Write-Bad "Node missing"; $devOk = $false }

$npmOk = $false
try {
    $np = & npm -v 2>$null
    if ($LASTEXITCODE -eq 0 -and $np) { Write-Ok ("npm " + $np); $npmOk = $true }
} catch {}
if (-not $npmOk) { Write-Bad "npm missing"; $devOk = $false }

$rustOk = $false
try {
    $rv = & rustc -V 2>$null
    if ($LASTEXITCODE -eq 0 -and $rv) { Write-Ok ("Rust " + $rv); $rustOk = $true }
} catch {}
if (-not $rustOk) { Write-Bad "rustc missing"; $devOk = $false }

$pf = $env:ProgramFiles
$pf86 = ${env:ProgramFiles(x86)}
if (-not $pf86) { $pf86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)") }

$vcList = @(
    'F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
)
if ($pf) {
    $vcList += (Join-Path $pf 'Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat')
    $vcList += (Join-Path $pf 'Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat')
    $vcList += (Join-Path $pf 'Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat')
}
if ($pf86) {
    $vcList += (Join-Path $pf86 'Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat')
}

$vcvars = $null
foreach ($c in $vcList) {
    if ($c -and (Test-Path -LiteralPath $c)) { $vcvars = $c; break }
}

if ($vcvars) {
    Write-Ok ("MSVC vcvars64: " + $vcvars)
    $env:TM_VCVARS = $vcvars
} else {
    Write-Bad "vcvars64.bat not found (need VS C++ build tools)"
    $devOk = $false
}

$link = Get-Command link.exe -ErrorAction SilentlyContinue
if ($link) {
    Write-Ok ("link.exe in PATH: " + $link.Source)
} else {
    Write-Warn2 "link.exe not in this shell - use scripts\dev\tauri-dev.bat"
    $notes += "Use tauri-dev.bat (calls vcvars first)"
}

$wvOk = $false
$wvPaths = @()
if ($pf86) {
    $wvPaths += (Join-Path $pf86 'Microsoft\EdgeWebView\Application')
    $wvPaths += (Join-Path $pf86 'Microsoft\Edge\Application')
}
if ($pf) {
    $wvPaths += (Join-Path $pf 'Microsoft\EdgeWebView\Application')
}
foreach ($w in $wvPaths) {
    if ($w -and (Test-Path -LiteralPath $w)) { $wvOk = $true; break }
}
if ($wvOk) { Write-Ok "WebView2/Edge present" }
else { Write-Warn2 "WebView2 folder not found; Tauri may bootstrap on first run" }

if (Test-Path -LiteralPath (Join-Path $Root 'app\node_modules')) {
    Write-Ok "app/node_modules installed"
} else {
    Write-Warn2 "app/node_modules missing - run: cd app & npm install"
    $notes += "cd app && npm install"
}

if (Test-Path -LiteralPath (Join-Path $Root 'Runtime\pythonw.exe')) {
    Write-Ok "Runtime\pythonw.exe present (can test real VC)"
} else {
    Write-Warn2 "No Runtime\pythonw.exe - UI works, worker will not"
    $notes += "Need Runtime at repo root for voice conversion"
}

foreach ($p in @('gui_v1.py', 'tools\realtime_worker.py', 'tools\worker_protocol.py')) {
    if (Test-Path -LiteralPath (Join-Path $Root $p)) { Write-Ok $p }
    else { Write-Bad ("missing " + $p); $devOk = $false }
}

$ud = Join-Path $Root 'User_Data'
if (-not (Test-Path -LiteralPath $ud)) {
    New-Item -ItemType Directory -Path $ud -Force | Out-Null
}
Write-Ok "User_Data/ ready"

Write-Host ""
Write-Host "======== SETUP build ========"

$pyOk = $false
try {
    $py = & python --version 2>&1
    if ($py) { Write-Ok ("Python " + $py); $pyOk = $true }
} catch {}
if (-not $pyOk) { Write-Bad "python not in PATH"; $setupOk = $false }

$iscc = $null
$isccList = @($env:ISCC, $env:INNO_SETUP_ISCC, 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe')
if ($pf86) { $isccList += (Join-Path $pf86 'Inno Setup 6\ISCC.exe') }
if ($pf) { $isccList += (Join-Path $pf 'Inno Setup 6\ISCC.exe') }
foreach ($c in $isccList) {
    if ($c -and (Test-Path -LiteralPath $c)) { $iscc = $c; break }
}
if ($iscc) {
    Write-Ok ("ISCC: " + $iscc)
    $env:ISCC = $iscc
} else {
    Write-Bad "ISCC.exe not found (Inno Setup 6)"
    $setupOk = $false
    $notes += "Install Inno Setup 6 or set ISCC=full\path\ISCC.exe"
}

foreach ($p in @('scripts\build_setup.py', 'scripts\build_release.py', 'installer\RVC_Fabric_Setup.iss')) {
    if (Test-Path -LiteralPath (Join-Path $Root $p)) { Write-Ok $p }
    else { Write-Bad ("missing " + $p); $setupOk = $false }
}

if (Test-Path -LiteralPath (Join-Path $Root 'CNB-GIT-RELEASE')) {
    Write-Ok "CNB-GIT-RELEASE/ present"
} else {
    Write-Info "No local CNB-GIT-RELEASE (OK for build; first-run needs network)"
}

$oldSetup = Join-Path $Root 'dist\RVC_Fabric_Setup.exe'
if (Test-Path -LiteralPath $oldSetup) {
    $t = (Get-Item -LiteralPath $oldSetup).LastWriteTime
    Write-Warn2 ("Old dist\RVC_Fabric_Setup.exe exists (" + $t + ") - rebuild with --clean for full test")
}

Write-Host ""
Write-Host "======== Next steps ========"
Write-Host "  DEV:    scripts\dev\tauri-dev.bat"
Write-Host "  SMOKE:  scripts\dev\run_smoke_tests.bat"
Write-Host "  SETUP:  scripts\dev\build_setup.bat"
Write-Host "  LIST:   scripts\dev\TEST_CHECKLIST.md"
Write-Host ""

if ($notes.Count -gt 0) {
    Write-Host "Notes:"
    foreach ($n in $notes) { Write-Host ("  - " + $n) }
    Write-Host ""
}

if (-not $devOk) {
    Write-Host "RESULT: DEV env not ready" -ForegroundColor Red
    exit 2
}
if (-not $setupOk) {
    Write-Host "RESULT: DEV OK; SETUP packaging env not ready" -ForegroundColor Yellow
    exit 3
}
Write-Host "RESULT: DEV + SETUP env ready" -ForegroundColor Green
exit 0

[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$VenvPython = Join-Path $Root ".venv-build311\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating isolated Python 3.11 build environment..."
    py -3.11 -m venv (Join-Path $Root ".venv-build311")
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 is required to build this executable. Install Python 3.11 and retry."
    }
}

$BuildVersion = & $VenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($BuildVersion.Trim() -ne "3.11") {
    throw "The isolated build environment must use Python 3.11; found $BuildVersion. Remove .venv-build311 and retry."
}

if (-not $SkipInstall) {
    Write-Host "Installing pinned build tools..."
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $VenvPython -m pip install -r (Join-Path $Root "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }
}

$PyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--log-level", "TRACE",
    "--workpath", (Join-Path $Root "build\pyinstaller"),
    "--distpath", (Join-Path $Root "dist")
)
if ($Clean) { $PyInstallerArgs += "--clean" }
$PyInstallerArgs += (Join-Path $Root "s_tcg.spec")

Write-Host "Building single-file Windows executable..."
$BuildLog = Join-Path $Root "build\pyinstaller-build.log"
$StdoutLog = Join-Path $Root "build\pyinstaller-stdout.log"
$StderrLog = Join-Path $Root "build\pyinstaller-stderr.log"
$ArgumentLine = ($PyInstallerArgs | ForEach-Object {
    if ([string]$_ -match '[\s"]') { '"' + ([string]$_).Replace('"', '\"') + '"' }
    else { [string]$_ }
}) -join ' '
$BuildProcess = Start-Process -FilePath $VenvPython -ArgumentList $ArgumentLine `
    -WorkingDirectory $Root -Wait -PassThru `
    -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog
Get-Content -Path $StdoutLog, $StderrLog -ErrorAction SilentlyContinue |
    Set-Content -Path $BuildLog -Encoding utf8
if ($BuildProcess.ExitCode -ne 0) {
    Write-Host "PyInstaller failed. Last build log lines:"
    Get-Content -Path $BuildLog -Tail 60
    throw "PyInstaller build failed; see build\pyinstaller-build.log."
}

$ExePath = Join-Path $Root "dist\s-tcg.exe"
if (-not (Test-Path $ExePath)) { throw "Build completed without dist\s-tcg.exe." }
$SizeMB = [math]::Round((Get-Item $ExePath).Length / 1MB, 1)
Write-Host "Build successful: $ExePath ($SizeMB MB)"
Write-Host "Build log: $BuildLog"
Write-Host "Copy this EXE to a Windows machine; Python is not required there."

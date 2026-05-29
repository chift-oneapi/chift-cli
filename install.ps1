<#
.SYNOPSIS
    chift CLI installer for Windows — downloads pre-built binaries from GitHub Releases.

.DESCRIPTION
    Usage:
        irm https://raw.githubusercontent.com/chift-oneapi/chift-cli/master/install.ps1 | iex

    Environment variables:
        CHIFT_VERSION      Pin to a specific release tag (e.g. v0.1.0). Default: latest
        CHIFT_INSTALL_DIR  Override install directory. Default: %LOCALAPPDATA%\chift-cli

.PARAMETER ModifyPath
    Add the install directory to the user PATH. By default the installer only
    prints the command to run.
#>
[CmdletBinding()]
param(
    [switch]$ModifyPath
)

$ErrorActionPreference = "Stop"

# -- Helpers ---------------------------------------------------------------

function Write-Info { param([string]$Message) Write-Host "info  $Message" -ForegroundColor Green }
function Write-Err  { param([string]$Message) Write-Host "error $Message" -ForegroundColor Red }
function Die        { param([string]$Message) Write-Err $Message; exit 1 }

# -- Configuration ---------------------------------------------------------

$Repo    = "chift-oneapi/chift-cli"
$Version = if ($env:CHIFT_VERSION) { $env:CHIFT_VERSION } else { "latest" }
$LibDir  = if ($env:CHIFT_INSTALL_DIR) { $env:CHIFT_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "chift-cli" }

# -- Detect platform -------------------------------------------------------

$Os = "windows"

switch ($env:PROCESSOR_ARCHITECTURE) {
    "AMD64" { $Arch = "amd64" }
    "x86"   { $Arch = "amd64" }  # 32-bit shell on 64-bit OS; binary is amd64
    "ARM64" { Die "Windows on ARM64 is not yet supported. Only amd64 binaries are published." }
    default { Die "Unsupported architecture: $($env:PROCESSOR_ARCHITECTURE). Supported: amd64" }
}

# -- Construct download URL ------------------------------------------------

$Binary  = "chift-$Os-$Arch"
$Tarball = "$Binary.tar.gz"

if ($Version -eq "latest") {
    $BaseUrl = "https://github.com/$Repo/releases/latest/download"
} else {
    $BaseUrl = "https://github.com/$Repo/releases/download/$Version"
}

Write-Host ""
Write-Info "Downloading chift CLI ($Os/$Arch)..."

# -- Download tarball and checksum -----------------------------------------

$TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("chift-install-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null

try {
    $TarballPath  = Join-Path $TmpDir $Tarball
    $ChecksumPath = Join-Path $TmpDir "$Tarball.sha256"

    try {
        Invoke-WebRequest -Uri "$BaseUrl/$Tarball" -OutFile $TarballPath -UseBasicParsing
    } catch {
        Die "Failed to download tarball. Check that a release exists with artifacts for $Os/$Arch."
    }
    try {
        Invoke-WebRequest -Uri "$BaseUrl/$Tarball.sha256" -OutFile $ChecksumPath -UseBasicParsing
    } catch {
        Die "Failed to download checksum."
    }

    Write-Info "Download complete"

    # -- Verify checksum ---------------------------------------------------

    Write-Info "Verifying checksum..."
    # The .sha256 file is in `sha256sum` format: "<hash>  <filename>"
    $Expected = ((Get-Content $ChecksumPath -Raw).Trim() -split '\s+')[0].ToLower()
    $Actual   = (Get-FileHash -Path $TarballPath -Algorithm SHA256).Hash.ToLower()
    if ($Expected -ne $Actual) {
        Die "Checksum verification failed! The downloaded archive may be corrupted."
    }
    Write-Info "Checksum verified"

    # -- Extract to install directory --------------------------------------

    Write-Info "Installing to $LibDir..."
    if (Test-Path $LibDir) { Remove-Item -Recurse -Force $LibDir }
    New-Item -ItemType Directory -Path $LibDir -Force | Out-Null

    # tar ships with Windows 10 1803+ and Windows 11. The archive contains a
    # top-level `__main__.dist/` directory; strip it so contents land in $LibDir.
    tar -xzf $TarballPath -C $LibDir --strip-components=1
    if ($LASTEXITCODE -ne 0) {
        Die "Failed to extract archive. 'tar' is required (built in to Windows 10 1803+)."
    }

    $ExePath = Join-Path $LibDir "$Binary.exe"
    if (-not (Test-Path $ExePath)) {
        Die "Expected binary not found after extraction: $ExePath"
    }

    # -- Create a `chift` shim ---------------------------------------------
    # A small .cmd wrapper lets users type `chift` instead of the full name.
    $ShimPath = Join-Path $LibDir "chift.cmd"
    Set-Content -Path $ShimPath -Value "@echo off`r`n`"%~dp0$Binary.exe`" %*" -Encoding ASCII
    Write-Info "Created shim $ShimPath"

} finally {
    Remove-Item -Recurse -Force $TmpDir -ErrorAction SilentlyContinue
}

# -- PATH configuration ----------------------------------------------------

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$OnPath = ($UserPath -split ';') -contains $LibDir

if (-not $OnPath -and $ModifyPath) {
    $NewPath = if ([string]::IsNullOrEmpty($UserPath)) { $LibDir } else { "$UserPath;$LibDir" }
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    $env:Path = "$env:Path;$LibDir"
    Write-Info "Added $LibDir to your user PATH"
    $OnPath = $true
    $PathModified = $true
}

# -- Success ---------------------------------------------------------------

Write-Host ""
Write-Info "chift CLI installed!"

if (-not $OnPath) {
    Write-Host ""
    Write-Host "  $LibDir is not on your PATH. Add it permanently by running:" -ForegroundColor White
    Write-Host "    setx Path `"`$env:Path;$LibDir`""
    Write-Host ""
    Write-Host "  Then open a new terminal to pick up the change." -ForegroundColor White
}

Write-Host ""
Write-Host "  Get started:" -ForegroundColor White
Write-Host "    chift auth setup     # Configure credentials"
Write-Host "    chift --help         # See all commands"
Write-Host ""
if ($PathModified) {
    Write-Host "  Open a new terminal to pick up PATH changes." -ForegroundColor White
    Write-Host ""
}

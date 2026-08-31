param(
    [string]$ModelUrl = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
    [string]$ExpectedModelSha256 = "",
    [string]$WorkDir = "build\release-core"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

$work = Join-Path $repo $WorkDir
$modelZip = Join-Path $work "vosk-model-small-ru-0.22.zip"
$modelExtract = Join-Path $work "model"
$modelDir = Join-Path $modelExtract "vosk-model-small-ru-0.22"
$distDir = Join-Path $work "dist"
$buildDir = Join-Path $work "pyinstaller"

New-Item -ItemType Directory -Force -Path $work | Out-Null

if (-not (Test-Path $modelZip)) {
    Write-Host "Downloading pinned Vosk model..."
    curl.exe -fL --retry 4 --retry-delay 3 $ModelUrl -o $modelZip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download Vosk model from the official source"
    }
}

$modelArchiveHash = (Get-FileHash -Algorithm SHA256 $modelZip).Hash.ToLowerInvariant()
if ($ExpectedModelSha256) {
    $expected = $ExpectedModelSha256.Trim().ToLowerInvariant()
    if ($expected.Length -ne 64 -or $modelArchiveHash -ne $expected) {
        throw "Vosk archive SHA256 mismatch: expected=$expected actual=$modelArchiveHash"
    }
}

if (Test-Path $modelExtract) {
    Remove-Item $modelExtract -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $modelExtract | Out-Null
Expand-Archive -Path $modelZip -DestinationPath $modelExtract -Force

foreach ($marker in @("am", "conf", "graph")) {
    if (-not (Test-Path (Join-Path $modelDir $marker))) {
        throw "Vosk model archive is incomplete: missing $marker"
    }
}

if (Test-Path $distDir) { Remove-Item $distDir -Recurse -Force }
if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }

$addData = "$modelDir;models/vosk/vosk-model-small-ru-0.22"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --noconsole `
    --name assistant-core `
    --distpath $distDir `
    --workpath $buildDir `
    --specpath $work `
    --collect-all silero `
    --collect-all vosk `
    --collect-all uiautomation `
    --collect-all pycaw `
    --collect-all comtypes `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.protocols.websockets.auto `
    --hidden-import uvicorn.lifespan.on `
    --add-data $addData `
    scripts/assistant_core_entry.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed"
}

$exe = Join-Path $distDir "assistant-core.exe"
if (-not (Test-Path $exe)) {
    throw "assistant-core.exe was not produced"
}

$env:ZIREN_PACKAGE_SELF_TEST = "1"
try {
    & $exe
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged Core self-test failed with exit code $LASTEXITCODE"
    }
} finally {
    Remove-Item Env:ZIREN_PACKAGE_SELF_TEST -ErrorAction SilentlyContinue
}

$hash = (Get-FileHash -Algorithm SHA256 $exe).Hash.ToLowerInvariant()
$size = (Get-Item $exe).Length
$metadata = [ordered]@{
    schema_version = 1
    artifact = "assistant-core.exe"
    sha256 = $hash
    size_bytes = $size
    vosk_model = "vosk-model-small-ru-0.22"
    vosk_source = $ModelUrl
    vosk_archive_sha256 = $modelArchiveHash
}
$metadata | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $distDir "assistant-core.metadata.json")

Write-Host "Release Core ready: $exe"
Write-Host "SHA256: $hash"
Write-Host "Size: $size bytes"
Write-Host "Vosk archive SHA256: $modelArchiveHash"

param(
    [string]$VoskModelUrl = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
    [string]$ExpectedVoskSha256 = "",
    [string]$SileroModelUrl = "https://models.silero.ai/models/tts/ru/v5_5_ru.pt",
    [string]$ExpectedSileroSha256 = "",
    [string]$WorkDir = "build\release-core"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

$work = Join-Path $repo $WorkDir
$voskZip = Join-Path $work "vosk-model-small-ru-0.22.zip"
$voskExtract = Join-Path $work "vosk"
$voskDir = Join-Path $voskExtract "vosk-model-small-ru-0.22"
$sileroModel = Join-Path $work "v5_5_ru.pt"
$distDir = Join-Path $work "dist"
$buildDir = Join-Path $work "pyinstaller"

New-Item -ItemType Directory -Force -Path $work | Out-Null

function Download-VerifiedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string]$ExpectedSha256 = "",
        [Parameter(Mandatory = $true)][string]$Label
    )

    if (-not (Test-Path $Destination)) {
        Write-Host "Downloading $Label..."
        curl.exe -fL --retry 4 --retry-delay 3 $Url -o $Destination
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to download $Label from the official source"
        }
    }

    $hash = (Get-FileHash -Algorithm SHA256 $Destination).Hash.ToLowerInvariant()
    if ($ExpectedSha256) {
        $expected = $ExpectedSha256.Trim().ToLowerInvariant()
        if ($expected.Length -ne 64 -or $hash -ne $expected) {
            throw "$Label SHA256 mismatch: expected=$expected actual=$hash"
        }
    }

    return $hash
}

$voskArchiveHash = Download-VerifiedFile `
    -Url $VoskModelUrl `
    -Destination $voskZip `
    -ExpectedSha256 $ExpectedVoskSha256 `
    -Label "Vosk model archive"

$sileroModelHash = Download-VerifiedFile `
    -Url $SileroModelUrl `
    -Destination $sileroModel `
    -ExpectedSha256 $ExpectedSileroSha256 `
    -Label "Silero TTS model"

if ((Get-Item $sileroModel).Length -lt 1MB) {
    throw "Silero TTS model is unexpectedly small"
}

if (Test-Path $voskExtract) {
    Remove-Item $voskExtract -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $voskExtract | Out-Null
Expand-Archive -Path $voskZip -DestinationPath $voskExtract -Force

foreach ($marker in @("am", "conf", "graph")) {
    if (-not (Test-Path (Join-Path $voskDir $marker))) {
        throw "Vosk model archive is incomplete: missing $marker"
    }
}

if (Test-Path $distDir) { Remove-Item $distDir -Recurse -Force }
if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }

$voskData = "$voskDir;models/vosk/vosk-model-small-ru-0.22"
$sileroData = "$sileroModel;models/silero"

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
    --add-data $voskData `
    --add-data $sileroData `
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
    schema_version = 2
    artifact = "assistant-core.exe"
    sha256 = $hash
    size_bytes = $size
    vosk_model = "vosk-model-small-ru-0.22"
    vosk_source = $VoskModelUrl
    vosk_archive_sha256 = $voskArchiveHash
    silero_model = "v5_5_ru.pt"
    silero_source = $SileroModelUrl
    silero_model_sha256 = $sileroModelHash
    offline_voice_assets = $true
}
$metadata | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $distDir "assistant-core.metadata.json")

Write-Host "Release Core ready: $exe"
Write-Host "SHA256: $hash"
Write-Host "Size: $size bytes"
Write-Host "Vosk archive SHA256: $voskArchiveHash"
Write-Host "Silero model SHA256: $sileroModelHash"

param([Parameter(Mandatory = $true)][string]$Root)
# Downloads FluidSynth (Windows x64 build) and the GeneralUser GS SoundFont into vendor\.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$headers = @{ 'User-Agent' = 'OrchSketch-setup' }

$vendor = Join-Path $Root 'vendor'
New-Item -ItemType Directory -Force -Path $vendor | Out-Null

# ---- FluidSynth ----
$fsDir = Join-Path $vendor 'fluidsynth'
$haveFs = (Test-Path $fsDir) -and (Get-ChildItem -Path $fsDir -Recurse -Filter 'libfluidsynth*.dll' -ErrorAction SilentlyContinue)
if (-not $haveFs) {
    $rel = Invoke-RestMethod -Uri 'https://api.github.com/repos/FluidSynth/fluidsynth/releases/latest' -Headers $headers
    $assets = $rel.assets | Where-Object { $_.name -match 'win10-x64' -and $_.name -like '*.zip' }
    $asset = ($assets | Where-Object { $_.name -notmatch 'glib' } | Select-Object -First 1)
    if (-not $asset) { $asset = $assets | Select-Object -First 1 }
    if (-not $asset) { throw "No Windows x64 FluidSynth build in release $($rel.tag_name)" }
    Write-Output "FluidSynth release $($rel.tag_name): $($asset.name)"
    $zip = Join-Path $env:TEMP $asset.name
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing -Headers $headers
    if (Test-Path $fsDir) { Remove-Item -Recurse -Force $fsDir }
    Expand-Archive -Path $zip -DestinationPath $fsDir -Force
    $dll = Get-ChildItem -Path $fsDir -Recurse -Filter 'libfluidsynth*.dll' | Select-Object -First 1
    if (-not $dll) { throw 'libfluidsynth DLL not found in the FluidSynth download' }
    Write-Output "FluidSynth DLL: $($dll.FullName)"
    Set-Content -Path (Join-Path $fsDir 'VERSION.txt') -Value "$($rel.tag_name) $($asset.name)"
} else { Write-Output 'FluidSynth already present' }

# ---- GeneralUser GS SoundFont ----
$sfDir = Join-Path $vendor 'soundfonts'
New-Item -ItemType Directory -Force -Path $sfDir | Out-Null
$sf = Join-Path $sfDir 'GeneralUser-GS.sf2'
if (-not (Test-Path $sf)) {
    $items = Invoke-RestMethod -Uri 'https://api.github.com/repos/mrbumpy409/GeneralUser-GS/contents/' -Headers $headers
    $sfItem = $items | Where-Object { $_.name -like '*.sf2' } | Select-Object -First 1
    if (-not $sfItem) { throw 'No .sf2 found in the GeneralUser GS repository' }
    Write-Output "SoundFont: $($sfItem.name)"
    Invoke-WebRequest -Uri $sfItem.download_url -OutFile $sf -UseBasicParsing -Headers $headers
    foreach ($it in ($items | Where-Object { $_.type -eq 'file' -and $_.name -match '(?i)licen|readme' })) {
        Invoke-WebRequest -Uri $it.download_url -OutFile (Join-Path $sfDir $it.name) -UseBasicParsing -Headers $headers
    }
} else { Write-Output 'SoundFont already present' }
Write-Output ("SoundFont size: {0:N1} MB" -f ((Get-Item $sf).Length / 1MB))

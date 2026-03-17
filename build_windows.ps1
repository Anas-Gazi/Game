$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot '..\.venv\Scripts\python.exe'

if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment not found at $pythonExe"
}

Set-Location $projectRoot

Remove-Item '.\build' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item '.\dist' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item '.\release' -Recurse -Force -ErrorAction SilentlyContinue

& $pythonExe -m PyInstaller --noconfirm '.\snake_game.spec'

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path '.\dist\SnakeLegends')) {
    throw 'Expected build output folder dist\SnakeLegends was not created.'
}

New-Item -ItemType Directory -Path '.\release' -Force | Out-Null

$zipPath = '.\release\SnakeLegends-windows.zip'
$maxAttempts = 5
$attempt = 0
$zipped = $false

while (-not $zipped -and $attempt -lt $maxAttempts) {
    try {
        if (Test-Path $zipPath) {
            Remove-Item $zipPath -Force
        }
        Compress-Archive -Path '.\dist\SnakeLegends\*' -DestinationPath $zipPath -Force
        $zipped = $true
    }
    catch {
        $attempt += 1
        if ($attempt -ge $maxAttempts) {
            throw "Failed to create release zip after $maxAttempts attempts. Last error: $($_.Exception.Message)"
        }
        Start-Sleep -Seconds 3
    }
}

Write-Host ''
Write-Host 'Build complete.'
Write-Host 'Upload this file to itch.io:'
Write-Host $zipPath
Write-Host ''
Write-Host 'Players should extract the zip and run SnakeLegends.exe'
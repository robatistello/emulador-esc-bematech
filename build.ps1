param([string]$Python, [switch]$CleanOnly)
$ErrorActionPreference = "Stop"
if (-not $Python) {
    # O python do PATH pode ser o atalho da Microsoft Store; o lançador py aponta para uma instalação real.
    $Python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
}
$previousCacheDir = $env:PYINSTALLER_CONFIG_DIR
Push-Location $PSScriptRoot
try {
    $workRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'work'))
    $buildWorkPath = Join-Path $workRoot 'pyinstaller'
    $buildCachePath = Join-Path $workRoot 'pyinstaller-cache'
    if ((Test-Path -LiteralPath $workRoot) -and ((Get-Item -LiteralPath $workRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "A pasta work e um link; limpeza cancelada."
    }
    foreach ($buildTarget in @($buildWorkPath, $buildCachePath)) {
        $resolvedTarget = [IO.Path]::GetFullPath($buildTarget)
        if (-not $resolvedTarget.StartsWith($workRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Pasta de limpeza fora de work: $resolvedTarget"
        }
        if (Test-Path -LiteralPath $resolvedTarget) {
            $buildItems = @((Get-Item -LiteralPath $resolvedTarget -Force)) + @(Get-ChildItem -LiteralPath $resolvedTarget -Recurse -Force)
            if ($buildItems | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
                throw "Link encontrado na pasta de build; limpeza cancelada."
            }
            foreach ($buildItem in $buildItems) {
                if ($buildItem.Attributes -band [IO.FileAttributes]::ReadOnly) {
                    $buildItem.Attributes = $buildItem.Attributes -band (-bnot [IO.FileAttributes]::ReadOnly)
                }
            }
            Write-Host "Limpando: $resolvedTarget"
            Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
        }
    }
    if ($CleanOnly) {
        Write-Host "Limpeza concluida. Fontes, historico e executavel preservados."
        return
    }
    $env:PYINSTALLER_CONFIG_DIR = $buildCachePath
    & $Python -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível criar o ambiente de build." }
    $buildPython = Join-Path $PSScriptRoot '.venv-build\Scripts\python.exe'
    & $buildPython -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível instalar o PyInstaller." }
    $webResource = (Join-Path $PSScriptRoot 'web') + ':web'
    $licenseResource = (Join-Path $PSScriptRoot 'THIRD-PARTY-NOTICES.txt') + ':.'
    $iconPath = Join-Path $PSScriptRoot 'printer.ico'
    $iconResource = $iconPath + ':.'
    $versionMatch = Select-String -LiteralPath (Join-Path $PSScriptRoot 'server.py') -Pattern '^VERSION = "(\d+)\.(\d+)\.(\d+)"$'
    if (-not $versionMatch) { throw "VERSION não encontrada em server.py." }
    $versionParts = $versionMatch.Matches[0].Groups[1..3] | ForEach-Object { $_.Value }
    $version = $versionParts -join '.'
    $versionTuple = ($versionParts + '0') -join ', '
    $versionFile = Join-Path $workRoot 'version-info.txt'
    New-Item -ItemType Directory -Force -Path $workRoot | Out-Null
    @"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($versionTuple), prodvers=($versionTuple), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', 'Rodrigo Batistello'),
      StringStruct('FileDescription', 'Emulador EscBematech'),
      StringStruct('FileVersion', '$version'),
      StringStruct('InternalName', 'EmuladorEscBematech'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 Rodrigo Batistello'),
      StringStruct('OriginalFilename', 'EmuladorEscBematech.exe'),
      StringStruct('ProductName', 'Emulador EscBematech'),
      StringStruct('ProductVersion', '$version')])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
"@ | Set-Content -LiteralPath $versionFile -Encoding ASCII
    & $buildPython -m PyInstaller --noconfirm --clean --onefile --windowed --name EmuladorEscBematech --icon $iconPath --version-file $versionFile --add-data $webResource --add-data $licenseResource --add-data $iconResource --distpath outputs --workpath $buildWorkPath --specpath work server.py
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o executável." }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LEIA-ME-WINDOWS.txt') -Destination (Join-Path outputs 'LEIA-ME.txt') -Force
    Write-Host "Pronto: $PSScriptRoot\outputs\EmuladorEscBematech.exe $version e LEIA-ME.txt"
} finally {
    $env:PYINSTALLER_CONFIG_DIR = $previousCacheDir
    Pop-Location
}

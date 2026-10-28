<#
.SYNOPSIS
Gera o executável do Windows em outputs\windows, com o LEIA-ME.txt ao lado.

.PARAMETER Python
Python usado para criar o ambiente de build. O padrão é o lançador py, ou python se ele não existir.

.PARAMETER CleanOnly
Só remove os arquivos temporários do build, sem compilar.
#>
param(
    [string]$Python,
    [switch]$CleanOnly
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PackagePath = Join-Path $ProjectRoot 'emulator'
$WorkRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'work'))
$WorkPath = Join-Path $WorkRoot 'windows'
$PyInstallerWorkPath = Join-Path $WorkPath 'pyinstaller'
$PyInstallerCachePath = Join-Path $WorkPath 'pyinstaller-cache'
$VenvPath = Join-Path $ProjectRoot '.venv-build'
$DistPath = Join-Path $ProjectRoot 'outputs\windows'
$ExePath = Join-Path $DistPath 'EmuladorEscBematech.exe'
$IconPath = Join-Path $PackagePath 'printer.ico'

function Test-Link([string]$Path) {
    return [bool]((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Clear-BuildFolder([string]$Path) {
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($WorkRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Pasta de limpeza fora de work: $resolved"
    }

    if (-not (Test-Path -LiteralPath $resolved)) {
        return
    }

    # Um link dentro de work faria o Remove-Item apagar arquivos fora da pasta de build.
    $items = @(Get-Item -LiteralPath $resolved -Force) + @(Get-ChildItem -LiteralPath $resolved -Recurse -Force)
    if ($items | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
        throw 'Link encontrado na pasta de build; limpeza cancelada.'
    }

    foreach ($item in $items) {
        if ($item.Attributes -band [IO.FileAttributes]::ReadOnly) {
            $item.Attributes = $item.Attributes -band (-bnot [IO.FileAttributes]::ReadOnly)
        }
    }

    Write-Host "Limpando: $resolved"
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Invoke-Checked([string]$FailureMessage, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Get-VersionParts {
    $pattern = '^VERSION = "(\d+)\.(\d+)\.(\d+)"$'
    $match = Select-String -LiteralPath (Join-Path $PackagePath 'server.py') -Pattern $pattern
    if (-not $match) {
        throw 'VERSION não encontrada em emulator\server.py.'
    }

    return $match.Matches[0].Groups[1..3] | ForEach-Object { $_.Value }
}

function Write-VersionInfo([string]$Path, [string[]]$VersionParts) {
    $version = $VersionParts -join '.'
    $versionTuple = ($VersionParts + '0') -join ', '

    # Formato do PyInstaller para a aba Detalhes das propriedades do .exe.
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
"@ | Set-Content -LiteralPath $Path -Encoding ASCII
}

if (-not $Python) {
    # O python do PATH pode ser o atalho da Microsoft Store; o lançador py aponta para uma instalação real.
    $Python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
}

$previousCacheDir = $env:PYINSTALLER_CONFIG_DIR
Push-Location $ProjectRoot
try {
    if ((Test-Path -LiteralPath $WorkRoot) -and (Test-Link $WorkRoot)) {
        throw 'A pasta work é um link; limpeza cancelada.'
    }

    Clear-BuildFolder $PyInstallerWorkPath
    Clear-BuildFolder $PyInstallerCachePath

    if ($CleanOnly) {
        Write-Host 'Limpeza concluída. Fontes, histórico e executável preservados.'
        return
    }

    if (Get-Process EmuladorEscBematech -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $ExePath }) {
        throw "O emulador está aberto ($ExePath). Saia dele pela bandeja antes de compilar."
    }

    $env:PYINSTALLER_CONFIG_DIR = $PyInstallerCachePath
    $buildPython = Join-Path $VenvPath 'Scripts\python.exe'
    Invoke-Checked 'Não foi possível criar o ambiente de build.' { & $Python -m venv $VenvPath }
    Invoke-Checked 'Não foi possível instalar o PyInstaller.' {
        & $buildPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-build.txt')
    }

    $versionParts = Get-VersionParts
    $versionFile = Join-Path $WorkPath 'version-info.txt'
    New-Item -ItemType Directory -Force -Path $WorkPath | Out-Null
    Write-VersionInfo $versionFile $versionParts

    $noticesPath = Join-Path $WorkPath 'THIRD-PARTY-NOTICES.txt'
    Invoke-Checked 'Não foi possível montar os avisos de licença.' {
        & $buildPython (Join-Path $PSScriptRoot 'notices.py') windows $noticesPath
    }

    $pyInstallerArguments = @(
        '--noconfirm', '--clean', '--onefile', '--windowed',
        '--name', 'EmuladorEscBematech',
        '--icon', $IconPath,
        '--version-file', $versionFile,
        '--paths', $ProjectRoot,
        '--add-data', "$(Join-Path $PackagePath 'web'):emulator/web",
        '--add-data', "${IconPath}:emulator",
        '--add-data', "${noticesPath}:.",
        '--distpath', $DistPath,
        '--workpath', $PyInstallerWorkPath,
        '--specpath', $WorkPath,
        (Join-Path $PackagePath '__main__.py')
    )
    Invoke-Checked 'Falha ao gerar o executável.' { & $buildPython -m PyInstaller @pyInstallerArguments }

    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LEIA-ME-WINDOWS.txt') -Destination (Join-Path $DistPath 'LEIA-ME.txt') -Force
    Copy-Item -LiteralPath $noticesPath -Destination $DistPath -Force
    Write-Host "Pronto: $ExePath $($versionParts -join '.'), LEIA-ME.txt e THIRD-PARTY-NOTICES.txt"
} finally {
    $env:PYINSTALLER_CONFIG_DIR = $previousCacheDir
    Pop-Location
}

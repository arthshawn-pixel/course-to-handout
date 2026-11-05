param(
    [string]$RuntimePath = (Join-Path (Get-Location) 'handout-runtime'),
    [string]$PythonExe = 'python',
    [string]$CompilerExe = ''
)
$ErrorActionPreference = 'Stop'
$runtimeRoot = [IO.Path]::GetFullPath($RuntimePath)
if ($runtimeRoot -eq [IO.Path]::GetPathRoot($runtimeRoot)) { throw 'Use a dedicated runtime folder.' }
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
& $PythonExe -c "import sys; assert sys.version_info >= (3,10)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ required; pass -PythonExe <python.exe>.' }
$runtimePython = Join-Path $runtimeRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython)) {
    & $PythonExe -m venv (Join-Path $runtimeRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
}
$requirementsFile = Join-Path $PSScriptRoot '..\requirements-media.txt'
$requirementsHash = (Get-FileHash -LiteralPath $requirementsFile -Algorithm SHA256).Hash
$dependencyStamp = Join-Path $runtimeRoot 'dependencies.sha256'
$dependenciesMatch = (Test-Path -LiteralPath $dependencyStamp) -and ((Get-Content -LiteralPath $dependencyStamp -Raw).Trim() -eq $requirementsHash)
if ($dependenciesMatch) {
    & $runtimePython -c "import sys,importlib.metadata as m; from pathlib import Path; pairs=[s.strip().split('==') for s in Path(sys.argv[1]).read_text().splitlines() if '==' in s and not s.lstrip().startswith('#')]; assert all(m.version(n)==v for n,v in pairs)" $requirementsFile
    if ($LASTEXITCODE -ne 0) { $dependenciesMatch = $false }
}
if (-not $dependenciesMatch) {
    & $runtimePython -m pip install --disable-pip-version-check --retries 1 -r $requirementsFile
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; check network before retrying.' }
    Set-Content -LiteralPath $dependencyStamp -Value $requirementsHash -Encoding ascii
}
if ($CompilerExe) {
    $compilerPath = [IO.Path]::GetFullPath($CompilerExe)
    if (-not (Test-Path -LiteralPath $compilerPath -PathType Leaf)) { throw 'CompilerExe does not exist.' }
} else {
    $compilerDirectory = Join-Path $runtimeRoot 'tectonic-0.17.0'
    $compilerPath = Join-Path $compilerDirectory 'tectonic.exe'
    if (-not (Test-Path -LiteralPath $compilerPath)) {
        $archivePath = Join-Path $runtimeRoot 'tectonic-0.17.0.zip'
        $expectedHash = 'f61ce51f0b0ade1015b7de7ef368541c5424e9756ecbd0d7af97d6d48030845f'
        $archiveValid = (Test-Path -LiteralPath $archivePath) -and ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLower() -eq $expectedHash)
        if (-not $archiveValid) {
            Invoke-WebRequest -Uri 'https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-pc-windows-msvc.zip' -OutFile $archivePath -TimeoutSec 180
        }
        if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLower() -ne $expectedHash) { throw 'Compiler archive checksum mismatch.' }
        Expand-Archive -LiteralPath $archivePath -DestinationPath $compilerDirectory -Force
    }
}
& $compilerPath --version
if ($LASTEXITCODE -ne 0) { throw 'Compiler cannot start; default installer targets Windows x64.' }
$cachePath = Join-Path $runtimeRoot 'tex-cache'
New-Item -ItemType Directory -Force -Path $cachePath | Out-Null
$settings = @{ python = $runtimePython; compiler = $compilerPath; engine = 'tectonic'; fonts = 'sourcehan'; version = '0.4.0'; tex_cache = $cachePath; root = $runtimeRoot }
$settings | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot 'runtime.json') -Encoding utf8
$oldTex = $env:HANDOUT_TEX
$oldRuntime = $env:HANDOUT_RUNTIME
$oldCache = $env:TECTONIC_CACHE_DIR
try {
    $env:HANDOUT_TEX = $compilerPath
    $env:HANDOUT_RUNTIME = $runtimeRoot
    $env:TECTONIC_CACHE_DIR = $cachePath
    & $runtimePython (Join-Path $PSScriptRoot 'lecture.py') preflight $runtimeRoot --engine tectonic --fonts sourcehan
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; runtime/cache preserved. Inspect smoke/build/student-reading/compiler.log.' }
} finally {
    $env:HANDOUT_TEX = $oldTex
    $env:HANDOUT_RUNTIME = $oldRuntime
    $env:TECTONIC_CACHE_DIR = $oldCache
}
Write-Output "Runtime prepared: $runtimeRoot"
Write-Output 'Reuse runtime.json for later courses. Visual inspection remains a host action.'

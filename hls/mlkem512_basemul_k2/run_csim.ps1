$ErrorActionPreference = 'Stop'

$src = Join-Path $PSScriptRoot 'src'
$tb = Join-Path $PSScriptRoot 'tb/tb_mlkem512_basemul_acc_k2.cpp'
$outDir = Join-Path $PSScriptRoot 'build'
$exe = Join-Path $outDir 'tb_mlkem512_basemul_acc_k2.exe'

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$compileArgs = @('-std=c++17', '-Wall', '-Wextra', '-Wconversion', '-Wshadow', '-pedantic',
    (Join-Path $src 'mlkem512_basemul_acc_k2.cpp'), $tb, '-I', $src, '-o', $exe)
& g++ @compileArgs
if ($LASTEXITCODE -ne 0) { throw "g++ compile failed" }

$runOutput = & $exe
if ($LASTEXITCODE -ne 0) { throw "ML-KEM-512 BaseMul C simulation failed" }
$runOutput
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$evidence = Join-Path $repoRoot 'results/accelerator_interface/basemul_k2_csim.txt'
[IO.File]::WriteAllText($evidence, (($runOutput -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))

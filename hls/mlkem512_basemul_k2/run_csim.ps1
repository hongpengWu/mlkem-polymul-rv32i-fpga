$ErrorActionPreference = 'Stop'

$src = Join-Path $PSScriptRoot 'src'
$tb = Join-Path $PSScriptRoot 'tb/tb_mlkem512_basemul_acc_k2.cpp'
$outDir = Join-Path $PSScriptRoot 'build'
$exe = Join-Path $outDir 'tb_mlkem512_basemul_acc_k2.exe'

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
& g++ -std=c++17 -Wall -Wextra -Wconversion -Wshadow -pedantic `
    (Join-Path $src 'mlkem512_basemul_acc_k2.cpp') $tb `
    '-I', $src, '-o', $exe
if ($LASTEXITCODE -ne 0) { throw "g++ compile failed" }

& $exe
if ($LASTEXITCODE -ne 0) { throw "ML-KEM-512 BaseMul C simulation failed" }

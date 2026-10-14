$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $root
$vivado = 'E:\Xilinx\Vivado\2024.2\bin\vivado.bat'
$base = Join-Path $root 'results\official_baseline\mlkem512\batches\rv32im_fast'
$names = @('batch_000_007','batch_008_015','batch_016_023','batch_024_031','batch_032_037')
foreach ($name in $names) {
    $result = Join-Path $base $name
    $meta = Get-Content -Raw -LiteralPath (Join-Path $result 'batch.json') | ConvertFrom-Json
    $project = Join-Path $root ('build\accel_kat\' + $name)
    New-Item -ItemType Directory -Force -Path $project | Out-Null
    Write-Host "=== ACCEL_KAT_MISSING $name cases=$($meta.case_count) ===" -ForegroundColor Cyan
    & $vivado -mode batch -source scripts/mlkem512_accel/run_kat_batch.tcl `
        -log (Join-Path $project 'vivado.log') `
        -journal (Join-Path $project 'vivado.jou') `
        -tclargs $result $project ([int]$meta.case_count)
    if ($LASTEXITCODE -ne 0) { throw "Missing batch failed: $name exit=$LASTEXITCODE" }
    $log = Get-Content -Raw -LiteralPath (Join-Path $result 'accelerate_simulate.log')
    if ($log -notmatch "MLKEM512_PASS cases=$($meta.case_count)\s") { throw "Missing final PASS: $name" }
    Write-Host "=== ACCEL_KAT_MISSING_PASS $name ===" -ForegroundColor Green
}
Write-Host '=== ACCEL_KAT_MISSING_FINISHED ===' -ForegroundColor Green

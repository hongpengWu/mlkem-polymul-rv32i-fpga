$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$project = Join-Path $root 'vivado/project_rv32im_iterative'
$results = Join-Path $root 'results/rv32im_iterative'
New-Item -ItemType Directory -Force -Path $results | Out-Null
$suites = [ordered]@{
    sim_cpu = 'RV32IM_ISA_PASS tests=4096 pcpi=4096'
    sim_core = 'V39-E MANUAL RTL COSIM PASS'
    sim_protocol = 'BRAM PROTOCOL PASS'
    sim_board = 'PYNQZ2 BOARD SIM PASS'
    sim_1 = 'BOARD VIO SIM PASS'
}
foreach ($suite in $suites.GetEnumerator()) {
    $path = Join-Path $project ("mlkem_pynqz2.sim/$($suite.Key)/behav/xsim/simulate.log")
    $content = Get-Content -LiteralPath $path -Raw
    if (-not $content.Contains($suite.Value) -or $content -match '(?im)^\s*(Fatal:|Error:|\$fatal)') {
        throw "Simulation did not pass: $($suite.Key)"
    }
    if ($suite.Key -eq 'sim_cpu' -and $content -notmatch '(?m)^RV32IM_ISA_PASS tests=4096 pcpi=4096 cycles=\d+ fast_mul=0\s*$') {
        throw 'CPU simulation did not use the iterative multiplier'
    }
    Copy-Item -LiteralPath $path -Destination (Join-Path $results ($suite.Key + '.txt'))
}
$cpuLog = Get-Content -LiteralPath (Join-Path $results 'sim_cpu.txt')
$csvLines = @($cpuLog | Where-Object { $_.StartsWith('RV32IM_CSV,') } | ForEach-Object { $_.Substring(11) })
$measurements = @($csvLines | ConvertFrom-Csv)
if ($measurements.Count -ne 8 -or @($measurements | Where-Object { [int]$_.samples -ne 512 }).Count) {
    throw 'Incomplete M instruction measurements'
}
if (($measurements.op | Sort-Object) -join ',' -ne 'DIV,DIVU,MUL,MULH,MULHSU,MULHU,REM,REMU') {
    throw 'Expected all eight distinct M instructions'
}
[IO.File]::WriteAllLines((Join-Path $results 'instruction_cycles.csv'), $csvLines)
foreach ($report in @('utilization_routed.rpt', 'utilization_hierarchical.rpt', 'timing_routed.rpt', 'bus_skew_routed.rpt', 'drc_routed.rpt')) {
    Copy-Item -LiteralPath (Join-Path $root "build/reports/rv32im_iterative/$report") -Destination $results
}
$release = Join-Path $root 'release/rv32im_iterative'
foreach ($artifact in @('mlkem_pynqz2.bit', 'mlkem_pynqz2.ltx', 'SHA256SUMS')) {
    if (-not (Test-Path -LiteralPath (Join-Path $release $artifact))) { throw "Missing artifact: $artifact" }
}
$releaseHashes = @{}
foreach ($line in (Get-Content -LiteralPath (Join-Path $release 'SHA256SUMS'))) {
    if ($line -notmatch '^([0-9a-fA-F]{64})  (mlkem_pynqz2\.(bit|ltx))$') { throw 'Invalid release checksum entry' }
    if ($releaseHashes.ContainsKey($Matches[2])) { throw 'Duplicate release checksum entry' }
    $releaseHashes[$Matches[2]] = $Matches[1]
}
foreach ($artifact in @('mlkem_pynqz2.bit', 'mlkem_pynqz2.ltx')) {
    if ((Get-FileHash -LiteralPath (Join-Path $release $artifact) -Algorithm SHA256).Hash -ne $releaseHashes[$artifact]) {
        throw "Release checksum mismatch: $artifact"
    }
}
Copy-Item -LiteralPath (Join-Path $release 'SHA256SUMS') -Destination (Join-Path $results 'release_sha256.txt')
Copy-Item -LiteralPath (Join-Path $project 'mlkem_pynqz2.runs/synth_1/runme.log') -Destination (Join-Path $results 'synthesis.txt')
Copy-Item -LiteralPath (Join-Path $project 'mlkem_pynqz2.sim/sim_1/behav/xsim/elaborate.log') -Destination (Join-Path $results 'elaborate_vio.txt')
$inputs = @('rtl', 'constraints', 'firmware/images', 'tb') | ForEach-Object {
    Get-ChildItem -LiteralPath (Join-Path $root $_) -File -Recurse | Where-Object {
        $_.Extension -in @('.v', '.sv', '.dat', '.mem', '.xdc') -and $_.FullName -notmatch '[\\/]\.sim[\\/]'
    }
}
$inputs += Get-Item -LiteralPath (Join-Path $root 'scripts/run.tcl'), (Join-Path $root 'vivado/project.tcl')
$inputs += Get-Item -LiteralPath (Join-Path $project 'mlkem_pynqz2.xpr'), (Join-Path $project 'mlkem_pynqz2.srcs/sources_1/ip/mlkem_profile_vio/mlkem_profile_vio.xci')
$inputs | Sort-Object FullName | ForEach-Object {
    [pscustomobject]@{
        Path=$_.FullName.Substring($root.Length+1).Replace('\','/')
        SHA256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }
} | Export-Csv -LiteralPath (Join-Path $results 'build_inputs.csv') -NoTypeInformation -Encoding utf8
$baseline = Join-Path $root 'results/rv32i_baseline'
New-Item -ItemType Directory -Force -Path $baseline | Out-Null
foreach ($report in @('utilization_routed.rpt', 'timing_routed.rpt', 'bus_skew_routed.rpt', 'drc_routed.rpt')) {
    $snapshot = Join-Path $root "build/reports/rv32i_baseline/$report"
    $saved = Join-Path $baseline $report
    if (Test-Path -LiteralPath $saved) {
        if ((Test-Path -LiteralPath $snapshot) -and
            (Get-FileHash -LiteralPath $snapshot).Hash -ne (Get-FileHash -LiteralPath $saved).Hash) {
            throw "Historical baseline differs; preserve it and record the new run separately: $report"
        }
    } elseif (Test-Path -LiteralPath $snapshot) {
        Copy-Item -LiteralPath $snapshot -Destination $saved
    } else {
        throw "Missing historical RV32I report: $report"
    }
}
foreach ($directory in @($results, $baseline)) {
    $hashes = Get-ChildItem -LiteralPath $directory -File | Where-Object Name -ne 'SHA256SUMS' | Sort-Object Name | ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        '{0}  {1}' -f $hash.Hash.ToLowerInvariant(), $_.Name
    }
    [IO.File]::WriteAllText((Join-Path $directory 'SHA256SUMS'), ($hashes -join "`n") + "`n", [Text.Encoding]::ASCII)
}
Write-Host "MEASUREMENTS_COLLECTED=$results"

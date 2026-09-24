<#
Run the host-side ML-KEM ACVP regression against the pinned mlkem-native tree.

The reference source and its build output live under build/, which is ignored.
This script only records the client output in results/official_reference/; it
does not copy the reference implementation into the FPGA project.
##>
[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [string]$BashPath
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$source = Join-Path $root 'build\kat_sources\mlkem-native'
$vectors = Join-Path $root 'vectors\official_kat\acvp'
$results = Join-Path $root 'results\official_reference'
$validator = Join-Path $root 'scripts\kat\validate_acvp_json.py'

if (-not (Test-Path -LiteralPath $source)) {
    throw "Pinned mlkem-native source is missing: $source"
}
if (-not (Test-Path -LiteralPath $vectors)) {
    throw "Checked-in ACVP vectors are missing: $vectors"
}
New-Item -ItemType Directory -Force -Path $results | Out-Null

python $validator
if ($LASTEXITCODE -ne 0) {
    throw 'ACVP vector structure validation failed.'
}

if ([string]::IsNullOrWhiteSpace($BashPath)) {
    $candidates = @(
        'D:\Git\bin\bash.exe',
        'E:\Xilinx\Vitis\2024.2\tps\win64\git-2.45.0\bin\bash.exe',
        'E:\Xilinx\Vitis\2024.2\tps\win64\git-2.41.0\bin\bash.exe'
    )
    $BashPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if ([string]::IsNullOrWhiteSpace($BashPath) -or -not (Test-Path -LiteralPath $BashPath)) {
    throw 'Git Bash was not found. Install Git for Windows or pass -BashPath.'
}

function Convert-ToGitBashPath([string]$Path) {
    $full = [System.IO.Path]::GetFullPath($Path)
    $drive = $full.Substring(0, 1).ToLowerInvariant()
    $rest = $full.Substring(2).Replace('\', '/')
    return "/$drive$rest"
}

$sourceUnix = Convert-ToGitBashPath $source
$vectorsUnix = Convert-ToGitBashPath $vectors
$shellUnix = Convert-ToGitBashPath (Join-Path (Split-Path $BashPath) 'sh.exe')

if (-not $SkipBuild) {
    $buildCommand = "cd '$sourceUnix' && rm -rf test/build && make SHELL='$shellUnix' CC=gcc OPT=0 Q= acvp"
    Write-Host "Building pinned mlkem-native ACVP binaries..."
    & $BashPath -lc $buildCommand
    if ($LASTEXITCODE -ne 0) {
        throw 'mlkem-native ACVP build failed.'
    }
}

$runs = @(
    @{ Name = 'keygen_fips203'; Prompt = "$vectorsUnix/fips203/ML-KEM-keyGen/prompt.json"; Expected = "$vectorsUnix/fips203/ML-KEM-keyGen/expectedResults.json" },
    @{ Name = 'encap_decap_fips203'; Prompt = "$vectorsUnix/fips203/ML-KEM-encapDecap/prompt.json"; Expected = "$vectorsUnix/fips203/ML-KEM-encapDecap/expectedResults.json" },
    @{ Name = 'encap_decap_fips203_tr1'; Prompt = "$vectorsUnix/fips203-tr1/ML-KEM-encapDecap/prompt.json"; Expected = "$vectorsUnix/fips203-tr1/ML-KEM-encapDecap/expectedResults.json" }
)

foreach ($run in $runs) {
    $log = Join-Path $results ($run.Name + '.log')
    # Git for Windows exposes the installed interpreter as `python`; some
    # Unix hosts use `python3`, so keep the Windows entry deterministic.
    $command = "cd '$sourceUnix' && if command -v python >/dev/null 2>&1; then python test/acvp/acvp_client.py -p '$($run.Prompt)' -e '$($run.Expected)'; else python3 test/acvp/acvp_client.py -p '$($run.Prompt)' -e '$($run.Expected)'; fi"
    Write-Host "Running $($run.Name)..."
    $captured = @(& $BashPath -lc $command 2>&1)
    $exitCode = $LASTEXITCODE
    $captured | ForEach-Object { $_.ToString() } | Set-Content -Encoding UTF8 -LiteralPath $log
    $captured | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) {
        throw "ACVP run failed: $($run.Name)"
    }
}

$metadata = [ordered]@{
    reference = 'mlkem-native'
    source = 'build/kat_sources/mlkem-native'
    mlkem_native_commit = 'b3ba7b32773e657dd37f6f87bce82528459ad8a4'
    acvp_server_commit = '975de31eb83d87039ec88934fdc47d8c312b892d'
    vector_root = 'vectors/official_kat/acvp'
    vector_manifest = 'vectors/official_kat/acvp/SHA256SUMS'
    generated_utc = (Get-Date).ToUniversalTime().ToString('o')
    build_command = "make SHELL=<git-bash>/sh.exe CC=gcc OPT=0 Q= acvp"
    runs = @($runs | ForEach-Object { $_.Name })
}
$metadata | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $results 'run_metadata.json')
Write-Host "ACVP host regression completed. Logs: $results"

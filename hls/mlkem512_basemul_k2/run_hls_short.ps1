param(
    [string]$BuildRoot = 'E:\hlsk2',
    [string]$VitisHls = 'E:\Xilinx\Vitis_HLS\2024.2\bin\vitis_hls.bat'
)

$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path $PSScriptRoot).Path
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$stageRoot = [IO.Path]::GetFullPath($BuildRoot)

New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceRoot 'src') -Destination $stageRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'tb') -Destination $stageRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'run_hls.tcl') -Destination $stageRoot -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'hls_config.cfg') -Destination $stageRoot -Force

if (-not (Test-Path -LiteralPath $VitisHls)) {
    throw "Vitis HLS executable not found: $VitisHls"
}

Push-Location $stageRoot
try {
    & $VitisHls -f run_hls.tcl
    if ($LASTEXITCODE -ne 0) { throw "Vitis HLS failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

$solutionRoot = Join-Path $stageRoot 'mlkem512_basemul_k2_vivado\solution1'
$reportRoot = Join-Path $solutionRoot 'syn\report'
$evidenceRoot = Join-Path $repoRoot 'results\accelerator_interface\hls_synthesis'
$ipRoot = Join-Path $sourceRoot 'ip'
New-Item -ItemType Directory -Force -Path $evidenceRoot,$ipRoot | Out-Null

foreach ($name in @('mlkem512_basemul_acc_k2_csynth.rpt','csynth.rpt','csynth_design_size.rpt')) {
    Copy-Item -LiteralPath (Join-Path $reportRoot $name) -Destination $evidenceRoot -Force
}
Copy-Item -LiteralPath (Join-Path $solutionRoot 'csim\report\mlkem512_basemul_acc_k2_csim.log') `
    -Destination (Join-Path $evidenceRoot 'csim.log') -Force
$ipZip = Get-ChildItem -LiteralPath (Join-Path $solutionRoot 'impl\ip') -Filter 'xilinx_com_hls_mlkem512_basemul_acc_k2_1_0.zip' | Select-Object -First 1
if ($null -eq $ipZip) { throw 'HLS IP archive was not generated' }
Copy-Item -LiteralPath $ipZip.FullName -Destination $ipRoot -Force

Write-Host "HLS_PASS: reports=$evidenceRoot ip=$ipRoot"

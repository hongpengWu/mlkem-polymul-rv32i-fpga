$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$manifest = Import-Csv -LiteralPath (Join-Path $root 'docs/source_integrity.csv')
$updates = @{}
$updateFile = Join-Path $root 'docs/source_changes.csv'
if (Test-Path -LiteralPath $updateFile) {
    foreach ($entry in (Import-Csv -LiteralPath $updateFile)) {
        if ($updates.ContainsKey($entry.Path)) { throw "Duplicate source update: $($entry.Path)" }
        $updates[$entry.Path] = $entry
    }
}
foreach ($entry in $manifest) {
    $file = Join-Path $root $entry.Path
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing source: $($entry.Path)" }
    $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    $expected = $entry.SHA256
    if ($updates.ContainsKey($entry.Path)) {
        $update = $updates[$entry.Path]
        if ($update.OriginalSHA256 -ne $entry.SHA256) { throw "Source update baseline mismatch: $($entry.Path)" }
        $expected = $update.CurrentSHA256
    }
    if ($actual -ne $expected) { throw "Unexpected source content change: $($entry.Path)" }
}
foreach ($path in $updates.Keys) {
    if ($path -notin $manifest.Path) { throw "Source update not in baseline: $path" }
}
Write-Host "SOURCE_INTEGRITY_PASS: $($manifest.Count - $updates.Count) original files unchanged; $($updates.Count) documented configuration updates verified."

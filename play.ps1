param([string]$Coverage = "")
$env:Path = "C:\msys64\mingw64\bin;" + $env:Path
Set-Location $PSScriptRoot

# Back up the save before every launch and keep the newest 30.
if (Test-Path acww.sav) {
    New-Item -ItemType Directory -Force backups | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item acww.sav "backups\acww-$stamp.sav"
    Get-ChildItem backups\acww-*.sav | Sort-Object Name -Descending | Select-Object -Skip 30 | Remove-Item
    "save backed up to backups\acww-$stamp.sav"
}

if (-not $Coverage) { $Coverage = "run-" + (Get-Date -Format "yyyyMMdd-HHmmss") }
& C:\acww\ndsrecomp\runner\build-acww\nds_runner.exe bios --rom acww.nds --config game.toml --interactive `
  --freebios --generated-firmware --boot direct --rtc-host `
  --save-path acww.sav --firmware-state-path bios\firmware-state.bin `
  --coverage-manifest "generated\coverage\$Coverage.json"

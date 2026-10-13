param([string]$Coverage = "", [switch]$NoMods, [int]$Days = 0, [int]$Hours = 0, [string]$Watch = "", [switch]$Tier3, [switch]$HD, [int]$Res = 3, [int]$TexUp = 2)
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
# Apply the enabled mods in mods\ as soon as the game is up (tools\mods.py).
if (-not $NoMods) {
    Start-Process -FilePath py -ArgumentList "-3.12", "tools\mods.py", "apply" -NoNewWindow -WorkingDirectory $PSScriptRoot
}
# -Days N / -Hours N start the game's clock ahead of the PC clock (for testing).
$extra = @()
if ($Days -ne 0 -or $Hours -ne 0) {
    $extra += "--rtc-offset-days", "$Days", "--rtc-offset-hours", "$Hours"
    "game clock starts $Days day(s) and $Hours hour(s) ahead of the PC clock"
}
# -Tier3 runs everything in the interpreter (slow, but exact addresses for -Watch).
if ($Tier3) { $extra += "--force-tier3"; "interpreter only: expect the game to run slowly" }
# -HD draws the 3D at -Res times (2-4, default 3) with textures smoothed
# -TexUp times (1 = off, 2 or 4; default 2). Needs tools\patch_hd.py.
# The governor is held at step 1 so it never takes step 2, which would
# switch HD off.
if ($HD) {
    $extra += "--internal-resolution", "$Res", "--texture-upscale", "$TexUp", "--performance-governor", "stage1"
    "HD: 3D at ${Res}x, texture smoothing ${TexUp}x, governor held at step 1"
}
# -Watch lo-hi records writes to that range for tools\watch.py.
if ($Watch) { $env:NDS_WATCH = $Watch; "watching writes to $Watch" }
else { Remove-Item Env:NDS_WATCH -ErrorAction SilentlyContinue }
& C:\acww\ndsrecomp\runner\build-acww\nds_runner.exe bios --rom acww.nds --config game.toml --interactive `
  --freebios --generated-firmware --boot direct --rtc-host `
  --save-path acww.sav --firmware-state-path bios\firmware-state.bin `
  --coverage-manifest "generated\coverage\$Coverage.json" @extra

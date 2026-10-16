param([string]$Coverage = "", [switch]$NoMods, [int]$Days = 0, [int]$Hours = 0, [string]$Watch = "", [switch]$Tier3, [switch]$Fps, [switch]$NoDiscord)
$env:Path = "C:\msys64\mingw64\bin;" + $env:Path
Set-Location $PSScriptRoot
# Your choices live in settings.toml: graphics and screen layout are read by
# the runner itself, mods by tools\mods.py, and backups and Discord here.
# The switches on this script are for development.
$settings = if (Test-Path settings.toml) { Get-Content settings.toml -Raw } else { "" }
function Setting([string]$Name, [string]$Default) {
    if ($settings -match "(?m)^\s*$Name\s*=\s*([^#\r\n]+)") { return $Matches[1].Trim().Trim('"') }
    return $Default
}
# Switches an older play.ps1 may have left in this window would win over
# settings.toml, so clear them.
Remove-Item Env:ACWW_SMOOTH_2D, Env:ACWW_HD_TEXT, Env:ACWW_SHOW_FPS -ErrorAction SilentlyContinue
# Back up the save before every launch and keep the newest few.
if ((Setting "backup_on_launch" "true") -eq "true" -and (Test-Path acww.sav)) {
    $keep = [int](Setting "keep_backups" "30")
    New-Item -ItemType Directory -Force backups | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item acww.sav "backups\acww-$stamp.sav"
    Get-ChildItem backups\acww-*.sav | Sort-Object Name -Descending | Select-Object -Skip $keep | Remove-Item
    "save backed up to backups\acww-$stamp.sav"
}
if (-not $Coverage) { $Coverage = "run-" + (Get-Date -Format "yyyyMMdd-HHmmss") }
# Apply the mods chosen in settings.toml as soon as the game is up (tools\mods.py).
if (-not $NoMods) {
    Start-Process -FilePath py -ArgumentList "-3.12", "tools\mods.py", "apply" -NoNewWindow -WorkingDirectory $PSScriptRoot
}
# Discord presence (tools\presence.py) runs alongside the game unless it is
# off in settings.toml or -NoDiscord is given.
if (-not $NoDiscord -and (Setting "presence" "true") -eq "true") {
    $presence = @("-3.12", "tools\presence.py")
    if ((Setting "show_names" "true") -ne "true") { $presence += "--hide-names" }
    if ((Setting "show_bells" "true") -ne "true") { $presence += "--hide-bells" }
    Start-Process -FilePath py -ArgumentList $presence -NoNewWindow -WorkingDirectory $PSScriptRoot
}
# -Days N / -Hours N start the game's clock ahead of the PC clock (for testing).
$extra = @()
if ($Days -ne 0 -or $Hours -ne 0) {
    $extra += "--rtc-offset-days", "$Days", "--rtc-offset-hours", "$Hours"
    "game clock starts $Days day(s) and $Hours hour(s) ahead of the PC clock"
}
# -Tier3 runs everything in the interpreter (slow, but exact addresses for -Watch).
if ($Tier3) { $extra += "--force-tier3"; "interpreter only: expect the game to run slowly" }
# -Fps shows the frame rate in the title bar whatever settings.toml says.
if ($Fps) { $env:ACWW_SHOW_FPS = "1" }
# -Watch lo-hi records writes to that range for tools\watch.py.
if ($Watch) { $env:NDS_WATCH = $Watch; "watching writes to $Watch" }
else { Remove-Item Env:NDS_WATCH -ErrorAction SilentlyContinue }
& C:\acww\ndsrecomp\runner\build-acww\nds_runner.exe bios --rom acww.nds --config game.toml --interactive `
  --freebios --generated-firmware --boot direct --rtc-host `
  --save-path acww.sav --firmware-state-path bios\firmware-state.bin `
  --coverage-manifest "generated\coverage\$Coverage.json" @extra

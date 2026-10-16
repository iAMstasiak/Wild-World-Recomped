param([string]$Coverage = "", [switch]$NoMods, [int]$Days = 0, [int]$Hours = 0, [string]$Watch = "", [switch]$Tier3, [switch]$Fps, [switch]$NoDiscord)
$env:Path = "C:\msys64\mingw64\bin;" + $env:Path
Set-Location $PSScriptRoot
# Your choices live in settings.toml. The runner reads all of it itself: it
# backs up the save, applies the mods and shows Discord presence, so no
# Python runs alongside the game. The switches here are for development.
# Switches an older play.ps1 may have left in this window would win over
# settings.toml, so clear them.
Remove-Item Env:ACWW_SMOOTH_2D, Env:ACWW_HD_TEXT, Env:ACWW_SHOW_FPS -ErrorAction SilentlyContinue
if (-not $Coverage) { $Coverage = "run-" + (Get-Date -Format "yyyyMMdd-HHmmss") }
# -NoMods and -NoDiscord leave those out for this run only.
if ($NoMods) { $env:ACWW_NO_MODS = "1" } else { Remove-Item Env:ACWW_NO_MODS -ErrorAction SilentlyContinue }
if ($NoDiscord) { $env:ACWW_NO_DISCORD = "1" } else { Remove-Item Env:ACWW_NO_DISCORD -ErrorAction SilentlyContinue }
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

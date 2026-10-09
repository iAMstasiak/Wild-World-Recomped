$env:Path = "C:\msys64\mingw64\bin;" + $env:Path
Set-Location $PSScriptRoot
$manifests = (Get-ChildItem generated\coverage\*.json).FullName
if (Test-Path generated\ingest) { Remove-Item -Recurse -Force generated\ingest }
py -3.12 C:\acww\ndsrecomp\tools\ingest_coverage_manifests.py @manifests --images generated\inputs --rom-sha1 77fde3e30e1e6068395d1f96ea63be569b61c351 --out generated\ingest | Out-Null
if ($LASTEXITCODE) { throw "coverage ingest failed" }
$r = Get-Content generated\ingest\ingest-report.json -Raw | ConvertFrom-Json
"ingest: $($r.manifests_accepted) sessions, $($r.entry_points_merged) entry points, $($r.page_versions_not_in_rom) runtime pages"
py -3.12 tools\make_banks.py --recompiler C:\acww\ndsrecomp\recompiler\build\nds_recompile.exe
if ($LASTEXITCODE) { throw "bank generation failed" }
& C:\msys64\mingw64\bin\cmake.exe --build C:\acww\ndsrecomp\runner\build-acww
if ($LASTEXITCODE) { throw "runner build failed" }
"rebuild complete"

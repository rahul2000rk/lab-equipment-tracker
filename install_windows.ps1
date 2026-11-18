# Right-click > Run with PowerShell. Installs deps, creates Desktop icon + auto-start of the background server.
$d = $PSScriptRoot
py -m pip install -q -r "$d\requirements.txt"
$pw = (Get-Command pyw.exe -ErrorAction SilentlyContinue).Source
if (-not $pw) { $pw = (Get-Command pythonw.exe).Source }
$ws = New-Object -ComObject WScript.Shell
function mk($path, $args2) {
  $s = $ws.CreateShortcut($path); $s.TargetPath = $pw; $s.Arguments = "`"$d\launcher.pyw`" $args2"; $s.WorkingDirectory = $d
  if (Test-Path "$d\icon.ico") { $s.IconLocation = "$d\icon.ico" }; $s.Save() }
mk "$([Environment]::GetFolderPath('Desktop'))\Lab Tracker.lnk" ""
mk "$([Environment]::GetFolderPath('Startup'))\Lab Tracker Server.lnk" "--server"
Write-Host "Done. Double-click 'Lab Tracker' on the Desktop."

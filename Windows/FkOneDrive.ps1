<#
.SYNOPSIS
  Fixes Windows Known Folder locations after OneDrive removal:
  - Creates local profile folders (Desktop, Documents, Pictures, etc.)
  - Moves content from OneDrive-backed folders back to local folders
  - Resets HKCU\User Shell Folders (friendly names + key GUIDs)
  - Fixes screenshot save location to %USERPROFILE%\Pictures\Screenshots
  - Restarts Explorer to apply changes

.PREREQUISITES (DO THIS FIRST)
  1) Unlink OneDrive (prevents Windows from reapplying folder redirection)
     - Click the OneDrive cloud icon in the system tray
     - Settings (gear) -> Settings -> Account -> Unlink this PC

  2) Disable OneDrive from auto-starting (stops it from reasserting folder redirection after cleanup)
     - Task Manager -> Startup apps -> Microsoft OneDrive -> Disable
     - (Optional) Settings -> Apps -> Installed apps -> Microsoft OneDrive -> Uninstall

  3) Restore default folder locations (Windows UI method, if possible)
     For each of these: Desktop, Documents, Pictures, Downloads
     - Right-click folder in File Explorer -> Properties -> Location tab
     - Click "Restore Default" -> Apply
     - When prompted to move files to the new location, choose "Yes"

     NOTE:
     If Windows refuses due to "folder can't be moved" / Access Denied,
     run this script FIRST to normalize the registry + paths,
     then retry Restore Default from the Location tab.

.NOTES
  - Safe-by-default: uses ROBOCOPY /MOVE to migrate content if OneDrive folders exist
  - Universal: works for "OneDrive" and "OneDrive - <OrgName>"
  - Run as the affected user account
#>


$ErrorActionPreference = "Stop"

function Write-Section($msg) {
  Write-Host "`n=== $msg ===" -ForegroundColor Cyan
}

function Get-OneDriveRoots {
  $user = $env:USERPROFILE
  $roots = @()

  # Standard personal OneDrive
  $std = Join-Path $user "OneDrive"
  if (Test-Path $std) { $roots += $std }

  # Business/School OneDrive patterns: "OneDrive - Company"
  $roots += Get-ChildItem -Path $user -Directory -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -like "OneDrive - *" } |
           Select-Object -ExpandProperty FullName

  $roots | Select-Object -Unique
}

function Ensure-Folder($path) {
  if (-not (Test-Path $path)) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    Write-Host "Created: $path"
  }
}

function Move-Contents($src, $dst) {
  if (-not (Test-Path $src)) { return }
  Ensure-Folder $dst

  # Only move if there's actually something inside
  $hasStuff = Get-ChildItem -Path $src -Force -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $hasStuff) { return }

  Write-Host "Moving: `n  FROM: $src`n  TO  : $dst" -ForegroundColor Yellow

  # Robust move, avoids junction loops
  robocopy $src $dst /E /MOVE /R:1 /W:1 /XJ /NFL /NDL | Out-Null
}

function Set-UserShellFolder($name, $value) {
  $regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
  New-ItemProperty -Path $regPath -Name $name -Value $value -PropertyType ExpandString -Force | Out-Null
  Write-Host "Set: $name -> $value"
}

Write-Section "Detecting OneDrive roots"
$OneDriveRoots = Get-OneDriveRoots
if ($OneDriveRoots.Count -eq 0) {
  Write-Host "No OneDrive folder roots detected under $env:USERPROFILE (that's OK)." -ForegroundColor DarkYellow
} else {
  $OneDriveRoots | ForEach-Object { Write-Host "Found: $_" }
}

Write-Section "Creating standard local folders"
$User = $env:USERPROFILE

$Local = @{
  Desktop    = Join-Path $User "Desktop"
  Documents  = Join-Path $User "Documents"
  Pictures   = Join-Path $User "Pictures"
  Music      = Join-Path $User "Music"
  Videos     = Join-Path $User "Videos"
  Downloads  = Join-Path $User "Downloads"
  Screenshots= Join-Path $User "Pictures\Screenshots"
}

$Local.Values | ForEach-Object { Ensure-Folder $_ }

Write-Section "Migrating content from OneDrive back to local profile folders (if present)"
foreach ($od in $OneDriveRoots) {
  Move-Contents (Join-Path $od "Desktop")    $Local.Desktop
  Move-Contents (Join-Path $od "Documents")  $Local.Documents
  Move-Contents (Join-Path $od "Pictures")   $Local.Pictures
  Move-Contents (Join-Path $od "Music")      $Local.Music
  Move-Contents (Join-Path $od "Videos")     $Local.Videos
  Move-Contents (Join-Path $od "Downloads")  $Local.Downloads

  # Some OneDrive setups store screenshots under Pictures\Screenshots
  Move-Contents (Join-Path $od "Pictures\Screenshots") $Local.Screenshots
}

Write-Section "Resetting User Shell Folders (friendly names)"
# Friendly names Windows uses
Set-UserShellFolder "Desktop"       "%USERPROFILE%\Desktop"
Set-UserShellFolder "Personal"      "%USERPROFILE%\Documents"  # Documents
Set-UserShellFolder "My Pictures"   "%USERPROFILE%\Pictures"
Set-UserShellFolder "My Music"      "%USERPROFILE%\Music"
Set-UserShellFolder "My Video"      "%USERPROFILE%\Videos"
Set-UserShellFolder "{374DE290-123F-4565-9164-39C4925E467B}" "%USERPROFILE%\Downloads"  # Downloads GUID

Write-Section "Resetting User Shell Folders (key GUIDs that commonly stay stuck on OneDrive)"
# Pictures GUID commonly used in your screenshot
Set-UserShellFolder "{0DDD015D-B06C-45D5-8C4C-F59713854639}" "%USERPROFILE%\Pictures"

# Documents GUID commonly used in your screenshot
Set-UserShellFolder "{F42EE2D3-909F-4907-8871-4C22FC0BF756}" "%USERPROFILE%\Documents"

Write-Section "Fixing screenshot save location"
# Screenshots KnownFolder GUID
Set-UserShellFolder "{B7BEDE81-DF94-4682-A7D8-57A52620B86F}" "%USERPROFILE%\Pictures\Screenshots"

Write-Section "Restarting Explorer to apply changes"
Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Process explorer.exe

Write-Section "Validation (show any remaining OneDrive paths in User Shell Folders)"
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
$props = (Get-ItemProperty -Path $regPath)
$oneDriveHits = $props.PSObject.Properties |
  Where-Object { $_.Value -is [string] -and $_.Value -match "OneDrive" } |
  Select-Object Name, Value

if ($oneDriveHits) {
  Write-Host "WARNING: Some entries still reference OneDrive:" -ForegroundColor Red
  $oneDriveHits | Format-Table -AutoSize
  Write-Host "If these are business-specific GUIDs on that machine, add them to the script." -ForegroundColor DarkYellow
} else {
  Write-Host "OK: No OneDrive paths detected in User Shell Folders." -ForegroundColor Green
}

Write-Host "`nDone. If an app still saves to the wrong place, sign out/in once." -ForegroundColor Green

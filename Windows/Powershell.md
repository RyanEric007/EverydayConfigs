# Powershell Profile

```powershell
# =====================================
# 🖥️ SYSTEM MANAGEMENT
# =====================================

# 'u' - Upgrade all packages via winget, including unknown sources
function u {
    winget upgrade --all --include-unknown
}

# 'eb' - Empty the Recycle Bin with error handling
function eb {
    try {
        Clear-RecycleBin -Force -ErrorAction Stop
        Write-Host "🗑️ Recycle Bin emptied successfully."
    } catch {
        Write-Warning "⚠️ Some recycle bins could not be cleared (e.g., OneDrive or disconnected drives)."
    }
}

# =====================================
# 🐍 PYTHON UTILITIES
# =====================================

# 'cu' - Upgrade all Conda packages and clean up caches
function cu {
    conda upgrade --all -y
    conda clean -a -y
}

# 'py' - Shortcut for launching Python 3
function py { python3 }

# 'ipy' - Shortcut for launching IPython 3
function ipy { ipython3 }

# =====================================
# ⚙️ GENERAL SHELL SHORTCUTS
# =====================================

# 'c' - Clear the terminal screen
function c { Clear-Host }

# 'll' - List files with hidden ones, sorted by last modified date, in a table format
function ll {
    Get-ChildItem -Force |
        Sort-Object LastWriteTime -Descending |
        Format-Table Mode, LastWriteTime, Length, Name -AutoSize
}

# 'ip' - Get Local IP address from powrshell
function ip {
(Get-NetIPConfiguration -InterfaceAlias "Wi-Fi").IPv4Address.IPAddress
}

# 'myip' - Get public IP address from AWS checkip service
function myip {
    (Invoke-WebRequest 'https://checkip.amazonaws.com').Content.Trim()
}
```
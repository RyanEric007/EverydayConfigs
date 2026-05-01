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
        Write-Warning "⚠️ Some recycle bins could not be cleared."
    }
}

# =====================================
# 🐍 PYTHON UTILITIES
# =====================================

# 'py' - Shortcut for launching Python 3
function py {
    python3
}

# 'ipy' - Shortcut for launching IPython 3
function ipy {
    ipython3
}

# =====================================
# 🔐 TAILSCALE UTILITIES
# =====================================

# 'tsips' - Show Tailscale peers with IPv4 and IPv6 addresses
function tsips {
    (tailscale status --json | ConvertFrom-Json).Peer.PSObject.Properties.Value |
        Sort-Object HostName |
        ForEach-Object {
            [pscustomobject]@{
                Host = $_.HostName
                IPv4 = ($_.TailscaleIPs | Where-Object { $_ -like "100.*" })
                IPv6 = ($_.TailscaleIPs | Where-Object { $_ -like "fd7a:*" })
            }
        }
}

# 'tsme' - Show this machine's Tailscale IPv4 and IPv6 addresses
function tsme {
    $ts = tailscale status --json | ConvertFrom-Json

    [pscustomobject]@{
        Host = $ts.Self.HostName
        IPv4 = ($ts.Self.TailscaleIPs | Where-Object { $_ -like "100.*" })
        IPv6 = ($ts.Self.TailscaleIPs | Where-Object { $_ -like "fd7a:*" })
    }
}

# 'tsping' - Ping a Tailscale host
function tsping {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName
    )

    tailscale ping $HostName
}

# =====================================
# ⚙️ GENERAL SHELL SHORTCUTS
# =====================================

# 'c' - Clear the terminal screen
function c {
    Clear-Host
}

# 'll' - List files with hidden ones, sorted by last modified date
function ll {
    Get-ChildItem -Force |
        Sort-Object LastWriteTime -Descending |
        Format-Table Mode, LastWriteTime, Length, Name -AutoSize
}

# 'myip' - Get public IP address from AWS checkip service
function myip {
    (Invoke-WebRequest 'https://checkip.amazonaws.com').Content.Trim()
}

# =====================================
# 🚀 SESSION CLEANUP / STARTUP SANITIZATION
# =====================================

Clear-Host
```

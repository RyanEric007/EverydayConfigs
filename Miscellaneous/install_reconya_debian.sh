#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Reconya: Ubuntu install + run (start -> finish)
# - Installs: git, make, curl, wget, nmap, nodejs, npm
# - Installs Go 1.21.13 to /usr/local/go and persists PATH
# - Clones/updates repo to ~/Media/GitHub/reconya
# - Runs: make install, then make start
# ============================================================

GO_VERSION="1.21.13"
GO_TARBALL="go${GO_VERSION}.linux-amd64.tar.gz"
GO_URL="https://dl.google.com/go/${GO_TARBALL}"

BASE_DIR="${HOME}/Media/GitHub"
REPO_DIR="${BASE_DIR}/reconya"
BASHRC="${HOME}/.bashrc"
GO_BIN_LINE='export PATH=$PATH:/usr/local/go/bin'

log() { printf "\n[%s] %s\n" "$(date +'%F %T')" "$*"; }

require_sudo() {
  if ! sudo -n true 2>/dev/null; then
    log "Sudo required. You may be prompted for your password."
  fi
  sudo true
}

ensure_packages() {
  log "Installing required packages (git, make, wget, curl, nmap, nodejs, npm)..."
  sudo apt update
  sudo apt install -y git make wget curl nmap nodejs npm
}

ensure_nmap_suid() {
  log "Setting nmap SUID for better LAN discovery (MAC/vendor) if possible..."
  local nmap_path
  nmap_path="$(command -v nmap)"
  if [[ -z "${nmap_path}" ]]; then
    echo "ERROR: nmap not found after install." >&2
    exit 1
  fi
  # Only set if not already SUID
  if ! ls -l "${nmap_path}" | awk '{print $1}' | grep -q "s"; then
    sudo chmod u+s "${nmap_path}" || true
  fi
}

install_go() {
  log "Installing Go ${GO_VERSION} to /usr/local/go ..."
  # Download tarball if missing
  if [[ ! -f "/tmp/${GO_TARBALL}" ]]; then
    log "Downloading ${GO_URL}"
    wget -O "/tmp/${GO_TARBALL}" "${GO_URL}"
  else
    log "Go tarball already exists: /tmp/${GO_TARBALL}"
  fi

  sudo rm -rf /usr/local/go
  sudo tar -C /usr/local -xzf "/tmp/${GO_TARBALL}"

  # Ensure PATH is persisted
  if ! grep -Fxq "${GO_BIN_LINE}" "${BASHRC}" 2>/dev/null; then
    log "Persisting Go PATH in ${BASHRC}"
    echo "" >> "${BASHRC}"
    echo "# Go (Reconya requirement)" >> "${BASHRC}"
    echo "${GO_BIN_LINE}" >> "${BASHRC}"
  else
    log "Go PATH already present in ${BASHRC}"
  fi

  # Export for current script session
  export PATH="$PATH:/usr/local/go/bin"
}

verify_versions() {
  log "Verifying toolchain versions..."
  echo -n "Go:     "; go version
  echo -n "Nmap:   "; nmap --version | head -n 1
  echo -n "Node:   "; node -v
  echo -n "NPM:    "; npm -v
}

clone_or_update_repo() {
  log "Preparing repo directory: ${BASE_DIR}"
  mkdir -p "${BASE_DIR}"

  if [[ -d "${REPO_DIR}/.git" ]]; then
    log "Reconya repo already exists. Pulling latest..."
    git -C "${REPO_DIR}" pull --ff-only
  else
    log "Cloning Reconya..."
    git clone https://github.com/Dyneteq/reconya.git "${REPO_DIR}"
  fi
}

build_and_start() {
  log "Running make install..."
  ( cd "${REPO_DIR}" && make install )

  log "Starting Reconya (make start)..."
  ( cd "${REPO_DIR}" && make start )
}

post_run_notes() {
  cat <<'EOF'

============================================================
Reconya should now be running.

Web UI:
  http://localhost:3008

Common ops (run inside repo dir):
  cd ~/Media/GitHub/reconya
  make status
  make logs
  make stop
  make start

If you don't see devices:
  - Confirm you are on the same L2 network segment as targets.
  - Ensure nmap has SUID:
      ls -l "$(which nmap)"
    The permissions should show an 's' in the user execute spot.
============================================================
EOF
}

main() {
  require_sudo
  ensure_packages
  ensure_nmap_suid
  install_go
  verify_versions
  clone_or_update_repo
  build_and_start
  post_run_notes
}

main "$@"

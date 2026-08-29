# ZSH for macOS
---

Check your shells:
```bash
cat /etc/shells
```

Change your Shell:
```bash
sudo chsh -s /bin/zsh root
```
Create config:
```bash
vim ~/.zshrc
```

Add to .zshrc
```bash
#### =========================================================
#### ~/.zshrc — macOS Apple Silicon
#### User + Root Safe
#### =========================================================


##### =========================================================
##### USER / ROOT DETECTION
##### =========================================================

if [[ $EUID -eq 0 ]]; then
    IS_ROOT=1
else
    IS_ROOT=0
fi


##### =========================================================
##### PATH / HOMEBREW
##### =========================================================

# Base macOS system paths
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Apple Silicon Homebrew — user only
if [[ $IS_ROOT -eq 0 && -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# Homebrew Python unversioned commands: python, pip
if [[ $IS_ROOT -eq 0 && -d /opt/homebrew/opt/python@3.14/libexec/bin ]]; then
    export PATH="/opt/homebrew/opt/python@3.14/libexec/bin:$PATH"
fi

# User-specific application paths
if [[ $IS_ROOT -eq 0 ]]; then

    # User-installed Python programs
    [[ -d "$HOME/Library/Python/3.14/bin" ]] && \
        export PATH="$HOME/Library/Python/3.14/bin:$PATH"

    # LM Studio CLI
    [[ -d "$HOME/.lmstudio/bin" ]] && \
        export PATH="$HOME/.lmstudio/bin:$PATH"

    # Grok CLI
    [[ -d "$HOME/.grok/bin" ]] && \
        export PATH="$HOME/.grok/bin:$PATH"

fi

# Remove duplicate PATH entries
typeset -U path PATH


##### =========================================================
##### ZSH CACHE / HISTORY
##### =========================================================

export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"

mkdir -p "$XDG_CACHE_HOME/zsh"

HISTFILE="$XDG_CACHE_HOME/zsh/history"
HISTSIZE=50000
SAVEHIST=50000


##### =========================================================
##### ZSH OPTIONS
##### =========================================================

# History
setopt APPEND_HISTORY
setopt SHARE_HISTORY
setopt INC_APPEND_HISTORY
setopt HIST_IGNORE_DUPS
setopt HIST_REDUCE_BLANKS
setopt HIST_EXPIRE_DUPS_FIRST

# Globbing
setopt NO_NOMATCH
setopt NULL_GLOB
setopt EXTENDED_GLOB
setopt NO_CASE_GLOB

# Shell behavior
setopt NO_BEEP
setopt INTERACTIVE_COMMENTS

# Pipelines return failure if any command fails
set -o pipefail


##### =========================================================
##### COMPLETION PATHS
##### =========================================================

# Docker Desktop completions
if [[ $IS_ROOT -eq 0 && -d "$HOME/.docker/completions" ]]; then
    fpath=("$HOME/.docker/completions" $fpath)
fi

# Grok completions
if [[ $IS_ROOT -eq 0 && -d "$HOME/.grok/completions/zsh" ]]; then
    fpath=("$HOME/.grok/completions/zsh" $fpath)
fi

# Remove duplicate completion paths
typeset -U fpath


##### =========================================================
##### ZSH COMPLETION
##### =========================================================

autoload -Uz compinit
compinit -d "$XDG_CACHE_HOME/zsh/zcompdump"


##### =========================================================
##### COLORS
##### =========================================================

autoload -Uz colors
colors


##### =========================================================
##### PROMPT
##### =========================================================

APPLE_NORMAL="🍏"
APPLE_ROOT="🍎"

COLOR_NORMAL="%F{green}"
COLOR_INFO="%F{blue}"
COLOR_ROOT="%F{red}"
COLOR_WHITE="%F{white}"

if [[ $IS_ROOT -eq 1 ]]; then

    PROMPT="${COLOR_ROOT}┌─${COLOR_WHITE}%n${APPLE_ROOT}%m${COLOR_ROOT} [%~]%f
${COLOR_ROOT}└─${COLOR_WHITE}# %f"

else

    PROMPT="${COLOR_NORMAL}┌─${COLOR_INFO}%n${APPLE_NORMAL}%m${COLOR_NORMAL} [%~]%f
${COLOR_NORMAL}└─${COLOR_INFO}$ %f"

fi

# Right-side clock
RPROMPT="%F{yellow}%*%f"


##### =========================================================
##### PRE-COMMAND PROMPT HOOK
##### =========================================================

precmd() {

    # Capture previous command's exit status immediately
    local exit_code=$?

    # Set terminal title
    print -Pn "\e]0;%n@%m: %~\a"

    # Display failures above the next prompt
    if (( exit_code != 0 )); then
        print -P "%F{red}[exit ${exit_code}]%f"
    fi
}


##### =========================================================
##### GENERAL ALIASES
##### =========================================================

# Directory listings
alias ls='ls -G'
alias ll='ls -lahG'
alias la='ls -laG'
alias l='ls -lG'
alias lt='ls -ltrhG'

# Navigation
alias ..='cd ..'
alias ...='cd ../..'

# File operations
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'

# Utilities
alias grep='grep --color=auto'
alias c='clear'
alias h='fc -l 1'
alias q='exit'


##### =========================================================
##### USER-ONLY SETTINGS
##### =========================================================

if [[ $IS_ROOT -eq 0 ]]; then

    ##### Editors

    export EDITOR='vim'
    export VISUAL='vim'
    export PAGER='less'


    ##### Python

    alias python='python3'
    alias pip='pip3'
    alias py='python3'

    if command -v ipython3 >/dev/null 2>&1; then
        alias ipy='ipython3'
    fi


    ##### Networking

    alias myip='curl -s checkip.amazonaws.com'
    alias lip='ipconfig getifaddr en0'
    alias ports='lsof -i -P -n | grep LISTEN'


    ##### Homebrew

    if command -v brew >/dev/null 2>&1; then
        export HOMEBREW_NO_ASK=1
        export HOMEBREW_NO_ENV_HINTS=1

        alias u='brew update && brew upgrade && brew cleanup'
        alias brewdoctor='brew doctor'
    fi

fi


##### =========================================================
##### TAILSCALE
##### =========================================================

if [[ -x "/Applications/Tailscale.app/Contents/MacOS/Tailscale" ]]; then
    alias tailscale="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
fi


# Display all Tailscale peers and addresses
tsips() {

    if ! command -v jq >/dev/null 2>&1; then
        echo "Error: jq is required."
        return 1
    fi

    if ! command -v tailscale >/dev/null 2>&1; then
        echo "Error: tailscale command not found."
        return 1
    fi

    printf "%-20s %-18s %-40s\n" "HOST" "IPv4" "IPv6"
    printf "%-20s %-18s %-40s\n" "----" "----" "----"

    tailscale status --json |
        jq -r '
            .Peer
            | to_entries[]
            | [
                .value.HostName,
                ([.value.TailscaleIPs[]? | select(startswith("100."))][0] // "-"),
                ([.value.TailscaleIPs[]? | select(startswith("fd7a:"))][0] // "-")
              ]
            | @tsv
        ' |
        while IFS=$'\t' read -r host ipv4 ipv6; do
            printf "%-20s %-18s %-40s\n" "$host" "$ipv4" "$ipv6"
        done
}


# Display this Mac's Tailscale addresses
tsme() {

    if ! command -v jq >/dev/null 2>&1; then
        echo "Error: jq is required."
        return 1
    fi

    if ! command -v tailscale >/dev/null 2>&1; then
        echo "Error: tailscale command not found."
        return 1
    fi

    printf "%-20s %-18s %-40s\n" "HOST" "IPv4" "IPv6"
    printf "%-20s %-18s %-40s\n" "----" "----" "----"

    tailscale status --json |
        jq -r '
            .Self
            | [
                .HostName,
                ([.TailscaleIPs[]? | select(startswith("100."))][0] // "-"),
                ([.TailscaleIPs[]? | select(startswith("fd7a:"))][0] // "-")
              ]
            | @tsv
        ' |
        while IFS=$'\t' read -r host ipv4 ipv6; do
            printf "%-20s %-18s %-40s\n" "$host" "$ipv4" "$ipv6"
        done
}


# Tailscale ping helper
tsping() {

    if [[ -z "$1" ]]; then
        echo "Usage: tsping <hostname>"
        return 1
    fi

    tailscale ping "$1"
}


##### =========================================================
##### ZSH PLUGINS
##### =========================================================

if [[ $IS_ROOT -eq 0 ]]; then

    # Autosuggestions
    if [[ -f /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
        source /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh
    fi

    # Syntax highlighting should normally be sourced last
    if [[ -f /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
        source /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
    fi

fi

```

```
sudo cp ~/.zshrc /var/root/.zshrc
```
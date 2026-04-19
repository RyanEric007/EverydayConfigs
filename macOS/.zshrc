#### =========================================================
#### Universal ~/.zshrc — macOS Ventura VM (Clean + Homebrew Safe)
#### =========================================================

# ====================== PATH & Homebrew ======================
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Load Homebrew environment
if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# Python convenience (if needed)
export PATH="/opt/homebrew/opt/python@3.14/libexec/bin:$PATH"

# ====================== ZSH Cache & Completions ======================
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
mkdir -p "$XDG_CACHE_HOME/zsh"

# Fix for Homebrew insecure directories (best for VMs)
autoload -Uz compinit
compinit -u -d "$XDG_CACHE_HOME/zsh/zcompdump"   # -u = ignore insecure dirs

# ====================== Colors & Prompt ======================
autoload -Uz colors
colors

# Simple clean prompt (you can keep your fancy one if you prefer)
PROMPT="%F{green}%n@%m %F{blue}%~ %f%# "
RPROMPT="%F{yellow}%*%f"

# ====================== History Settings ======================
setopt APPEND_HISTORY SHARE_HISTORY INC_APPEND_HISTORY
setopt HIST_IGNORE_DUPS HIST_REDUCE_BLANKS HIST_EXPIRE_DUPS_FIRST
HISTFILE="$XDG_CACHE_HOME/zsh/history"
HISTSIZE=10000
SAVEHIST=10000

# ====================== Shell Options ======================
setopt NO_NOMATCH NULL_GLOB NO_BEEP EXTENDED_GLOB INTERACTIVE_COMMENTS
set -o pipefail

# ====================== Aliases ======================
alias ls='ls -G'
alias ll='ls -lahG'
alias la='ls -laG'
alias l='ls -lG'
alias ..='cd ..'
alias ...='cd ../..'
alias grep='grep --color=auto'
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias c='clear'
alias h='history'
alias q='exit'
alias u='brew update && brew upgrade && brew cleanup'

# ====================== User-only Section (Plugins) ======================
if [[ $EUID -ne 0 ]]; then
  # Zsh plugins (load AFTER compinit)
  [[ -f /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]] && \
    source /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh

  [[ -f /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]] && \
    source /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh

  # Other user stuff
  export EDITOR=vim
  alias python=python3
  alias pip=pip3
  alias myip='curl -s checkip.amazonaws.com'
fi
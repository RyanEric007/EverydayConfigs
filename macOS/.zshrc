#### =========================================================
#### Universal ~/.zshrc — macOS Ventura VM (Homebrew Safe)
#### =========================================================

# ====================== PATH & Homebrew ======================
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Load Homebrew environment
if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# Python path
export PATH="/opt/homebrew/opt/python@3.14/libexec/bin:$PATH"

# ====================== ZSH Cache & Completions ======================
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
mkdir -p "$XDG_CACHE_HOME/zsh"

# Fix for "insecure directories" warning from Homebrew
autoload -Uz compinit
compinit -u -d "$XDG_CACHE_HOME/zsh/zcompdump"   # -u ignores insecure dirs

# ====================== Colors ======================
autoload -Uz colors
colors

# ====================== Prompt (Your Original Style) ======================
APPLE_NORMAL="🍏"
APPLE_ROOT="🍎"
COLOR_NORMAL="%F{green}"
COLOR_INFO="%F{blue}"
COLOR_ROOT="%F{red}"
COLOR_WHITE="%F{white}"

if [[ $EUID -eq 0 ]]; then
  PROMPT="${COLOR_ROOT}┌─${COLOR_WHITE}%n${APPLE_ROOT}%m${COLOR_ROOT} [%~]%f
${COLOR_ROOT}└─${COLOR_WHITE}# %f"
else
  PROMPT="${COLOR_NORMAL}┌─${COLOR_INFO}%n${APPLE_NORMAL}%m${COLOR_NORMAL} [%~]%f
${COLOR_NORMAL}└─${COLOR_INFO}$ %f"
fi

RPROMPT="%F{yellow}%*%f"

precmd() {
  if [[ $? -ne 0 ]]; then
    echo -n "%F{red}[exit $?]%f "
  fi
  print -Pn "\e]0;%n@%m: %~\a"
}

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
alias lt='ls -ltrhG'
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

# ====================== User-only Extras ======================
if [[ $EUID -ne 0 ]]; then
  # Extra paths
  export PATH="$HOME/.lmstudio/bin:$PATH"
  export PATH="$HOME/Library/Python/3.14/bin:$PATH"

  # Editors & Python aliases
  export EDITOR=vim
  alias python=python3
  alias pip=pip3
  alias py='python3'
  alias ipy='ipython3'

  # Networking
  alias myip='curl -s checkip.amazonaws.com'
  alias lip='ipconfig getifaddr en0'
  alias ports='lsof -i -P -n | grep LISTEN'

  # Zsh plugins — IMPORTANT: Load AFTER compinit
  [[ -f /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]] && \
    source /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh

  [[ -f /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]] && \
    source /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi
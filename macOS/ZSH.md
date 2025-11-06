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
#### ~/.zshrc — macOS (Apple Silicon) Unified Configuration
#### =========================================================
#### Author: Ryan
#### Platform: macOS (M1, Tahoe 26.1)
#### Purpose: Stable Zsh setup for dev, networking, and OSINT
#### =========================================================

#### -------------------------------
#### Homebrew (Apple Silicon)
#### -------------------------------
if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

#### -------------------------------
#### PATH Configuration
#### -------------------------------
# User Python binaries first
export PATH="$HOME/Library/Python/3.14/bin:$PATH"

# LM Studio CLI
[[ ":$PATH:" != *":/Users/rj/.lmstudio/bin:"* ]] && export PATH="/Users/rj/.lmstudio/bin:$PATH"

# Docker completions
fpath=(/Users/rj/.docker/completions $fpath)

#### -------------------------------
#### Auto Homebrew Update (Weekly)
#### -------------------------------
if [[ ! -f ~/.last_brew_update ]] || (( $(date +%s) - $(<~/.last_brew_update) > 604800 )); then
  brew update >/dev/null
  date +%s > ~/.last_brew_update
fi

#### -------------------------------
#### Autocompletion & Colors
#### -------------------------------
ZSH_COMPDUMP_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/zsh"
mkdir -p "$ZSH_COMPDUMP_DIR"

autoload -Uz compinit colors
colors
compinit -d "${ZSH_COMPDUMP_DIR}/zcompdump"

#### -------------------------------
#### Prompt Customization
#### -------------------------------
APPLE_NORMAL="🍏"
APPLE_ROOT="🍎"
COLOR_NORMAL="%F{green}"
COLOR_INFO="%F{blue}"
COLOR_ROOT="%F{red}"
COLOR_WHITE="%F{white}"

if [[ "$EUID" -eq 0 ]]; then
  PROMPT="${COLOR_ROOT}┌─${COLOR_WHITE}%n${APPLE_ROOT}%m${COLOR_ROOT} [%~]%f
${COLOR_ROOT}└─${COLOR_WHITE}# %f"
else
  PROMPT="${COLOR_NORMAL}┌─${COLOR_INFO}%n${APPLE_NORMAL}%m${COLOR_NORMAL} [%~]%f
${COLOR_NORMAL}└─${COLOR_INFO}$ %f"
fi

# Right-side prompt (time)
RPROMPT="%F{yellow}%*%f"

# Display last exit code if non-zero
precmd() {
  if [[ $? -ne 0 ]]; then
    echo -n "%F{red}[exit $?]%f "
  fi
  print -Pn "\e]0;%n@%m: %~\a"
}

#### -------------------------------
#### Shell Behavior & Safety
#### -------------------------------
setopt APPEND_HISTORY SHARE_HISTORY INC_APPEND_HISTORY
setopt HIST_IGNORE_DUPS HIST_REDUCE_BLANKS HIST_EXPIRE_DUPS_FIRST
setopt NO_NOMATCH NULL_GLOB NO_BEEP EXTENDED_GLOB NO_CASE_GLOB
setopt INTERACTIVE_COMMENTS
set -o pipefail

#### -------------------------------
#### History Configuration
#### -------------------------------
export XDG_CACHE_HOME="$HOME/.cache"
HISTFILE="$XDG_CACHE_HOME/zsh/history"
HISTSIZE=5000
SAVEHIST=5000

#### -------------------------------
#### Aliases
#### -------------------------------
# Python
alias python=python3
alias pip=pip3

# Safer file ops
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'

# ls shortcuts
alias ls='ls -G'
alias ll='ls -lahG'
alias la='ls -laG'
alias l='ls -lG'
alias lt='ls -ltrhG'

# Navigation
alias ..='cd ..'
alias ...='cd ../..'

# Utilities
alias grep='grep --color=auto'
alias egrep='grep -E --color=auto'
alias fgrep='grep -F --color=auto'
alias diff='diff --color=auto'
alias c='clear'
alias myip='curl -s checkip.amazonaws.com'
alias lip='ipconfig getifaddr en0'
alias ports='lsof -i -P -n | grep LISTEN'
alias py='python3'
alias ipy='ipython3'
alias path='print -l $path'
alias q='exit'
alias mkd='mkdir -p'
alias please='sudo'
alias g='git'
alias v='vim'
alias h='history'
alias u='brew update && brew upgrade && brew cleanup'
alias cc='sync && sudo purge && clear'
alias brewdoctor='HOMEBREW_NO_ENV_HINTS=1 brew doctor'

#### -------------------------------
#### Editor & Pager
#### -------------------------------
export EDITOR=vim
export VISUAL=vim
export PAGER=less

#### -------------------------------
#### Man Page Colors
#### -------------------------------
export LESS_TERMCAP_mb=$'\e[1;31m'
export LESS_TERMCAP_md=$'\e[1;36m'
export LESS_TERMCAP_me=$'\e[0m'
export LESS_TERMCAP_so=$'\e[01;33m'
export LESS_TERMCAP_se=$'\e[0m'
export LESS_TERMCAP_us=$'\e[1;32m'
export LESS_TERMCAP_ue=$'\e[0m'

#### -------------------------------
#### Key Bindings
#### -------------------------------
bindkey '^R' history-incremental-search-backward

#### -------------------------------
#### Plugins
#### -------------------------------
# Homebrew Zsh plugins
if [[ -d /opt/homebrew/share/zsh-autosuggestions ]]; then
  fpath+=('/opt/homebrew/share/zsh-autosuggestions')
  source /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh
fi

if [[ -d /opt/homebrew/share/zsh-syntax-highlighting ]]; then
  fpath+=('/opt/homebrew/share/zsh-syntax-highlighting')
  source /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

#### -------------------------------
#### Local Config (Optional)
#### -------------------------------
[[ -f ~/.zsh_aliases ]] && source ~/.zsh_aliases

#### -------------------------------
#### iTerm2 Integration
#### -------------------------------
test -e "${HOME}/.iterm2_shell_integration.zsh" && source "${HOME}/.iterm2_shell_integration.zsh"

#### -------------------------------
#### Python Integration
#### -------------------------------
export PYTHONPATH="$HOME/Library/Python/3.14/lib/python/site-packages:$PYTHONPATH"

```

```bash
#### -------------------------------
#### Install commands for my zshrc
#### -------------------------------

# Install Homebrew (if not installed)
# Visit brew.sh for latest, or run:
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Update brew
brew update

# Zsh enhancements
brew install zsh
brew install zsh-syntax-highlighting
brew install zsh-autosuggestions

# GNU tools (optional, if you want gnubin path)
brew install coreutils

# iTerm2 integration script (optional if using iTerm2)
curl -L https://iterm2.com/shell_integration/zsh \
    -o ~/.iterm2_shell_integration.zsh

# Development & tools
brew install vim
brew install git
brew install ipython
brew install python
brew install lsof
brew install curl
brew install diffutils

# Nice-to-haves
brew install less
brew install grep
brew install gnu-sed
brew install wget

# LM Studio (optional, if you use it)
# Usually installed via their official site or installer
# but if there’s a CLI, ensure it’s in your PATH

#### -------------------------------
#### End install commands
#### -------------------------------

```